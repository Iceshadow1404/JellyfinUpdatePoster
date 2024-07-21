# config.py
import json

def load_config():
    with open("config.json", 'r') as file:
        return json.load(file)

config = load_config()
JELLYFIN_URL = config["jellyfin_url"]
API_KEY = config["api_key"]
TMDB_API_KEY = config["tmdb_api_key"]
USE_TMDB = config.get("use_tmdb", True)

# Export the config object
__all__ = ['config', 'JELLYFIN_URL', 'API_KEY', 'TMDB_API_KEY', 'USE_TMDB']