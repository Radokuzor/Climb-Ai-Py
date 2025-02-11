from fastapi import APIRouter,Query
from src.services.default.controller import DefaultController
from src.services.sms.controller import SMSController
from src.services.lead.controller import LeadController

router = APIRouter()

@router.get("/")
async def get_company_availability(message: str = Query(None)):
    """Fetch company availability based on the given phone number."""
    print(f"Received message: {message}")

    # Call the company availability function with a fixed phone number
    phone_number = "+18177655422"

    return await DefaultController.get_company_availability(phone_number, force_fetch=True)

@router.post("/inbound-sms/agent-faq")
async def inbound_sms_for_agent(payload: dict):
    """
        - Accepts:  
            - User's phone number.  
            - Company's phone number.  
            - Message from the user.  
        - Stores the message and the corresponding chat response in the `users` collection under `conversation`. 
    """
    return await SMSController.handle_ai_response_for_agent(payload)

@router.post("/api/receive-lead-confirmation")
async def receive_lead_confirmation(payload: dict):
    """
        - Accepts:  
            - User's phone number.  
            - Company's phone number.  
            - Message from the user.  
        - Stores the message and the corresponding chat response in the `leads` collection under `conversation`.
    """
    return await LeadController.receive_lead_confirmation(payload)

@router.post("/sms-outbound")
async def sms_outbound(payload: dict):
    """
        - Accepts:  
            - User details: `firstName`, `lastName`, `email`, `phone`.  
            - Recipient details: `phoneNumberTo`.  
            - Additional information: `moveInDate`, `budget`, etc.  
        - Stores the details and the conversation in the `leads` collection.  
        - Matches data with the corresponding Firebase collection.
    """
    return await SMSController.sms_outbound(payload)