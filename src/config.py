from dotenv import load_dotenv
import os
import time
load_dotenv()

JELLYFIN_URL = os.getenv('JELLYFIN_URL').rstrip('/')
API_KEY = os.getenv('JELLYFIN_API_KEY')
TMDB_KEY = os.getenv('TMDB_API_KEY')
INCLUDE_EPISODES = os.getenv('INCLUDE_EPISODES', 'false').lower() in ['true', 'yes', '1', 'y']
ENABLE_WEBHOOK = os.getenv('ENABLE_WEBHOOK', 'false').lower() in ['true', 'yes', '1', 'y']
DISABLE_BLACKLIST = os.getenv('DISABLE_BLACKLIST', 'false').lower() in ['true', 'yes', '1', 'y']
RAW_TIMES = [time.strip() for time in os.getenv('SCHEDULED_TIMES', '').split(',') if time.strip()]
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 10))