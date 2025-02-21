from pydantic import BaseModel, EmailStr
from typing import Optional, List

class PhoneNumber(BaseModel):
    phone_number : str

class InboundSmsForAgentRequest(BaseModel):
    from_phone : PhoneNumber
    to_phone : List[PhoneNumber]
    text : str

class SmsOutboundRequest(BaseModel):
    firstName: Optional[str] = ""
    lastName: Optional[str] = ""
    email: Optional[EmailStr] = ""
    phone: Optional[str] = ""
    phoneNumberTo: Optional[str] = ""
    moveInDate: Optional[str] = ""
    budget: Optional[str] = ""
    desiredLocation: Optional[str] = ""
    howDidYouHear: Optional[str] = ""
    companyName: Optional[str] = ""
    bedsBath: Optional[str] = ""
    subscribed: Optional[str] = ""
    criminalHistory: Optional[str] = ""


class AnalysisSerializer(BaseModel):
    firstName: Optional[str] = ""
    lastName: Optional[str] = ""
    email: Optional[EmailStr] = ""
    moveInDate: Optional[str] = ""
    budget: Optional[str] = ""
    desiredLocation: Optional[str] = ""
    howDidYouHear: Optional[str] = ""
    beds: Optional[int] = None
    baths: Optional[int] = None
    wants_to_book_appointment: bool
    criminalHistory: Optional[str] = ""
    isInterested: bool
    subscribed: Optional[str] = ""
    companyName: Optional[str] = ""
    

class InboundCallEndedRequest(BaseModel):
    from_phone: str
    to_phone: str
    summary: str
    analysis: AnalysisSerializer
    