import os
from dotenv import load_dotenv
from openai import AsyncOpenAI

# from decouple import config
load_dotenv()
class Config:
    CHATGPT_API_KEY = os.getenv('CHATGPT_API_KEY')
    SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
    TELNYX_PHONE_NUMBER = os.getenv('TELNYX_PHONE_NUMBER')
    
client = AsyncOpenAI(api_key=Config.CHATGPT_API_KEY)
