import json

def load_config():
    with open("config.json", 'r') as file:
        return json.load(file)

config = load_config()
JELLYFIN_URL = config["jellyfin_url"]
API_KEY = config["api_key"]