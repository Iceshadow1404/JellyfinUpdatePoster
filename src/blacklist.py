from src.constants import BLACKLIST_FILENAME, OUTPUT_FILENAME
from src.logging import logging
from src.config import DISABLE_BLACKLIST
from typing import Dict, List

import json
import os

logger = logging.getLogger(__name__)


def load_blacklist() -> Dict[str, List[str]]:
    # If blacklist is disabled, return an empty blacklist
    if DISABLE_BLACKLIST:
        return {"ids": [], "libraries": []}

    with open(BLACKLIST_FILENAME, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_blacklist(blacklist: Dict[str, List[str]]):
    # Only save if blacklist is not disabled
    if not DISABLE_BLACKLIST:
        with open(BLACKLIST_FILENAME, 'w', encoding='utf-8') as f:
            json.dump(blacklist, f, indent=4, ensure_ascii=False)


def add_to_blacklist(item_id: str, is_library: bool = False):
    # Only add if blacklist is not disabled
    if DISABLE_BLACKLIST:
        return

    blacklist = load_blacklist()
    key = 'libraries' if is_library else 'ids'
    if item_id not in blacklist[key]:
        blacklist[key].append(item_id)
        save_blacklist(blacklist)
        logger.info(f"Added {'library' if is_library else 'item'} with ID {item_id} to blacklist.")


def remove_from_blacklist(item_id: str, is_library: bool = False):
    # Only remove if blacklist is not disabled
    if DISABLE_BLACKLIST:
        return

    blacklist = load_blacklist()
    key = 'libraries' if is_library else 'ids'
    if item_id in blacklist[key]:
        blacklist[key].remove(item_id)
        save_blacklist(blacklist)
        logger.info(f"Removed {'library' if is_library else 'item'} with ID {item_id} from blacklist.")


def is_blacklisted(item: Dict) -> bool:
    # If blacklist is disabled, no items are blacklisted
    if DISABLE_BLACKLIST:
        return False

    blacklist = load_blacklist()
    return (item['Id'] in blacklist['ids'] or
            item['LibraryId'] in blacklist['libraries'])


BLACKLIST = {
    "ids": ["EXAMPLE_ID"],  # Example IDs in the blacklist
    "libraries": ["EXAMPLE_LIBRARY_ID"]  # Example libraries in the blacklist
}


def update_output_file():
    cleanup_blacklist()
    """Updates the output file by removing blacklisted items."""
    # If blacklist is disabled, skip processing
    if DISABLE_BLACKLIST:
        logger.info("Blacklist is disabled. Skipping output file update.")
        return

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


def cleanup_blacklist():
    """
    Checks the blacklist and removes IDs that no longer exist in the output file.
    Distinguishes between regular IDs and Library IDs.
    """
    # If blacklist is disabled, skip cleanup
    if DISABLE_BLACKLIST:
        logger.info("Blacklist is disabled. Skipping blacklist cleanup.")
        return

    # Check if required files exist
    if not os.path.exists(BLACKLIST_FILENAME) or not os.path.exists(OUTPUT_FILENAME):
        logger.warning("Blacklist or output file doesn't exist. Cleanup not possible.")
        return

    # Define protected example IDs that should never be removed
    PROTECTED_IDS = {"EXAMPLE_ID"}
    PROTECTED_LIBRARY_IDS = {"EXAMPLE_LIBRARY_ID"}

    # Load blacklist and output file
    blacklist = load_blacklist()
    with open(OUTPUT_FILENAME, 'r', encoding='utf-8') as f:
        output_items = json.load(f)

    # Collect all IDs and Library IDs from output file
    existing_ids = set(item['Id'] for item in output_items)
    existing_library_ids = set(item['LibraryId'] for item in output_items)

    # Find IDs to remove, excluding protected IDs
    ids_to_remove = [item_id for item_id in blacklist['ids']
                     if item_id not in existing_ids and item_id not in PROTECTED_IDS]
    libraries_to_remove = [lib_id for lib_id in blacklist['libraries']
                           if lib_id not in existing_library_ids and lib_id not in PROTECTED_LIBRARY_IDS]

    # Remove non-existent IDs
    for item_id in ids_to_remove:
        blacklist['ids'].remove(item_id)
        logger.info(f"Removed ID {item_id} from blacklist - no longer exists in jellyfin")

    # Remove non-existent Library IDs
    for lib_id in libraries_to_remove:
        blacklist['libraries'].remove(lib_id)
        logger.info(f"Removed Library ID {lib_id} from blacklist - no longer exists in jellyfin")

    # Save updated blacklist
    save_blacklist(blacklist)

    # Log summary
    total_removed = len(ids_to_remove) + len(libraries_to_remove)
    if total_removed > 0:
        logger.info(f"Blacklist cleaned up: removed {len(ids_to_remove)} IDs and {len(libraries_to_remove)} "
                    f"Library IDs")
    else:
        logger.info("No outdated IDs found in blacklist")


# Example usage
if __name__ == "__main__":
    # Add a library to the blacklist
    add_to_blacklist('f4dda38cd82a250f2d1cb08db0c166cf', is_library=True)

    # Update the output file
    update_output_file()