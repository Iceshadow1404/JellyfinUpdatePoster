import json
import os
import sys
import shutil

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ROOT_DIR, 'backups')
SRC_DIR = os.path.join(ROOT_DIR, 'src')
MAX_BACKUPS = 5


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


def backup_files(files_to_backup):
    if not os.path.exists(CONFIG_DIR):
        os.makedirs(CONFIG_DIR)

    # Get existing backup folders
    existing_backups = [d for d in os.listdir(CONFIG_DIR) if os.path.isdir(os.path.join(CONFIG_DIR, d)) and d.isdigit()]
    existing_backups.sort(key=lambda x: int(x))

    # Remove oldest backup if we already have MAX_BACKUPS
    if len(existing_backups) >= MAX_BACKUPS:
        oldest_backup = os.path.join(CONFIG_DIR, existing_backups[0])
        shutil.rmtree(oldest_backup)
        existing_backups.pop(0)

    # Shift existing backups
    for i in range(len(existing_backups), 0, -1):
        old_path = os.path.join(CONFIG_DIR, str(i))
        new_path = os.path.join(CONFIG_DIR, str(i + 1))
        if os.path.exists(old_path):
            if os.path.exists(new_path):
                shutil.rmtree(new_path)
            os.rename(old_path, new_path)

    # Create new backup folder
    new_backup_dir = os.path.join(CONFIG_DIR, '1')
    if os.path.exists(new_backup_dir):
        shutil.rmtree(new_backup_dir)
    os.makedirs(new_backup_dir)

    # Backup files
    for file_path in files_to_backup:
        if os.path.exists(file_path):
            shutil.copy2(file_path, new_backup_dir)
        else:
            print(f"Warning: {file_path} does not exist. Skipping backup.")

    print(f"New backup created in folder: {new_backup_dir}")

def backup_all():
    files_to_backup = [
        os.path.join(ROOT_DIR, 'config.json'),
        os.path.join(SRC_DIR, 'raw.json'),
        os.path.join(SRC_DIR, 'sorted_series.json')
    ]
    backup_files(files_to_backup)

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