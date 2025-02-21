from src.db.database import db
from src.utils.telnyx import send_telnyx_message
from src.config.config import Config

from google.cloud import firestore

async def create_or_update_lead(task_data, user_id, company_id):
    leads_collection = db.collection("leads")
    users_collection = db.collection("users")
    company_collection = db.collection("companies")

    lead_phone = task_data["phoneNumber"]

    print(f"Checking if lead exists for phone number: {lead_phone}")

    # Check if a lead with the same phone number exists
    existing_lead_query = leads_collection.where("phoneNumber", "==", lead_phone).stream()

    existing_leads = [doc for doc in existing_lead_query]

    if existing_leads:
        existing_lead_doc = existing_leads[0]
        lead_id = existing_lead_doc.id

        print(f"Lead already exists with ID: {lead_id}, updating the lead...")

        # Update lead with new data
        existing_lead_doc.reference.update({
            "firstName": task_data.get("firstName", existing_lead_doc.to_dict().get("firstName")),
            "lastName": task_data.get("lastName", existing_lead_doc.to_dict().get("lastName")),
            "email": task_data.get("email", existing_lead_doc.to_dict().get("email")),
            "status": task_data.get("status", existing_lead_doc.to_dict().get("status")),
            "leadOwnerId": user_id,
            "dateUpdated": firestore.SERVER_TIMESTAMP,
        })

        message = f"Lead with phone number {lead_phone} has been updated successfully."
    else:
        print(f"No lead found with phone number: {lead_phone}. Creating a new lead...")

        new_lead_doc_ref = leads_collection.add({
            "firstName": task_data["firstName"],
            "lastName": task_data["lastName"],
            "phoneNumber": lead_phone,
            "email": task_data.get("email"),
            "leadOwnerId": user_id,
            "status": task_data.get("status", "Unknown"),
            "dateCreated": firestore.SERVER_TIMESTAMP,
        })[1]

        lead_id = new_lead_doc_ref.id

        print(f"Lead created successfully with ID: {lead_id}")

        # Update user and company docs with the new lead ID
        users_collection.document(user_id).update({
            "leads": firestore.ArrayUnion([lead_id])
        })
        company_collection.document(company_id).update({
            "leads": firestore.ArrayUnion([lead_id])
        })

        message = f"New lead with phone number {lead_phone} has been created successfully."

    return message, lead_id


async def get_lead(task_data, recipient_phone_number):
    leads_collection = db.collection("leads")
    lead_phone = task_data["phoneNumber"]

    lead_query = leads_collection.where("phoneNumber", "==", lead_phone).stream()
    leads = [doc for doc in lead_query]

    if leads:
        lead = leads[0].to_dict()

        # Send lead details to recipient
        await send_telnyx_message(
            recipient_phone_number,
            f"Lead Details:\nName: {lead['firstName']} {lead['lastName']}\nPhone: {lead['phoneNumber']}\nEmail: {lead['email']}\nStatus: {lead['status']}",
            Config.TELNYX_PHONE_NUMBER
        )
        print("Lead details sent.")
    else:
        print(f"Lead not found for phone number: {lead_phone}")
        await send_telnyx_message(
            recipient_phone_number,
            f"No lead found with phone number: {lead_phone}",
            Config.TELNYX_PHONE_NUMBER
        )
        
  