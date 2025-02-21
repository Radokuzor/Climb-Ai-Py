from fastapi import APIRouter

from src.services.default.controller import DefaultController

from src.services.sms.controller import SMSController
from src.services.sms.serializer import (
    InboundSmsForAgentRequest,
    SmsOutboundRequest,
    InboundCallEndedRequest
)

from src.services.lead.controller import LeadController

from src.services.email.controller import EmailController
from src.services.email.serializer import EmailScrapingRequest

router = APIRouter()

@router.get("/")
async def get_company_availability(message:str = None):
    """Fetch company availability based on the given phone number."""
    print(f"Received message: {message}")

    # Call the company availability function with a fixed phone number
    phone_number = "+18177655422"

    return await DefaultController.get_company_availability(phone_number, force_fetch=True)

@router.post("/inbound-sms/agent-faq")
async def inbound_sms_for_agent(payload: InboundSmsForAgentRequest):
    """
        - Accepts:  
            - User's phone number.  
            - Company's phone number.  
            - Message from the user.  
        - Stores the message and the corresponding chat response in the `users` collection under `conversation`. 
    """
    return await SMSController.handle_ai_response_for_agent(payload)

@router.post("/api/receive-lead-confirmation")
async def receive_lead_confirmation(payload: InboundSmsForAgentRequest):
    """
        - Accepts:  
            - User's phone number.  
            - Company's phone number.  
            - Message from the user.  
        - Stores the message and the corresponding chat response in the `leads` collection under `conversation`.
    """
    return await LeadController.receive_lead_confirmation(payload)

@router.post("/sms-outbound")
async def sms_outbound(payload: SmsOutboundRequest):
    """
        - Accepts:  
            - User details: `firstName`, `lastName`, `email`, `phone`.  
            - Recipient details: `phoneNumberTo`.  
            - Additional information: `moveInDate`, `budget`, etc.  
        - Stores the details and the conversation in the `leads` collection.  
        - Matches data with the corresponding Firebase collection.
    """
    return await SMSController.sms_outbound(payload)

@router.post("/inbound/call-ended")
async def inbound_call_ended(payload: InboundCallEndedRequest):
    """
        - Accepts:  
        - Call data: `from`, `to`, `firstName`, `lastName`, `email`, etc.  
        - Verifies the provided data against the Firebase collection.  
        - Stores the data in the `leads` collection.  
        - Links the `leadsId` to the `company` collection.
    """
    return await SMSController.inbound_call_ended(payload)

@router.post("/email-scraping")
async def email_scraping(payload: EmailScrapingRequest):
    """
        Processes an email scraping request.

        - **Accepts:**  
        - A JSON payload containing an `email` field.  

        - **Functionality:**  
        - Validates the provided email.  
        - Sends the email content to OpenAI for processing.  
        - Parses the assistant’s response and returns structured data.  

        - **Returns:**  
        - A JSON response with extracted details if successful.  
        - An error message if the process fails.
    """
    return await EmailController.email_scraping(payload)
