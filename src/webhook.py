from src.utils import *
import aiohttp


async def webhook(HA_WEBHOOK_URL, HA_WEBHOOK_ID):
    try:
        webhook_url = f"{HA_WEBHOOK_URL}/api/webhook/{HA_WEBHOOK_ID}"
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_url) as response:
                if response.status == 200:
                    log("Webhook sent successfully!")
                else:
                    print(f"Statuscode: {response.status}")

    except aiohttp.ClientError as e:
        print(f"Error while sending webhook: {e}")