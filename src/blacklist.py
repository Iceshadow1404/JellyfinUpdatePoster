from src.constants import BLACKLIST_FILENAME, OUTPUT_FILENAME
from src.logging import logging
from typing import Dict, List

import json
import os

logger = logging.getLogger(__name__)


def load_blacklist() -> Dict[str, List[str]]:
    with open(BLACKLIST_FILENAME, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_blacklist(blacklist: Dict[str, List[str]]):
    with open(BLACKLIST_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(blacklist, f, indent=4, ensure_ascii=False)


def add_to_blacklist(item_id: str, is_library: bool = False):
    blacklist = load_blacklist()
    key = 'libraries' if is_library else 'ids'
    if item_id not in blacklist[key]:
        blacklist[key].append(item_id)
        save_blacklist(blacklist)
        logger.info(f"Added {'library' if is_library else 'item'} with ID {item_id} to blacklist.")


def remove_from_blacklist(item_id: str, is_library: bool = False):
    blacklist = load_blacklist()
    key = 'libraries' if is_library else 'ids'
    if item_id in blacklist[key]:
        blacklist[key].remove(item_id)
        save_blacklist(blacklist)
        logger.info(f"Removed {'library' if is_library else 'item'} with ID {item_id} from blacklist.")


def is_blacklisted(item: Dict) -> bool:
    blacklist = load_blacklist()
    return (item['Id'] in blacklist['ids'] or
            item['LibraryId'] in blacklist['libraries'])


BLACKLIST = {
    "ids": ["EXAMPLE_ID"],               # Example IDs in the blacklist
    "libraries": ["EXAMPLE_LIBRARY_ID"]  # Example libraries in the blacklist
}


def update_output_file():
    """Updates the output file by removing blacklisted items."""
    # Check if the blacklist file exists
    if not os.path.exists(BLACKLIST_FILENAME):
        logger.warning(f"{BLACKLIST_FILENAME} does not exist. Creating example blacklist.")

        # Save the example blacklist in the specified format
        with open(BLACKLIST_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(BLACKLIST, f, indent=4, ensure_ascii=False)
        return  # Exit the function to ensure the output file is not updated

    # Load the current output file
    if not os.path.exists(OUTPUT_FILENAME):
        logger.warning(f"{OUTPUT_FILENAME} does not exist. No items to process.")
        return  # Exit if the output file does not exist

    with open(OUTPUT_FILENAME, 'r', encoding='utf-8') as f:
        items = json.load(f)

    # Load the blacklist from the file
    with open(BLACKLIST_FILENAME, 'r', encoding='utf-8') as f:
        blacklist = json.load(f)

    # Filter out blacklisted items
    filtered_items = [item for item in items if not is_blacklisted(item)]

    # Save the updated output file
    with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as f:
        json.dump(filtered_items, f, indent=4, ensure_ascii=False)

    if len(items) - len(filtered_items) != 0:
        logger.info(f"Updated {OUTPUT_FILENAME}. Removed {len(items) - len(filtered_items)} blacklisted items.")

# Example usage
if __name__ == "__main__":
    # Add a library to the blacklist
    add_to_blacklist('f4dda38cd82a250f2d1cb08db0c166cf', is_library=True)

    # Update the output file
    update_output_file()