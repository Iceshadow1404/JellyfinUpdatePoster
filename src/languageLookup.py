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
            return json.load(infile)  # Load processed TMDb IDs and titles
    except FileNotFoundError:
        return {}  # Return an empty dictionary if the file doesn't exist

# Save processed data to the file with the last update time
def save_processed_data(data):
    data['last_updated'] = datetime.now().isoformat()  # Save the current time as last updated
    with open(LANGUAGE_DATA_FILENAME, "w", encoding="utf-8") as outfile:
        json.dump(data, outfile, indent=4, ensure_ascii=False)

# Check if the cache is still valid
def is_cache_valid(data):
    if 'last_updated' in data:
        last_updated = datetime.fromisoformat(data['last_updated'])
        return datetime.now() - last_updated < timedelta(days=CACHE_EXPIRY_DAYS)
    return False

# Main function
def collect_titles():
    # Load already processed titles to avoid re-fetching
    processed_data = load_processed_data()

    # Refresh cache if it's older than the defined period
    if not is_cache_valid(processed_data):
        logger.warning("Cache is outdated, refreshing data...")
        processed_data = {}  # Reset processed data to fetch new entries

    with open(OUTPUT_FILENAME, "r", encoding="utf-8") as file:
        media_items = json.load(file)  # Assuming the file contains a list of JSON objects

    total_items = len(media_items)
    count = 0  # Counter for processed (including skipped) items

    for item in media_items:
        tmdb_id = str(item.get("TMDbId")) if item.get("TMDbId") is not None else None
        media_type = item.get("Type").lower()  # "movie", "series", or "boxset"
        title = item.get("Name", "Unknown Title")
        originaltitle = item.get("OriginalTitle", "Unknown Title")
        year = item.get("Year", "Unknown Year")

        if tmdb_id in processed_data:
            count += 1  # Increment the counter for skipped items
            continue

        count += 1
        logger.info(f"Remaining TMDB API calls: {total_items - count}")

        if tmdb_id:
            # Fetch TMDb data (movie, series, or collection)
            if media_type == "boxset":
                titles = get_tmdb_titles(tmdb_id, "collection")
            else:
                titles = get_tmdb_titles(tmdb_id, media_type)

            if titles:
                processed_data[tmdb_id] = {
                    "titles": titles,
                    "extracted_title": title,
                    "year": year,
                    "type": media_type
                }

                # Add originaltitle only if media_type is not "boxset"
                if media_type != "boxset":
                    processed_data[tmdb_id]["originaltitle"] = originaltitle
            else:
                # Log an error if there are no titles available
                logger.warning(f"No titles found for ID {tmdb_id}. Saving with an empty array.")
                processed_data[tmdb_id] = {
                    "titles": [],
                    "extracted_title": title,
                    "originaltitle": originaltitle,
                    "year": year,
                    "type": media_type
                }

            # Pause briefly (reduced to 0.1 seconds)
            sleep(0.1)
        else:
            # Handle non-TMDB boxsets or items without TMDb ID
            logger.info(f"Processing non-TMDB item: {title}")
            processed_data[title] = {
                "titles": [title],
                "extracted_title": title,
                "year": year,
                "type": media_type
            }

            # Don't add originaltitle for boxsets
            if media_type != "boxset":
                processed_data[title]["originaltitle"] = originaltitle

        # Save the progress after each item
        save_processed_data(processed_data)

if __name__ == "__main__":
    collect_titles()