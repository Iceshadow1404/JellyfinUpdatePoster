from dotenv import load_dotenv
import os

load_dotenv()

JELLYFIN_URL = os.getenv('JELLYFIN_URL')
API_KEY = os.getenv('JELLYFIN_API_KEY')
TMDB_KEY = os.getenv('TMDB_API_KEY')
INCLUDE_EPISODES = os.getenv('include_episodes', 'false').lower() in ['true', 'yes', '1', 'y']