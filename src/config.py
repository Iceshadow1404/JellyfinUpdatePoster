import json
import os
import sys
import shutil
from datetime import datetime

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT_DIR, 'backups')
SRC_DIR = os.path.join(ROOT_DIR, 'src')
MAX_BACKUPS = 3


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
    with open(config_path, 'w') as file:
        json.dump(default_config, file, indent=4)
    return config_path


def backup_file(file_path, backup_dir):
    if not os.path.exists(file_path):
        print(f"Warning: {file_path} does not exist. Skipping backup.")
        return

    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    filename = os.path.basename(file_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{filename[:-5]}_{timestamp}.json"
    backup_path = os.path.join(backup_dir, backup_filename)

    shutil.copy2(file_path, backup_path)

    backups = sorted([f for f in os.listdir(backup_dir) if f.startswith(filename[:-5])], reverse=True)
    for old_backup in backups[MAX_BACKUPS:]:
        os.remove(os.path.join(backup_dir, old_backup))


def backup_all():
    config_path = os.path.join(ROOT_DIR, 'config.json')
    raw_json_path = os.path.join(SRC_DIR, 'raw.json')
    sorted_series_path = os.path.join(SRC_DIR, 'sorted_series.json')

    backup_file(config_path, os.path.join(CONFIG_DIR, 'config'))
    backup_file(raw_json_path, os.path.join(CONFIG_DIR, 'raw'))
    backup_file(sorted_series_path, os.path.join(CONFIG_DIR, 'sorted_series'))


def load_config():
    config_path = os.path.join(ROOT_DIR, "config.json")
    if not os.path.exists(config_path):
        config_path = create_default_config()
        print("Please set your Settings in the config.json file in the root directory")
        sys.exit()

    with open(config_path, 'r') as file:
        config = json.load(file)

    backup_all()
    return config


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