import json
import os

from src.logging import logging
from src.constants import CONTENT_IDS_FILE
from src.getIDs import get_jellyfin_content

logger = logging.getLogger(__name__)

def get_content_ids(items):
    """Extract IDs from items, filtering only Seasons and Movies"""
    return sorted([
        item['Id']
        for item in items
        if item['Type'] in ['Season', 'Movie', 'BoxSet']
    ])

def load_content_ids():
    if os.path.exists(CONTENT_IDS_FILE):
        try:
            with open(CONTENT_IDS_FILE, 'r') as f:
                content = f.read()
                if content.strip():  # Check if file is not empty
                    return json.loads(content)
                else:
                    logger.info("Content IDs file is empty. Treating as no previous content.")
                    return []
        except json.JSONDecodeError:
            logger.warning("Error decoding Content IDs file. Treating as no previous content.")
            return []
    else:
        logger.warning("Content IDs file does not exist. Treating as no previous content.")
        return []

def save_content_ids(ids):
    with open(CONTENT_IDS_FILE, 'w') as f:
        json.dump(ids, f)


def check_jellyfin_content():
    try:
        old_ids = load_content_ids()

        # Fetch new content
        items = get_jellyfin_content(silent=True)
        if items:
            new_ids = get_content_ids(items)

            if old_ids != new_ids:
                logging.info('New content detected in Jellyfin!')

                logging.info(f'Old IDs: {len(old_ids)}')
                logging.info(f'New IDs: {len(new_ids)}')

                # Save new content right away when detected
                processed_items = get_jellyfin_content()

                if processed_items:
                    save_content_ids(new_ids)
                    return True
                return False
            else:
                logging.info('No changes detected in Jellyfin content.')
                return False
        else:
            logging.warning("No data retrieved from Jellyfin.")
            return False

    except Exception as e:
        logging.error(f"An error occurred while checking Jellyfin content: {e}")
        return False

if __name__ == "__main__":
    check_jellyfin_content()