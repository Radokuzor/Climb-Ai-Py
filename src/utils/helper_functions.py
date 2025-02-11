import sendgrid, pytz, re

from src.config.config import Config
from src.utils.telnyx import send_telnyx_message
from src.db.database import db

from sendgrid.helpers.mail import Mail, Email, To, Content

from datetime import datetime

async def send_email(to_email: str, subject: str, text: str):
    if not to_email or not subject or not text:
        raise ValueError("Missing required parameters: to_email, subject, and text are required")

    sg = sendgrid.SendGridAPIClient(api_key=Config.SENDGRID_API_KEY)
    from_email = Email("hannahai.tech@gmail.com", "Hannah AI")
    to_email = To(to_email)
    content = Content("text/plain", text)
    mail = Mail(from_email, to_email, subject, content)

    try:
        response = sg.client.mail.send.post(request_body=mail.get())
        print("SendGrid Response:", response.status_code, response.headers)
        return {"success": True, "message": "Email sent successfully", "response": response.status_code}
    except Exception as e:
        print("SendGrid Error:", str(e))
        return {"success": False, "message": "Error sending email", "error": str(e)}

def convert_central_time_to_utc(central_time_string):
    if not central_time_string:
        raise ValueError("Input string is required")

    try:
        central = pytz.timezone("America/Chicago")
        utc = pytz.utc

        date = datetime.fromisoformat(central_time_string).replace(tzinfo=central)
        return date.astimezone(utc).isoformat()
    except Exception as e:
        raise ValueError(f"Failed to convert time: {str(e)}")

def add_minutes_to_iso_string(iso_string, minutes_to_add):
    date = datetime.fromisoformat(iso_string)
    date = date + datetime.timedelta(minutes=minutes_to_add)
    return date.isoformat()

def format_to_readable_date(iso_date):
    date = datetime.fromisoformat(iso_date)
    return date.astimezone(pytz.timezone("America/Chicago")).strftime("%B %d, %Y %I:%M %p CST")


async def handle_guest_card(task_data, from_phone_number):
    leads_collection = db.collection("leads")
    lead_phone = task_data["phoneNumber"]

    existing_lead_query = leads_collection.where("phoneNumber", "==", lead_phone).stream()
    leads = [doc for doc in existing_lead_query]

    if leads:
        existing_lead_doc = leads[0]

        try:
            email_result = await send_email(
                task_data["email"],
                "guestcard",
                f"Guest Card Info\nClient Name: {existing_lead_doc.to_dict()['firstName']} {existing_lead_doc.to_dict()['lastName']}\n"
                f"Client Email: {existing_lead_doc.to_dict()['email']}\nClient Phone Number: {lead_phone}"
            )

            response_message = "Your guest card has been successfully emailed! ✅" if email_result["success"] else \
                "Sorry, there was a problem sending your guest card email. ❌"

            await send_telnyx_message(from_phone_number, response_message, Config.TELNYX_PHONE_NUMBER)
        except Exception as email_error:
            print("Email sending failed:", email_error)
            await send_telnyx_message(from_phone_number, "Sorry, there was a system error.", Config.TELNYX_PHONE_NUMBER)
    else:
        await send_telnyx_message(from_phone_number, f"I wasn't able to find a lead with {lead_phone}", Config.TELNYX_PHONE_NUMBER)



def format_phone_number(phone: str) -> str:
    if not phone:
        return ""

    # Remove all non-numeric characters except the plus sign for international numbers
    cleaned_phone = re.sub(r"[^0-9+]", "", phone)

    # Add +1 if it's missing and the number is 10 digits long
    if not cleaned_phone.startswith("+1") and len(cleaned_phone) == 10:
        cleaned_phone = f"+1{cleaned_phone}"

    # Ensure the phone number is in the correct length (11 for US +1 country code)
    if cleaned_phone.startswith("+1") and len(cleaned_phone) != 12:
        return cleaned_phone  # Just return the formatted number without raising an error

    return cleaned_phone


