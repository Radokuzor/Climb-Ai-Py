import os
from dotenv import load_dotenv
from openai import AsyncOpenAI

# from decouple import config
load_dotenv()
class Config:
    CHATGPT_API_KEY = "sk-proj-tFWKwLGsXZyCUCvOhrJmT3BlbkFJffaMLC8a10zlqEVrdKfy"#os.getenv('CHATGPT_API_KEY')
    SENDGRID_API_KEY = "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"#os.getenv('SENDGRID_API_KEY')
    TELNYX_PHONE_NUMBER = "+17373014328"#os.getenv('TELNYX_PHONE_NUMBER')
    
client = AsyncOpenAI(api_key=Config.CHATGPT_API_KEY)
