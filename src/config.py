import os
import sys
from dotenv import load_dotenv
import logging

load_dotenv()

env_vars = {
    'JELLYFIN_URL': os.getenv('JELLYFIN_URL'),
    'JELLYFIN_API_KEY': os.getenv('JELLYFIN_API_KEY'),
    'TMDB_API_KEY': os.getenv('TMDB_API_KEY')
}

# Check if any are missing
missing = [key for key, value in env_vars.items() if not value]
if missing:
    for key in missing:
        logging.error(f"Please set the {key} in a .env file or as an environment variable (e.g. in Docker).")
    sys.exit(1)

JELLYFIN_URL = env_vars['JELLYFIN_URL'].rstrip('/')
API_KEY = env_vars['JELLYFIN_API_KEY']
TMDB_KEY = env_vars['TMDB_API_KEY']

INCLUDE_EPISODES = os.getenv('INCLUDE_EPISODES', 'false').lower() in ['true', 'yes', '1', 'y']
ENABLE_WEBHOOK = os.getenv('ENABLE_WEBHOOK', 'false').lower() in ['true', 'yes', '1', 'y']
DISABLE_BLACKLIST = os.getenv('DISABLE_BLACKLIST', 'false').lower() in ['true', 'yes', '1', 'y']
RAW_TIMES = [time.strip() for time in os.getenv('SCHEDULED_TIMES', '').split(',') if time.strip()]
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 10))
# When enabled, folders will be named using the path from Jellyfin instead of "Name (Year)" scheme
USE_PATH_FOR_FOLDERS = os.getenv('USE_PATH_FOR_FOLDERS', 'true').lower() in ['true', 'yes', '1', 'y']