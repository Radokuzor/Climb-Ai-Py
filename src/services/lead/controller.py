from fastapi import HTTPException

from src.utils.ai_handler import handle_ai_response

import asyncio

previous_sms = {}

class LeadController:
    
    @classmethod
    async def receive_lead_confirmation(cls,payload):
        try:
            from_phone_number = payload.get("from").get("phone_number")
            to_phone_number = payload.get("to")[0].get("phone_number")
            message = payload.get("text")

            if not from_phone_number or not to_phone_number or not message:
                raise HTTPException(status_code=400, detail="Missing required fields: fromPhoneNumber, toPhoneNumber, or message.")

            if len(from_phone_number) < 10 or len(to_phone_number) < 10:
                raise HTTPException(status_code=400, detail="All fields must have at least 10 characters.")

            # Check for duplicate message
            if from_phone_number in previous_sms and previous_sms[from_phone_number]["message"] == message:
                raise HTTPException(status_code=400, detail="Duplicate message detected.")

            # Ignore messages from the same number
            if from_phone_number == to_phone_number:
                raise HTTPException(status_code=400, detail="From and To numbers are the same.")

            if from_phone_number in ["+17373014328", "+17209535293", "+17373093928"]:
                raise HTTPException(status_code=400, detail="From and To numbers are the same.")

            print("BEGIN ACTION: Inbound text received from:", from_phone_number)

            # Store message in dictionary
            previous_sms[from_phone_number] = {
                "message": message,
                "timestamp": asyncio.get_event_loop().time(),  # Store timestamp in seconds
            }

            # Call AI response handler
            response_data = await handle_ai_response(from_phone_number, to_phone_number, message)
            return response_data

        except KeyError:
            raise HTTPException(status_code=400, detail="Invalid payload format.")