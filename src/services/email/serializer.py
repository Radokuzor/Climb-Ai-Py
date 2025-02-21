from pydantic import BaseModel, EmailStr

class EmailScrapingRequest(BaseModel):
    firstName: str
    fromEmail: EmailStr
    lastName: str
    phoneNumber: str
    task: str
