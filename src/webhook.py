import requests
from src.utils import *


def webhook(HA_WEBHOOK_URL, HA_WEBHOOK_ID):
    try:
        webhook_url = f"{HA_WEBHOOK_URL}/api/webhook/{HA_WEBHOOK_ID}"
        response = requests.post(webhook_url)
        response.raise_for_status()
        if response.status_code == 200:
            log("Webhook sent successfully!")
        else:
            print(f"Statuscode: {response.status_code}")

    except requests.exceptions.RequestException as e:
        print(f"Error while sending webhook: {e}")
