import json
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def create_default_config():
    default_config = {
        "jellyfin_url": "http://your-jellyfin-url",
        "api_key": "your-api-key",
        "tmdb_api_key": "your-tmdb-api-key",
        "use_tmdb": False,
        "use_HA_webhook": False,
        "HA_webhook_id": "",
        "HA_webhook_url": ""

    }
    config_path = os.path.join(ROOT_DIR, 'config.json')
    with open("config.json", 'w') as file:
        json.dump(default_config, file, indent=4)

def load_config():
    config_path = os.path.join(ROOT_DIR, "config.json")
    if not os.path.exists(config_path):
        create_default_config()
        print("Please set your Settings in the config.json file in the root directory")
        sys.exit()
    with open(config_path, 'r') as file:
        return json.load(file)

config = load_config()
JELLYFIN_URL = config["jellyfin_url"].rstrip('/')
API_KEY = config["api_key"]
TMDB_API_KEY = config["tmdb_api_key"]
USE_TMDB = config.get("use_tmdb", False)
USE_HA = config.get("use_HA_webhook")
HA_WEBHOOK_ID = config.get("HA_webhook_id")
HA_WEBHOOK_URL = config.get("HA_webhook_url")


# Export the config object
__all__ = ['config', 'JELLYFIN_URL', 'API_KEY', 'TMDB_API_KEY', 'USE_TMDB', 'USE_HA', 'HA_WEBHOOK_ID', 'HA_WEBHOOK_URL']
