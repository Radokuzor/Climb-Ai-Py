from src.utils.ai_handler import handle_ai_response
from src.utils.response import (
    ErrorResponseSerializer,
    SuccessResponseSerializer,
    response_structure
)
from src.db.database import db

from .serializer import EmailScrapingRequest

from fastapi import status

import logging


logger = logging.getLogger(__name__)


class EmailController:
    
    @classmethod
    async def email_scraping(cls,payload:EmailScrapingRequest):
        try:
            print("Hi")
            company_ref = db.collection("companies").where("email", "==", payload.fromEmail)
            
            company_snapshot = company_ref.get()
            print("Hello")
            
            if company_snapshot:
                print("Hello")
                
                comapny_data = company_snapshot[0]
                
                response_data = await handle_ai_response(payload.phoneNumber, comapny_data.to_dict().get('liTextNumber'), payload.task)
                
                serializer = SuccessResponseSerializer(
                    success=True,
                    status_code=status.HTTP_200_OK,
                    data= response_data
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_200_OK
                )
                
            else:
                print("Hello1")
                serializer = SuccessResponseSerializer(
                    success=True,
                    message="Company not found",
                    status_code=status.HTTP_404_NOT_FOUND
                )
                return response_structure(
                    serializer=serializer,
                    status_code=status.HTTP_200_OK
                )
            
        except Exception as e:
            logger.error(f"Error processing Email Scraping: {str(e)}",exc_info=True)
            serializer = ErrorResponseSerializer(
                success = False,
                message = "Internal Server Error",
                error = f"Error processing Email Scraping: {str(e)}"
            )
            return response_structure(
                serializer=serializer,
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )