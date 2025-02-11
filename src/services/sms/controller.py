from src.utils.ai_handler import send_text_to_chatgpt_for_agent
from src.utils.leads import create_or_update_lead, get_lead
from src.utils.telnyx import send_telnyx_message
from src.utils.event import create_or_update_event
from src.utils.helper_functions import handle_guest_card, format_phone_number

from src.db.database import db
from src.config.config import Config

from fastapi import HTTPException

from google.cloud import firestore

from datetime import datetime

import logging, re


logger = logging.getLogger(__name__)

# {
#     "from": {
#         "phone_number": "+12223334445"
#     },
#     "to": [
#         {
#             "phone_number": "+18177655422"
#         }
#     ],
#     "text": "Hello, this is a normal message from user side! Ravi Test"
# }


class SMSController:
    
    @classmethod
    async def handle_ai_response_for_agent(cls,payload: dict):
        try:
            from_phone_number = payload.get("from").get("phone_number")
            to_phone_number = payload.get("to")[0].get("phone_number")
            message = payload.get("text")

            if not from_phone_number or not to_phone_number or not message:
                raise HTTPException(status_code=400, detail="Missing required fields: from_phoneNumber, toPhoneNumber, or message.")

            if len(from_phone_number) < 10 or len(to_phone_number) < 10:
                raise HTTPException(status_code=400, detail="All fields must have at least 10 characters.")

            if from_phone_number == to_phone_number:
                raise HTTPException(status_code=400, detail="From and To numbers are the same.")

            if from_phone_number in ["+17373093928", Config.TELNYX_PHONE_NUMBER]:
                raise HTTPException(status_code=400, detail="SMS from this number is blocked.")

            company_ref = db.collection("companies").where("agentFAQNumber", "==", to_phone_number).get()
            user_ref = db.collection("users").where("phoneNumber", "==", from_phone_number).get()

            if not company_ref or not user_ref:
                return {"success": False, "message": "You are not registered with an agency.", "error": "User or agent not found"}
            
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

            print("ai_response : ",ai_response)
            
            if "error" in ai_response or "warning" in ai_response:
                return {"success": False, "message": "Error processing request.", "error": ai_response.get("error", ai_response.get("warning"))}

            # Save inbound and AI response
            conversation_ref.add({"content": message, "timestamp": datetime.now().isoformat(), "direction": "inbound"})
            conversation_ref.add({"content": ai_response, "timestamp": datetime.now().isoformat(), "direction": "outbound"})

            task_data = ai_response.get("taskData", {})
            user_object = ai_response.get("userObject", {})

            if task_data.get("work"):
                action = task_data.get("action", "").lower()
                if action in ["create lead", "update lead"]:
                    lead_message = await create_or_update_lead(task_data, user_id, company_id)
                    await send_telnyx_message("+19036467318", lead_message, Config.TELNYX_PHONE_NUMBER)
                elif action == "get lead":
                    await get_lead(task_data, user_object.get("phoneNumber"))
                elif action == "guest card":
                    await handle_guest_card(task_data, from_phone_number)
                elif action in ["create event", "update event"]:
                    event_message = await create_or_update_event(task_data, user_id, from_phone_number)
                    await send_telnyx_message("+19036467318", event_message, Config.TELNYX_PHONE_NUMBER)
                else:
                    print(f"Unknown action: {action}")
            else:
                await send_telnyx_message("+19036467318", ai_response.get("chatResponse", ""), Config.TELNYX_PHONE_NUMBER)

            return {"success": True, "response": ai_response.get("chatResponse", "")}

        except Exception as e:
            logger.error(str(e),exc_info=True)
            return {"success": False, "message": "Internal Server Error", "error": str(e)}
    
    @classmethod
    async def sms_outbound(cls,payload: dict):
        logger.info("SMS sent webhook triggered")
        leads_collection = db.collection("leads")
        lead_object = {}
        agent_phone_number = None
        lead_id = None

        try:
            
            lead_object = {
                "firstName": payload.get("firstName", ""),
                "lastName": payload.get("lastName", ""),
                "email": payload.get("email", ""),
                "phoneNumberFrom": format_phone_number(payload.get("phone", "")) or "",
                "phoneNumberTo": payload.get("phoneNumberTo", ""),
                "moveInDate": payload.get("moveInDate", ""),
                "budget": payload.get("budget", ""),
                "desiredLocation": payload.get("desiredLocation", ""),
                "howDidYouHear": payload.get("howDidYouHear", ""),
                "companyName": payload.get("companyName", ""),
                "bedsBath": payload.get("bedsBath", ""),
                "subscribed": payload.get("subscribed", ""),
                "criminalHistory": payload.get("criminalHistory", ""),
                "needsApartment": True,
                "pathway": "website",
                "appointmentTime": "",
                "transcriptSummary": ""
            }

            if not lead_object["phoneNumberFrom"] or not lead_object["phoneNumberTo"] or \
            len(lead_object["phoneNumberFrom"]) < 10 or len(lead_object["phoneNumberTo"]) < 10:
                raise HTTPException(status_code=400, detail="Phone number is required and must be at least 10 characters long.")

            logger.info("Processed Lead Object Data:", lead_object)

            existing_lead_query = leads_collection.where("phoneNumber", "==", lead_object["phoneNumberFrom"]).get()

            if existing_lead_query:
                logger.info("Lead already exists with phone", lead_object["phoneNumberFrom"])
                existing_lead_doc = existing_lead_query[0]
                lead_id = existing_lead_doc.id
                existing_lead_doc.reference.set(lead_object, merge=True)
            else:
                logger.info("Creating new lead with phone", lead_object["phoneNumberFrom"])
                new_lead_doc_ref = leads_collection.document()
                lead_id = new_lead_doc_ref.id
                new_lead_doc_ref.set(lead_object)

            company_snapshot = db.collection("companies").where("liPhoneNumber", "==", lead_object["phoneNumberTo"]).get()

            if company_snapshot:
                company_doc = company_snapshot[0]
                
                company_id = company_doc.id
                print(f"\n\n company_id {company_id} \n\n")
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
                    logger.info("User not found with ownerId:", owner_id)

                first_text = company_doc.to_dict().get("firstText","Default Text").replace("[-]", lead_object["firstName"])
                lead_object["firstText"] = first_text

                logger.info("Sending SMS to lead:", lead_object["phoneNumberFrom"])
                try:
                    if not re.match(r"^(\+?\d{1,3}[-]?)?\(?\d{1,4}\)?[-]?\d{1,4}[-]?\d{1,4}$", lead_object["phoneNumberFrom"]):
                        raise ValueError("Invalid phone number format for the lead.")
                    if not re.match(r"^(\+?\d{1,3}[-]?)?\(?\d{1,4}\)?[-]?\d{1,4}[-]?\d{1,4}$", company_doc.to_dict().get("liTextNumber","+12223334444")):
                        raise ValueError("Invalid phone number format for liTextNumber.")
                    await send_telnyx_message(lead_object["phoneNumberFrom"], first_text, Config.TELNYX_PHONE_NUMBER)
                    # await send_telnyx_message("+19036467318", first_text, Config.TELNYX_PHONE_NUMBER)
                    logger.info("SMS sent to lead")
                except Exception as e:
                    logger.error(f"Error sending message to lead: {str(e)}",exc_info=True)

                if agent_phone_number:
                    try:
                        agent_message = f"Hi {lead_object['companyName']} Here! You have a new lead from your website: {lead_object['firstName']} {lead_object['lastName']}\n"
                        agent_message += f"Phone Number: {lead_object['phoneNumberFrom']}\nBudget: {lead_object['budget']}\nMove In Date: {lead_object['moveInDate']}\n"
                        agent_message += f"They heard of you from: {lead_object['howDidYouHear'] or 'an unknown source'}"
                        # await send_telnyx_message(agent_phone_number, agent_message, lead_object.get("liTextNumber"))
                        await send_telnyx_message(agent_phone_number, agent_message, Config.TELNYX_PHONE_NUMBER)
                        logger.info("SMS sent to agent")
                    except Exception as e:
                        logger.error(f"Error sending message to agent: {str(e)}",exc_info=True)
                else:
                    logger.info("Agent phone number is missing.")

                conversation_ref = leads_collection.document(lead_id).collection("conversation")
                conversation_ref.add({
                    "automated": True,
                    "content": {"chatResponse": lead_object["firstText"]},
                    "direction": "outbound",
                    "timestamp": datetime.now().isoformat()
                })
            else:
                logger.info("Company not found for phone number:", lead_object["phoneNumberTo"])

            return {"message": "Webhook received and processed"}
        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Error processing webhook")
