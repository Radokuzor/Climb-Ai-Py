from fastapi import HTTPException
from google.cloud import firestore
from typing import Dict

from src.config.config import client, Config
from src.db.database import db
from src.services.default.controller import DefaultController
from src.utils.telnyx import send_telnyx_message

from datetime import datetime

import asyncio, json, logging

logger = logging.getLogger(__name__)


async def handle_ai_response(from_phone_number: str, to_phone_number: str, inbound_message: str):
    leads_collection = db.collection("leads")
    users_collection = db.collection("users")
    events_collection = db.collection("events")

    lead_data, lead_id = None, None

    # Check if the lead exists
    try:
        existing_lead_query = leads_collection.where("phoneNumber", "==", from_phone_number).stream()
        existing_leads = list(existing_lead_query)
        
        if existing_leads:
            existing_lead_doc = existing_leads[0]
            lead_data = existing_lead_doc.to_dict()
            lead_id = existing_lead_doc.id
            print(f"Lead already exists with ID: {lead_id}")
        else:
            new_lead_ref, _ = leads_collection.add({
                "phoneNumber": from_phone_number,
                "companyPhoneNumber": to_phone_number,
                "dateCreated": datetime.now().isoformat(),
                "pathway": "sms",
            })
            lead_id = new_lead_ref.id
            new_lead_doc = new_lead_ref.get()
            lead_data = new_lead_doc.to_dict()
            print(f"Lead created with ID: {lead_id}")
    except Exception as error:
        print(f"Error fetching or creating lead: {error}")
        raise HTTPException(status_code=500, detail="Error fetching or creating lead")

    conversation_ref = leads_collection.document(lead_id).collection("conversation")

    # Associate lead with the company
    try:
        company_snapshot = db.collection("companies").where("liTextNumber", "==", to_phone_number).stream()
        company_docs = list(company_snapshot)

        if company_docs:
            company_doc = company_docs[0]
            owner_id = company_doc.to_dict().get("ownerId")
            print(f"Company found with ID: {company_doc.id}")

            company_id = company_doc.id
            db.collection("companies").document(company_id).update({
                "leads": firestore.ArrayUnion([lead_id]),
            })

            if owner_id:
                user_ref = db.collection("users").document(owner_id)
                user_doc = user_ref.get()
                if user_doc.exists:
                    user_ref.update({
                        "leads": firestore.ArrayUnion([lead_id]),
                    })
                    print(f"Lead {lead_id} associated with user {owner_id}")
                else:
                    print(f"User with ID {owner_id} not found.")
            else:
                print(f"No ownerId found for company {company_id}")
        else:
            print(f"No company found with phone number: {to_phone_number}")
            return f"No company found with phone number: {to_phone_number}"

    except Exception as error:
        print(f"Error associating lead with company: {error}")
        raise HTTPException(status_code=500, detail="Error associating lead with company")

    # Retrieve and concatenate previous conversation
    conversation = ""
    try:
        conversation_snapshot = conversation_ref.order_by("timestamp").stream()
        conversation = "\n".join(
            [str(doc.to_dict().get("content", "")) for doc in conversation_snapshot]
        )
        
        print(f"Current conversation: {conversation}")
    except Exception as error:
        print(f"Error retrieving conversation: {error}")
        raise HTTPException(status_code=500, detail="Error retrieving conversation")

    # Send conversation to OpenAI and get AI response
    ai_response = None
    try:
        if to_phone_number == "+17209535293":
            ai_response = await send_text_to_chatgpt_for_apt_amigo(conversation, inbound_message, from_phone_number, to_phone_number, str(lead_data))
        elif to_phone_number == "+12816260629":
            ai_response = await send_text_to_chatgpt_for_pathfinders(conversation, inbound_message, from_phone_number, to_phone_number, str(lead_data))
        elif lead_data["pathway"] == "call":
            ai_response = await send_text_to_chatgpt_for_lead_details_conf(conversation, inbound_message, from_phone_number, to_phone_number, str(lead_data))
        elif lead_data["pathway"] == "sms":
            ai_response = await send_text_to_chatgpt_for_conversation_sms(conversation, inbound_message, from_phone_number, to_phone_number, str(lead_data))
        elif lead_data["pathway"] == "website":
            ai_response = await send_text_to_chatgpt_for_appointment_setting(conversation, inbound_message, from_phone_number, to_phone_number, str(lead_data))
        print(f"AI response received: {ai_response}")
    except Exception as error:
        print(f"Error getting AI response: {error}")
        raise HTTPException(status_code=500, detail="Error getting AI response")

    # Save inbound and AI response to conversation
    try:
        conversation_ref.add({
            "content": inbound_message,
            "timestamp": datetime.now().isoformat(),
            "direction": "inbound",
        })
        conversation_ref.add({
            "content": ai_response.get("chatResponse"),
            "timestamp": datetime.now().isoformat(),
            "direction": "outbound",
        })
        print("Conversation saved successfully.")
    except Exception as error:
        print(f"Error saving conversation: {error}")
        raise HTTPException(status_code=500, detail="Error saving conversation")

    # Send AI response to user
    try:
        await send_telnyx_message(from_phone_number, ai_response["chatResponse"], Config.TELNYX_PHONE_NUMBER)
        print("AI response sent to user.")
    except Exception as error:
        print(f"Error sending message to user: {error}")
        raise HTTPException(status_code=500, detail="Error sending message to user")

    # Prepare and update lead data
    lead_update_data = {
        "toPhoneNumber": to_phone_number,
        "lastResponse": datetime.now().isoformat(),
        "leadOwnerId": company_doc.to_dict().get("ownerId"),
        "leadCreator": company_doc.id,
        **extract_user_data(ai_response),
    }

    try:
        if lead_update_data:
            leads_collection.document(lead_id).set(lead_update_data, merge=True)
            print("Lead information updated successfully in Firebase.")
    except Exception as error:
        print(f"Error updating lead data: {error}")
        raise HTTPException(status_code=500, detail="Error updating lead data")

    return ai_response.get("chatResponse")

def extract_user_data(ai_response: Dict) -> Dict:
    user_data = ai_response.get("userData", {})
    lead_update_data = {}

    if user_data:
        fields = [
            "firstName", "lastName", "email", "phone", "beds", "baths", "budget",
            "moveInDate", "desiredLocation", "goalNumber", "reasonForMove", "notes",
            "backgroundQualify", "mustHaves", "status", "criminalHistory", "isInterested", 
            "needsApartment", "appointmentTime"
        ]
        for field in fields:
            if field in user_data:
                lead_update_data[field] = user_data[field]
        if user_data.get("appointmentTime"):
            lead_update_data["appointmentTime"] = ""

    return lead_update_data


async def send_text_to_chatgpt_for_apt_amigo(conversation, new_message, lead_phone_number, company_phone_number, leads_object):
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Prepare the content for the thread
    content = f"""This is the previous conversation: {conversation}.
    Observe the leads data here: {leads_object}.
    Look at the new inbound message which you will be responding to: [{new_message}].
    Here's today's date: {today}. Be mindful of this when booking the appointment.
    User's phone number: {lead_phone_number}"""

    # Create the thread with the content
    thread = await client.beta.threads.create(
        messages=[{
            "role": "user",
            "content": content
        }]
    )
    
    # Start the run for the thread
    run = await client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id="asst_qMCh6j8JTeiTdlsiC1RRhKdy",
    )

    # Polling the run status until completion
    while True:
        run_status = await client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if run_status.status in ["completed", "failed", "cancelled"]:
            break
        await asyncio.sleep(1)

    # Fetch the response from the assistant
    messages = await client.beta.threads.messages.list(thread_id=thread.id)
    if messages.data:
        response_text = messages.data[0].content[0].text.value
        return json.loads(response_text)

    return {
        'chatResponse': "No response from assistant.",
        'taskData': {},
        'userObject': {'phoneNumber': lead_phone_number, 'companyPhoneNumber': company_phone_number}
    }


async def send_text_to_chatgpt_for_agent(conversation, new_message, lead_phone_number, company_phone_number):
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    thread = await client.beta.threads.create(
        messages=[
            {
                "role": "user",
                "content": f"""This is the previous conversation: {conversation}.
                Look at the new inbound message which you will be responding to: [{new_message}]
                Here's today's date: {today}. Be mindful of this when setting dates.
                User's phone number: {lead_phone_number}
                Company's phone number: {company_phone_number}"""
            }
        ]
    )
    
    run = await client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id="asst_P7t29BxJnGqzeJLXnE6Cpc5o",
    )
    
    while True:
        run_status = await client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if run_status.status in ["completed", "failed", "cancelled"]:
            break
        await asyncio.sleep(1)

    messages = await client.beta.threads.messages.list(thread_id=thread.id)
    if messages.data:        
        response_text = messages.data[0].content[0].text.value 
        return json.loads(response_text)
    
    return {
        'chatResponse': "No response from assistant.",
        'taskData': {},
        'userObject': {'phoneNumber': f'{lead_phone_number}', 'companyPhoneNumber': f'{company_phone_number}'}
    }


async def send_text_to_chatgpt_for_pathfinders(conversation, new_message, lead_phone_number, company_phone_number, leads_object):
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Prepare the content for the thread
    content = f"""This is the previous conversation: {conversation}.
    Observe the leads data here: {leads_object}.
    Look at the new inbound message which you will be responding to: [{new_message}].
    Here's today's date: {today}. Be mindful of this when conversing.
    User's phone number: {lead_phone_number}"""

    # Create the thread with the content
    thread = await client.beta.threads.create(
        messages=[{
            "role": "user",
            "content": content
        }]
    )
    
    # Start the run for the thread
    run = await client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id="asst_ZwRXQCVdDiykfTj7p53kdjNB",
    )

    # Polling the run status until completion
    while True:
        run_status = await client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if run_status.status in ["completed", "failed", "cancelled"]:
            break
        await asyncio.sleep(1)

    # Fetch the response from the assistant
    messages = await client.beta.threads.messages.list(thread_id=thread.id)
    if messages.data:
        response_text = messages.data[0].content[0].text.value
        return json.loads(response_text)

    return {
        'chatResponse': "No response from assistant.",
        'taskData': {},
        'userObject': {'phoneNumber': lead_phone_number, 'companyPhoneNumber': company_phone_number}
    }


async def send_text_to_chatgpt_for_conversation_sms(conversation, new_message, lead_phone_number, company_phone_number, leads_object):
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Get company availability (assuming you have this function implemented elsewhere)
    availability = await DefaultController.get_company_availability(company_phone_number, True)
    availed_string = json.dumps(availability, indent=2)

    # Prepare the content for the thread
    content = f"""This is the previous conversation: {conversation}.
    Observe the leads data here: {leads_object}.
    Look at the new inbound message which you will be responding to: [{new_message}].
    Here's today's date: {today}. Be mindful of this when conversing.
    User's phone number: {lead_phone_number}"""

    # Create the thread with the content
    thread = await client.beta.threads.create(
        messages=[{
            "role": "user",
            "content": content
        }]
    )
    
    # Start the run for the thread
    run = await client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id="asst_AcjjAxUTmAlMUisRIj33hCGz",
    )

    # Polling the run status until completion
    while True:
        run_status = await client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if run_status.status in ["completed", "failed", "cancelled"]:
            break
        await asyncio.sleep(1)

    # Fetch the response from the assistant
    messages = await client.beta.threads.messages.list(thread_id=thread.id)
    if messages.data:
        response_text = messages.data[0].content[0].text.value
        return json.loads(response_text)

    return {
        'chatResponse': "No response from assistant.",
        'taskData': {},
        'userObject': {'phoneNumber': lead_phone_number, 'companyPhoneNumber': company_phone_number}
    }


async def send_text_to_chatgpt_for_appointment_setting(conversation, new_message, lead_phone_number, company_phone_number, leads_object):
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Get company availability (assuming you have this function implemented elsewhere)
    # availability = await get_company_availability(company_phone_number, True)
    # availed_string = json.dumps(availability, indent=2)

    # Prepare the content for the thread
    content = f"""This is the previous conversation: {conversation}.
    Observe the leads data here: {leads_object}.
    Look at the new inbound message which you will be responding to: [{new_message}].
    Here's today's date: {today}. Be mindful of this when conversing.
    User's phone number: {lead_phone_number}"""

    # Create the thread with the content
    thread = await client.beta.threads.create(
        messages=[{
            "role": "user",
            "content": content
        }]
    )
    
    # Start the run for the thread
    run = await client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id="asst_SR6AfOGkXgCF8a9pkpkqT0OC",
    )

    # Polling the run status until completion
    while True:
        run_status = await client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if run_status.status in ["completed", "failed", "cancelled"]:
            break
        await asyncio.sleep(1)

    # Fetch the response from the assistant
    messages = await client.beta.threads.messages.list(thread_id=thread.id)
    if messages.data:
        response_text = messages.data[0].content[0].text.value
        return json.loads(response_text)

    return {
        'chatResponse': "No response from assistant.",
        'taskData': {},
        'userObject': {'phoneNumber': lead_phone_number, 'companyPhoneNumber': company_phone_number}
    }


async def send_text_to_chatgpt_for_lead_details_conf(conversation, new_message, lead_phone_number, company_phone_number, leads_object):
    today = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    availability = await DefaultController.get_company_availability(company_phone_number, True)

    # Uncomment and update the availability mapping if needed
    # updated_availability = [{
    #     "title": appointment["title"],
    #     "start": convert_utc_to_central_time_for_avail(appointment["start"]),
    #     "end": convert_utc_to_central_time_for_avail(appointment["end"]),
    # } for appointment in availability]

    availed_string = json.dumps(availability, indent=2)

    # Prepare the content for the thread
    content = f"""This is the previous conversation: {conversation}.
    Observe the leads data here: {leads_object}.
    Look at the new inbound message which you will be responding to: [{new_message}].
    Here's today's date: {today}. Be mindful of this when booking the appointment.
    User's phone number: {lead_phone_number}.
    Here's a list of available time slots: {availed_string}"""

    # Create the thread with the content
    thread = await client.beta.threads.create(
        messages=[{
            "role": "user",
            "content": content
        }]
    )

    # Start the run for the thread
    run = await client.beta.threads.runs.create(
        thread_id=thread.id,
        assistant_id="asst_gGp5KGyeslXh42Zq4SMDyoXc",
    )

    # Polling the run status until completion
    while True:
        run_status = await client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
        if run_status.status in ["completed", "failed", "cancelled"]:
            break
        await asyncio.sleep(1)

    # Fetch the response from the assistant
    messages = await client.beta.threads.messages.list(thread_id=thread.id)
    if messages.data:
        response_text = messages.data[0].content[0].text.value
        return json.loads(response_text)

    return {
        'chatResponse': "No response from assistant.",
        'taskData': {},
        'userObject': {'phoneNumber': lead_phone_number, 'companyPhoneNumber': company_phone_number}
    }


async def send_text_to_chatgpt_for_email_scraping(email: str):
    if not email or not isinstance(email, str) or not email.strip():
        logger.info("Invalid email provided for scraping.")
        return False, "Invalid email input. Please provide a valid email string."

    logger.info(f"Sending email: {email} to chat for scraping")

    try:
        # Create a new thread
        thread = await client.beta.threads.create(
            messages=[{"role": "user", "content": email}]
        )

        # Start the assistant run
        run = await client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id="asst_96fZpFCfX8Tj8QieTXySrlgr"
        )

        # Stream the response
        while True:
            run_status = await client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run_status.status in ["completed", "failed", "cancelled"]:
                break
            await asyncio.sleep(1)  # Wait before checking again

        messages = await client.beta.threads.messages.list(thread_id=thread.id)

        if messages.data:
            
            last_message = messages.data[0]  # Assuming the last message is the assistant's response
            if last_message.content and last_message.content[0].type == "text":
                try:
                    data = json.loads(last_message.content[0].text.value)
                    return True, data
                except json.JSONDecodeError:
                    logger.error("Error parsing assistant response.")
                    return False, "Error parsing assistant response."
        
        logger.error("Empty or unexpected response from assistant.")
        return False, "Empty or unexpected response from assistant."
    
    except Exception as e:
        logger.error(f"Error creating thread: {e}",exc_info=True)
        return False, "Failed to create thread for email scraping."
