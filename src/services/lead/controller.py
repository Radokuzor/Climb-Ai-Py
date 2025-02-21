from fastapi import status

from src.utils.ai_handler import handle_ai_response
from src.utils.response import (
    ErrorResponseSerializer,
    SuccessResponseSerializer,
    response_structure
)

import asyncio,logging


logger = logging.getLogger(__name__)

previous_sms = {}


class LeadController:
    
    @classmethod
    async def receive_lead_confirmation(cls,payload):
        try:
            from_phone_number = payload.from_phone.phone_number
            to_phone_number = payload.to_phone[0].phone_number
            message = payload.text

            if not from_phone_number or not to_phone_number or not message:
                serializer = ErrorResponseSerializer(
                    success = False,
                    error = "Missing required fields: fromPhoneNumber, toPhoneNumber, or message."
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

            # Check for duplicate message
            if from_phone_number in previous_sms and previous_sms[from_phone_number]["message"] == message:
                serializer = ErrorResponseSerializer(
                    success = False,
                    error = "Duplicate message detected."
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            # Ignore messages from the same number
            if from_phone_number == to_phone_number:
                serializer = ErrorResponseSerializer(
                    success = False,
                    error = "From and To numbers are the same."
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            if from_phone_number in ["+17373014328", "+17209535293", "+17373093928"]:
                serializer = ErrorResponseSerializer(
                    success = False,
                    error = "From and To numbers are the same."
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_400_BAD_REQUEST
                )

            logger.info(f"BEGIN ACTION: Inbound text received from: {from_phone_number}")

            # Store message in dictionary
            previous_sms[from_phone_number] = {
                "message": message,
                "timestamp": asyncio.get_event_loop().time(),  # Store timestamp in seconds
            }

            # Call AI response handler
            response_data = await handle_ai_response(from_phone_number, to_phone_number, message)
            
            serializer = SuccessResponseSerializer(
                success=True,
                data=response_data
            )
            return response_structure(
                serializer=serializer,
                status_code=status.HTTP_200_OK
            )

        except KeyError:
            serializer = ErrorResponseSerializer(
                success = False,
                error = "Invalid payload format."
            )
            return response_structure(
                serializer=serializer,
                status_code=status.HTTP_400_BAD_REQUEST
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