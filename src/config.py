import json
import os
import sys

def create_default_config():
    default_config = {
        "jellyfin_url": "http://your-jellyfin-url",
        "api_key": "your-api-key",
        "tmdb_api_key": "your-tmdb-api-key",
        "use_tmdb": False
    }
    with open("config.json", 'w') as file:
        json.dump(default_config, file, indent=4)

def load_config():
    if not os.path.exists("config.json"):
        create_default_config()
        print("Please set your Settings in the config.json file")
        sys.exit()
    with open("config.json", 'r') as file:
        return json.load(file)

config = load_config()
JELLYFIN_URL = config["jellyfin_url"].rstrip('/')
API_KEY = config["api_key"]
TMDB_API_KEY = config["tmdb_api_key"]
USE_TMDB = config.get("use_tmdb", False)

# Export the config object
__all__ = ['config', 'JELLYFIN_URL', 'API_KEY', 'TMDB_API_KEY', 'USE_TMDB']
