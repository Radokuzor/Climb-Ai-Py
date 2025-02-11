import asyncio, telnyx, logging

logger = logging.getLogger(__name__)


async def send_telnyx_message(to, text, from_number):
    try:
        message = await asyncio.to_thread(
            telnyx.Message.create,
            from_=from_number,
            to=to,
            text=text
        )
        print("Message sent successfully:", message)
        return message
    except Exception as e:
        logger.error(str(e),exc_info=True)
        print("Error sending message:", e)
 