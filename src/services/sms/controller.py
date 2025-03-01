from src.utils.ai_handler import send_text_to_chatgpt_for_agent
from src.utils.leads import create_or_update_lead, get_lead
from src.utils.telnyx import send_telnyx_message
from src.utils.event import create_or_update_event
from src.utils.helper_functions import handle_guest_card, format_phone_number
from src.utils.response import (
    SuccessResponseSerializer,
    ErrorResponseSerializer,
    response_structure
)

from src.db.database import db
from src.config.config import Config

from .serializer import SmsOutboundRequest, InboundCallEndedRequest

from fastapi import status

from google.cloud import firestore

from datetime import datetime

import logging, re


logger = logging.getLogger(__name__)


class SMSController:
    
    @classmethod
    async def handle_ai_response_for_agent(cls,payload):
        try:
            from_phone_number = payload.from_phone.phone_number
            to_phone_number = payload.to_phone[0].phone_number
            message = payload.text

            if not from_phone_number or not to_phone_number or not message:
                serializer = ErrorResponseSerializer(
                    success = False,
                    error = "Missing required fields: from_phoneNumber, toPhoneNumber, or message."
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            if len(from_phone_number) < 10 or len(to_phone_number) < 10:
                serializer = ErrorResponseSerializer(
                    success = False,
                    error = "All fields must have at least 10 characters."
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            if from_phone_number == to_phone_number:
                serializer = ErrorResponseSerializer(
                    success = False,
                    error = "From and To numbers are the same."
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            if from_phone_number in ["+17373093928", Config.TELNYX_PHONE_NUMBER]:
                serializer = ErrorResponseSerializer(
                    success = False,
                    error = "SMS from this number is blocked."
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            company_ref = db.collection("companies").where("agentFAQNumber", "==", to_phone_number).get()
            user_ref = db.collection("users").where("phoneNumber", "==", from_phone_number).get()

            if not company_ref or not user_ref:
                serializer = ErrorResponseSerializer(
                    success = False,
                    message = "You are not registered with an agency.",
                    error = "User or agent not found"
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            
            company_doc = company_ref[0]
            user_doc = user_ref[0]
            user_id = user_doc.id
            company_id = company_doc.id
            conversation_ref = user_doc.reference.collection("conversation")

            conversation_snapshot = conversation_ref.order_by("timestamp").stream()
            conversation = "\n".join(
                [str(doc.to_dict().get("content", "")) for doc in conversation_snapshot]
            )

            ai_response = await send_text_to_chatgpt_for_agent(conversation, message, from_phone_number, to_phone_number)

            logger.info(f"ai_response : {ai_response}")
            
            if "error" in ai_response or "warning" in ai_response:
                serializer = ErrorResponseSerializer(
                    success = False,
                    message = "Error processing request.",
                    error = str(ai_response.get("error", ai_response.get("warning")))
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            # Save inbound and AI response
            conversation_ref.add({"content": message, "timestamp": datetime.now().isoformat(), "direction": "inbound"})
            conversation_ref.add({"content": ai_response, "timestamp": datetime.now().isoformat(), "direction": "outbound"})

            task_data = ai_response.get("taskData", {})
            user_object = ai_response.get("userObject", {})

            if task_data.get("work"):
                action = task_data.get("action", "").lower()
                if action in ["create lead", "update lead"]:
                    lead_message, lead_id = await create_or_update_lead(task_data, user_id, company_id)
                    await send_telnyx_message("+19036467318", lead_message, Config.TELNYX_PHONE_NUMBER)
                elif action == "get lead":
                    await get_lead(task_data, user_object.get("phoneNumber"))
                elif action == "guest card":
                    await handle_guest_card(task_data, from_phone_number)
                elif action in ["create event", "update event"]:
                    event_message = await create_or_update_event(task_data, user_id, from_phone_number)
                    await send_telnyx_message("+19036467318", event_message, Config.TELNYX_PHONE_NUMBER)
                else:
                    logger.info(f"Unknown action: {action}")
            else:
                await send_telnyx_message("+19036467318", ai_response.get("chatResponse", ""), Config.TELNYX_PHONE_NUMBER)
            
            serializer = SuccessResponseSerializer(
                success=True,
                data=ai_response.get("chatResponse", "")
            )
            return response_structure(
                serializer=serializer,
                status_code=status.HTTP_200_OK
            )

        except Exception as e:
            logger.error(str(e),exc_info=True)
            serializer = ErrorResponseSerializer(
                    success = False,
                    message = "Internal Server Error",
                    error = str(e)
                )
            return response_structure(
                serializer=serializer,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @classmethod
    async def sms_outbound(cls,payload: SmsOutboundRequest):
        logger.info("SMS sent webhook triggered")
        leads_collection = db.collection("leads")
        lead_object = {}
        agent_phone_number = None
        lead_id = None

        try:
            
            lead_object = {
                "firstName": payload.firstName,
                "lastName": payload.lastName,
                "email": payload.email,
                "phoneNumberFrom": format_phone_number(payload.phone) or "",
                "phoneNumberTo": payload.phoneNumberTo,
                "moveInDate": payload.moveInDate,
                "budget": payload.budget,
                "desiredLocation": payload.desiredLocation,
                "howDidYouHear": payload.howDidYouHear,
                "companyName": payload.companyName,
                "bedsBath": payload.bedsBath,
                "subscribed": payload.subscribed,
                "criminalHistory": payload.criminalHistory,
                "needsApartment": True,
                "pathway": "website",
                "appointmentTime": "",
                "transcriptSummary": ""
            }

            if not lead_object["phoneNumberFrom"] or not lead_object["phoneNumberTo"] or \
            len(lead_object["phoneNumberFrom"]) < 10 or len(lead_object["phoneNumberTo"]) < 10:
                serializer = ErrorResponseSerializer(
                    success = False,
                    error = "Phone number is required and must be at least 10 characters long."
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            logger.info(f"Processed Lead Object Data: {lead_object}")

            existing_lead_query = leads_collection.where("phoneNumber", "==", lead_object["phoneNumberFrom"]).get()

            if existing_lead_query:
                logger.info(f"Lead already exists with phone {lead_object['phoneNumberFrom']}")
                existing_lead_doc = existing_lead_query[0]
                lead_id = existing_lead_doc.id
                existing_lead_doc.reference.set(lead_object, merge=True)
            else:
                logger.info(f"Creating new lead with phone {lead_object['phoneNumberFrom']}")
                new_lead_doc_ref = leads_collection.document()
                lead_id = new_lead_doc_ref.id
                new_lead_doc_ref.set(lead_object)

            company_snapshot = db.collection("companies").where("liPhoneNumber", "==", lead_object["phoneNumberTo"]).get()

            if company_snapshot:
                company_doc = company_snapshot[0]
                
                company_id = company_doc.id
                logger.info(f"Company id: {company_id}")
                owner_id = company_doc.to_dict().get("ownerId", "")

                company_doc.reference.update({"leads": firestore.ArrayUnion([lead_id])})
                leads_collection.document(lead_id).set({"leadOwnerId": owner_id}, merge=True)

                all_users = db.collection("users").get()
                user_data = None
                user_ref = None

                for doc in all_users:
                    if doc.id == owner_id:
                        user_data = doc.to_dict()
                        user_ref = doc.reference
                        break

                if user_ref:
                    agent_phone_number = user_data.get("phoneNumber")
                    user_ref.update({"leads": firestore.ArrayUnion([lead_id])})
                    logger.info("Lead ID added to owner's leads array")
                else:
                    logger.info(f"User not found with ownerId: {owner_id}")
                    serializer = ErrorResponseSerializer(
                        success = False,
                        error = "User not Found"
                    )
                    return response_structure(
                        serializer=serializer,
                        status_code=status.HTTP_400_BAD_REQUEST
                    )

                first_text = company_doc.to_dict().get("firstText","Default Text").replace("[-]", lead_object["firstName"])
                lead_object["firstText"] = first_text

                logger.info(f"Sending SMS to lead: {lead_object['phoneNumberFrom']}")
                try:
                    if not re.match(r"^(\+?\d{1,3}[-]?)?\(?\d{1,4}\)?[-]?\d{1,4}[-]?\d{1,4}$", lead_object["phoneNumberFrom"]):
                        serializer = ErrorResponseSerializer(
                            success = False,
                            error = "Invalid phone number format for liTextNumber."
                        )
                        return response_structure(
                            serializer=serializer,
                            status_code=status.HTTP_400_BAD_REQUEST
                        )
                    if not re.match(r"^(\+?\d{1,3}[-]?)?\(?\d{1,4}\)?[-]?\d{1,4}[-]?\d{1,4}$", company_doc.to_dict().get("liTextNumber","+12223334444")):
                        serializer = ErrorResponseSerializer(
                            success = False,
                            error = "Invalid phone number format for liTextNumber."
                        )
                        return response_structure(
                            serializer=serializer,
                            status_code=status.HTTP_400_BAD_REQUEST
                        )
                    await send_telnyx_message(lead_object["phoneNumberFrom"], first_text, Config.TELNYX_PHONE_NUMBER)
                    
                    logger.info("SMS sent to lead")
                except Exception as e:
                    logger.error(f"Error sending message to lead: {str(e)}",exc_info=True)
                    serializer = ErrorResponseSerializer(
                            success = False,
                            message = "Internal Server Error",
                            error = f"Error sending message to lead: {str(e)}"
                        )
                    return response_structure(
                        serializer=serializer,
                        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )

                if agent_phone_number:
                    try:
                        agent_message = f"Hi {lead_object['companyName']} Here! You have a new lead from your website: {lead_object['firstName']} {lead_object['lastName']}\n"
                        agent_message += f"Phone Number: {lead_object['phoneNumberFrom']}\nBudget: {lead_object['budget']}\nMove In Date: {lead_object['moveInDate']}\n"
                        agent_message += f"They heard of you from: {lead_object['howDidYouHear'] or 'an unknown source'}"
                        
                        await send_telnyx_message(agent_phone_number, agent_message, Config.TELNYX_PHONE_NUMBER)
                        logger.info("SMS sent to agent")
                    except Exception as e:
                        logger.error(f"Error sending message to agent: {str(e)}",exc_info=True)
                        serializer = ErrorResponseSerializer(
                            success = False,
                            message = "Internal Server Error",
                            error = f"Error sending message to agent: {str(e)}"
                        )
                        return response_structure(
                            serializer=serializer,
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
                        )
                else:
                    logger.info("Agent phone number is missing.")
                    serializer = ErrorResponseSerializer(
                        success = False,
                        error = "Agent phone number is missing."
                    )
                    return response_structure(
                        serializer=serializer,
                        status_code=status.HTTP_400_BAD_REQUEST
                    )

                conversation_ref = leads_collection.document(lead_id).collection("conversation")
                conversation_ref.add({
                    "automated": True,
                    "content": {"chatResponse": lead_object["firstText"]},
                    "direction": "outbound",
                    "timestamp": datetime.now().isoformat()
                })
            else:
                logger.info(f"Company not found for phone number: {lead_object['phoneNumberTo']}")
                serializer = ErrorResponseSerializer(
                    success = False,
                    error = "Company not Found"
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            serializer = SuccessResponseSerializer(
                success=True,
                message="Webhook received and processed"
            )
            return response_structure(
                serializer=serializer,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(str(e),exc_info=True)
            serializer = ErrorResponseSerializer(
                    success = False,
                    message = "Internal Server Error",
                    error = str(e)
                )
            return response_structure(
                serializer=serializer,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @classmethod
    async def inbound_call_ended(cls, payload: InboundCallEndedRequest):
        try:
            from_number = payload.from_phone.replace("\D", "")
            to_number = payload.to_phone.replace("\D", "")

            if not from_number or len(from_number) < 10:
                serializer = ErrorResponseSerializer(
                    success = False,
                    error = "Phone Number is required and must be at least 10 digits long"
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_400_BAD_REQUEST
                )
            if not to_number or len(to_number) < 10:
                serializer = ErrorResponseSerializer(
                    success = False,
                    error = "Company Number is required and must be at least 10 digits long"
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            analysis = payload.analysis
            lead_object = {
                "firstName": analysis.firstName,
                "lastName": analysis.lastName,
                "email": analysis.email,
                "phoneNumberFrom": format_phone_number(payload.from_phone),
                "phoneNumberTo": payload.to_phone,
                "moveInDate": analysis.moveInDate,
                "budget": analysis.budget,
                "desiredLocation": analysis.desiredLocation,
                "howDidYouHear": analysis.howDidYouHear,
                "transcriptSummary": payload.summary,
                "companyName": analysis.companyName,
                "beds": analysis.beds,
                "baths": analysis.baths,
                "subscribed": analysis.subscribed,
                "isInterested": True,
                "wantsToBook": True,
                "criminalHistory": analysis.criminalHistory,
                "needsApartment": True,
                "pathway": "website",
            }

            leads_collection = db.collection("leads")
            lead_id = None

            # Check for existing lead
            existing_leads = leads_collection.where("phoneNumber", "==", lead_object["phoneNumberFrom"]).stream()
            existing_leads = list(existing_leads)
            
            if existing_leads:
                lead_id = existing_leads[0].id
                leads_collection.document(lead_id).set(lead_object, merge=True)
            else:
                new_lead_ref = leads_collection.document()
                lead_id = new_lead_ref.id
                new_lead_ref.set({**lead_object, "dateCreated": datetime.now().isoformat()})
            
            # Query companies
            company_snapshot = db.collection("companies").where("liPhoneNumber", "==", lead_object["phoneNumberTo"]).stream()
            company_docs = list(company_snapshot)

            if company_docs:
                company_doc = company_docs[0]
                company_data = company_doc.to_dict()
                owner_id = company_data.get("ownerId")
                
                company_doc.reference.update({"leads": firestore.ArrayUnion([lead_id])})
                lead_object.update({
                    "liTextNumber": company_data.get("liTextNumber"),
                    "agentFAQNumber": company_data.get("agentFAQNumber"),
                    "companyName": company_data.get("name"),
                })

                # If owner exists, update their leads
                if owner_id:
                    user_doc = db.collection("users").document(owner_id).get()
                    if user_doc.exists:
                        user_data = user_doc.to_dict()
                        user_doc.reference.update({"leads": firestore.ArrayUnion([lead_id])})
                        
                        if lead_object["isInterested"]:
                            await send_telnyx_message(
                                lead_object["phoneNumberFrom"],
                                f"Hi {lead_object['firstName']}, it's Lucy with {lead_object['companyName']}! Great chatting with you earlier...",
                                Config.TELNYX_PHONE_NUMBER
                            )
                            await send_telnyx_message(
                                user_data["phoneNumber"],
                                f"Hi, it's Lucy from {lead_object['companyName']}! A new lead just called...",
                                Config.TELNYX_PHONE_NUMBER
                            )
                            serializer = SuccessResponseSerializer(
                                success=True,
                                message="Telnyx messages sent successfully"
                            )
                            return response_structure(
                                serializer=serializer,
                                status_code=status.HTTP_200_OK
                            )
                    else:
                        serializer = ErrorResponseSerializer(
                            success = False,
                            error = "Owner not found"
                        )
                        return response_structure(
                            serializer=serializer,
                            status_code=status.HTTP_404_NOT_FOUND
                        )
                else:
                    serializer = ErrorResponseSerializer(
                        success = False,
                        error = "Company has no ownerId field"
                    )
                    return response_structure(
                        serializer=serializer,
                        status_code=status.HTTP_404_NOT_FOUND
                    )
            else:
                serializer = ErrorResponseSerializer(
                    success = False,
                    error = f"No company found for phone number: {lead_object['phoneNumberTo']}"
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_404_NOT_FOUND
                )
            
            serializer = SuccessResponseSerializer(
                success=True,
                message="Lead successfully added"
            )
            return response_structure(
                serializer=serializer,
                status_code=status.HTTP_200_OK
            )
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}",exc_info=True)
            serializer = ErrorResponseSerializer(
                    success = False,
                    message = "Internal Server Error",
                    error = f"Error processing webhook: {str(e)}"
                )
            return response_structure(
                serializer=serializer,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
         
    
    