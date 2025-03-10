import sys

import requests
import json
import logging
import time
from datetime import datetime, timedelta
from time import sleep

from src.constants import OUTPUT_FILENAME, LANGUAGE_DATA_FILENAME
from src.config import TMDB_KEY

logger = logging.getLogger(__name__)

# Base URLs for the TMDb API
BASE_URL_MOVIE = "https://api.themoviedb.org/3/movie/"
BASE_URL_TV = "https://api.themoviedb.org/3/tv/"
BASE_URL_COLLECTION = "https://api.themoviedb.org/3/collection/"
CACHE_EXPIRY_DAYS = 7  # Cache expiration period in days

def validate_tmdb_key():

    test_url = "https://api.themoviedb.org/3/authentication"
    params = {
        "api_key": TMDB_KEY
    }
    try:
        response = requests.get(test_url, params=params)
        if response.status_code == 200:
            return True
        elif response.status_code == 401:
            logger.error("Invalid TMDB API key")
            input()
        else:
            logger.error(f"Unexpected response from TMDB API: {response.status_code}")
            input()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error validating TMDB API key: {str(e)}")
        input()

# Function to fetch titles from TMDb
def get_tmdb_titles(tmdb_id, media_type="movie"):
    if media_type == "movie":
        base_url = BASE_URL_MOVIE
        title_field = "title"
    elif media_type == "tv":
        base_url = BASE_URL_TV
        title_field = "name"
    elif media_type == "collection":
        base_url = BASE_URL_COLLECTION
        title_field = "name"
    else:
        return None

    # Fetch the main title
    title_url = f"{base_url}{tmdb_id}?api_key={TMDB_KEY}&language=en-US"
    title_response = requests.get(title_url)

    if title_response.status_code != 200:
        logger.error(f"Error fetching main title for ID {tmdb_id}")
        return None

    title_data = title_response.json()
    main_title = title_data.get(title_field, "Unknown Title")

    # Fetch German title
    german_title_url = f"{base_url}{tmdb_id}?api_key={TMDB_KEY}&language=de-DE"
    german_title_response = requests.get(german_title_url)

    if german_title_response.status_code != 200:
        logger.error(f"Error fetching German title for ID {tmdb_id}")
        german_title = "Unknown German Title"
    else:
        german_title_data = german_title_response.json()
        german_title = german_title_data.get(title_field, "Unknown German Title")

    # For collections, we don't need to fetch alternative titles
    if media_type == "collection":
        return [main_title, german_title]

    # Fetch alternative titles
    alt_titles_url = f"{base_url}{tmdb_id}/alternative_titles?api_key={TMDB_KEY}"
    alt_titles_response = requests.get(alt_titles_url)

    if alt_titles_response.status_code != 200:
        logger.error(f"Error fetching alternative titles for ID {tmdb_id}")
        return None

    alt_titles_data = alt_titles_response.json()
    alternative_titles = [alt_title.get("title") for alt_title in alt_titles_data.get("titles", [])]

    # Combine all titles and filter duplicates
    all_titles = [main_title, german_title] + alternative_titles
    unique_titles = list(set(all_titles))  # Filter duplicates
    return unique_titles

# Load already processed data (if available)
def load_processed_data():
    try:
        with open(LANGUAGE_DATA_FILENAME, "r", encoding="utf-8") as infile:
            data = json.load(infile)
            # Convert old format to new format if necessary
            if not isinstance(data, dict) or not all(key in data for key in ['movies', 'tv', 'collections']):
                return {
                    'movies': {},
                    'tv': {},
                    'collections': {}
                }
            # Remove global last_updated if it exists
            if 'last_updated' in data:
                del data['last_updated']
            return data
    except FileNotFoundError:
        return {
            'movies': {},
            'tv': {},
            'collections': {}
        }

# Save processed data to the file with the last update time
def save_processed_data(data):
    with open(LANGUAGE_DATA_FILENAME, "w", encoding="utf-8") as outfile:
        json.dump(data, outfile, indent=4, ensure_ascii=False)

# Check if the cache is still valid
def is_entry_cache_valid(entry):
    if 'last_updated' in entry:
        last_updated = datetime.fromisoformat(entry['last_updated'])
        return datetime.now() - last_updated < timedelta(days=CACHE_EXPIRY_DAYS)
    return False


def cleanup_unused_language_entries(media_items, processed_data):
    # Create sets of current media IDs/titles for each category
    current_items = {
        'movies': set(),
        'tv': set(),
        'collections': set()
    }

    # Populate sets with current media IDs/titles
    for item in media_items:
        tmdb_id = str(item.get("TMDbId")) if item.get("TMDbId") is not None else None
        media_type = item.get("Type").lower()
        title = item.get("Name", "Unknown Title")

        if media_type == "series":
            category = "tv"
        elif media_type == "movie":
            category = "movies"
        elif media_type == "boxset":
            category = "collections"
        else:
            continue

        # Add either TMDb ID or title to the set
        current_items[category].add(tmdb_id if tmdb_id else title)

    # Create a copy of the processed data to modify
    cleaned_data = {
        'movies': {},
        'tv': {},
        'collections': {}
    }

    removed_count = 0

    # Compare and clean up entries
    for category in processed_data:
        for key in processed_data[category]:
            if key in current_items[category]:
                cleaned_data[category][key] = processed_data[category][key]
            else:
                removed_count += 1
                logger.info(f"Removing unused {category} entry: {key}")

    return cleaned_data, removed_count

# Main function
def collect_titles():
    # Validate TMDB API key before proceeding
    if not validate_tmdb_key():
        logger.error("Failed to validate TMDB API key. Aborting title collection.")
        return False

    processed_data = load_processed_data()

    with open(OUTPUT_FILENAME, "r", encoding="utf-8") as file:
        media_items = json.load(file)

    # Clean up unused entries before processing new ones
    cleaned_data, removed_count = cleanup_unused_language_entries(media_items, processed_data)
    if removed_count > 0:
        logger.info(f"Removed {removed_count} unused language entries")
        processed_data = cleaned_data
        # Save the cleaned data immediately
        save_processed_data(processed_data)

    needed_requests = 0
    for item in media_items:
        tmdb_id = str(item.get("TMDbId")) if item.get("TMDbId") is not None else None
        media_type = item.get("Type").lower()

        if media_type == "series":
            category = "tv"
        elif media_type == "movie":
            category = "movies"
        elif media_type == "boxset":
            category = "collections"
        else:
            continue

        # Check if entry needs updating
        if tmdb_id:
            if tmdb_id not in processed_data[category] or not is_entry_cache_valid(processed_data[category][tmdb_id]):
                needed_requests += 1
        else:
            title = item.get("Name", "Unknown Title")
            if title not in processed_data[category] or not is_entry_cache_valid(processed_data[category][title]):
                needed_requests += 1

    if int(needed_requests) != 0:
        logger.info(f"Found {len(media_items)} total items, {int(needed_requests)} need TMDB API calls")

    processed_count = 0
    for item in media_items:
        tmdb_id = str(item.get("TMDbId")) if item.get("TMDbId") is not None else None
        media_type = item.get("Type").lower()
        title = item.get("Name", "Unknown Title")
        originaltitle = item.get("OriginalTitle", "Unknown Title")
        year = item.get("Year", "Unknown Year")

        if media_type == "series":
            category = "tv"
        elif media_type == "movie":
            category = "movies"
        elif media_type == "boxset":
            category = "collections"
        else:
            logger.warning(f"Unknown media type: {media_type}")
            continue

        entry_key = tmdb_id if tmdb_id else title

        # Skip if entry exists and cache is still valid
        if entry_key in processed_data[category] and is_entry_cache_valid(processed_data[category][entry_key]):
            continue

        if tmdb_id:
            processed_count += 1
            logger.info(f"Processing TMDB API call {processed_count}/{needed_requests}")

            tmdb_type = "collection" if media_type == "boxset" else "tv" if media_type == "series" else "movie"
            titles = get_tmdb_titles(tmdb_id, tmdb_type)

            if titles:
                processed_data[category][tmdb_id] = {
                    "titles": titles,
                    "extracted_title": title,
                    "year": year,
                    "type": media_type,
                    "last_updated": datetime.now().isoformat()
                }

                if media_type != "boxset":
                    processed_data[category][tmdb_id]["originaltitle"] = originaltitle
            else:
                logger.warning(f"No titles found for ID {tmdb_id}. Saving with an empty array.")
                processed_data[category][tmdb_id] = {
                    "titles": [],
                    "extracted_title": title,
                    "originaltitle": originaltitle,
                    "year": year,
                    "type": media_type,
                    "last_updated": datetime.now().isoformat()
                }

            sleep(0.1)
        else:
            logger.info(f"Processing non-TMDB item: {title}")
            processed_data[category][title] = {
                "titles": [title],
                "extracted_title": title,
                "year": year,
                "type": media_type,
                "last_updated": datetime.now().isoformat()
            }

            if media_type != "boxset":
                processed_data[category][title]["originaltitle"] = originaltitle

        # Save after each update to prevent data loss
        save_processed_data(processed_data)


if __name__ == "__main__":
    collect_titles()