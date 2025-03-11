import sys
import requests
import json
import logging
import time
from datetime import datetime, timedelta
from time import sleep
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache

from src.constants import OUTPUT_FILENAME, LANGUAGE_DATA_FILENAME
from src.config import TMDB_KEY

logger = logging.getLogger(__name__)

# Base URLs for the TMDb API
BASE_URL_MOVIE = "https://api.themoviedb.org/3/movie/"
BASE_URL_TV = "https://api.themoviedb.org/3/tv/"
BASE_URL_COLLECTION = "https://api.themoviedb.org/3/collection/"
CACHE_EXPIRY_DAYS = 7  # Cache expiration period in days

# Session for reusing connections with expanded connection pool
from urllib3.util import Retry
from requests.adapters import HTTPAdapter

# Create session with larger connection pool and retry strategy
session = requests.Session()
# Configure max pool size to match our max concurrency plus a buffer
adapter = HTTPAdapter(
    pool_connections=30,  # Base connections in pool
    pool_maxsize=30,  # Max connections in pool
    max_retries=Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504]
    )
)
session.mount('https://', adapter)
session.mount('http://', adapter)


# Validate TMDB key once and cache the result
@lru_cache(maxsize=1)
def validate_tmdb_key():
    test_url = "https://api.themoviedb.org/3/authentication"
    params = {"api_key": TMDB_KEY}
    try:
        response = session.get(test_url, params=params)
        if response.status_code == 200:
            return True
        elif response.status_code == 401:
            logger.error("Invalid TMDB API key")
            return False
        else:
            logger.error(f"Unexpected response from TMDB API: {response.status_code}")
            return False
    except requests.exceptions.RequestException as e:
        logger.error(f"Error validating TMDB API key: {str(e)}")
        return False


# Fetch titles from TMDb with retry mechanism
def get_tmdb_titles(tmdb_id, media_type="movie", max_retries=3, retry_delay=2):
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

    # Create URLs upfront
    title_url = f"{base_url}{tmdb_id}?api_key={TMDB_KEY}&language=en-US"
    german_title_url = f"{base_url}{tmdb_id}?api_key={TMDB_KEY}&language=de-DE"
    alt_titles_url = f"{base_url}{tmdb_id}/alternative_titles?api_key={TMDB_KEY}" if media_type != "collection" else None

    # Function to make request with retries
    def make_request(url, retry_count=0):
        try:
            response = session.get(url)
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429 and retry_count < max_retries:  # Rate limit
                retry_after = int(response.headers.get("Retry-After", retry_delay))
                time.sleep(retry_after)
                return make_request(url, retry_count + 1)
            else:
                return None
        except requests.exceptions.RequestException:
            if retry_count < max_retries:
                time.sleep(retry_delay)
                return make_request(url, retry_count + 1)
            return None

    # Get main title
    title_data = make_request(title_url)
    if not title_data:
        logger.error(f"Error fetching main title for ID {tmdb_id}")
        return None

    main_title = title_data.get(title_field, "Unknown Title")

    # Get German title
    german_title_data = make_request(german_title_url)
    german_title = german_title_data.get(title_field,
                                         "Unknown German Title") if german_title_data else "Unknown German Title"

    # For collections, we don't need to fetch alternative titles
    if media_type == "collection":
        return [main_title, german_title]

    # Get alternative titles
    all_titles = [main_title, german_title]

    if alt_titles_url:
        alt_titles_data = make_request(alt_titles_url)
        if alt_titles_data:
            alternative_titles = [alt_title.get("title") for alt_title in alt_titles_data.get("titles", [])]
            all_titles.extend(alternative_titles)

    # Filter duplicates
    unique_titles = list(set(all_titles))
    return unique_titles


# Load already processed data with error handling
def load_processed_data():
    default_data = {
        'movies': {},
        'tv': {},
        'collections': {}
    }

    try:
        with open(LANGUAGE_DATA_FILENAME, "r", encoding="utf-8") as infile:
            data = json.load(infile)
            # Convert old format to new format if necessary
            if not isinstance(data, dict) or not all(key in data for key in ['movies', 'tv', 'collections']):
                return default_data
            # Remove global last_updated if it exists
            if 'last_updated' in data:
                del data['last_updated']
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        return default_data


# Save processed data to the file with the last update time
def save_processed_data(data):
    with open(LANGUAGE_DATA_FILENAME, "w", encoding="utf-8") as outfile:
        json.dump(data, outfile, indent=4, ensure_ascii=False)


# Check if the cache is still valid
def is_entry_cache_valid(entry):
    if 'last_updated' in entry:
        try:
            last_updated = datetime.fromisoformat(entry['last_updated'])
            return datetime.now() - last_updated < timedelta(days=CACHE_EXPIRY_DAYS)
        except (ValueError, TypeError):
            return False
    return False


# Clean up unused language entries
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
        media_type = item.get("Type", "").lower()
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


# Process a single item and fetch titles from TMDB
def process_item(item):
    tmdb_id = str(item.get("TMDbId")) if item.get("TMDbId") is not None else None
    media_type = item.get("Type", "").lower()
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
        return None

    entry_key = tmdb_id if tmdb_id else title

    # Return all necessary data about this item
    result = {
        'category': category,
        'entry_key': entry_key,
        'title': title,
        'originaltitle': originaltitle,
        'year': year,
        'type': media_type,
        'tmdb_id': tmdb_id,
        'titles': None
    }

    if tmdb_id:
        tmdb_type = "collection" if media_type == "boxset" else "tv" if media_type == "series" else "movie"
        titles = get_tmdb_titles(tmdb_id, tmdb_type)
        result['titles'] = titles if titles else []
    else:
        result['titles'] = [title]

    return result


# Main function with concurrent processing
def collect_titles():
    # Validate TMDB API key before proceeding
    if not validate_tmdb_key():
        logger.error("Failed to validate TMDB API key. Aborting title collection.")
        return False

    processed_data = load_processed_data()

    try:
        with open(OUTPUT_FILENAME, "r", encoding="utf-8") as file:
            media_items = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.error(f"Error loading media items: {str(e)}")
        return False

    # Clean up unused entries before processing new ones
    cleaned_data, removed_count = cleanup_unused_language_entries(media_items, processed_data)
    if removed_count > 0:
        logger.info(f"Removed {removed_count} unused language entries")
        processed_data = cleaned_data
        # Save the cleaned data immediately
        save_processed_data(processed_data)

    # Identify items that need updating
    items_to_process = []

    for item in media_items:
        tmdb_id = str(item.get("TMDbId")) if item.get("TMDbId") is not None else None
        media_type = item.get("Type", "").lower()

        if media_type not in ["series", "movie", "boxset"]:
            continue

        category = {"series": "tv", "movie": "movies", "boxset": "collections"}[media_type]
        entry_key = tmdb_id if tmdb_id else item.get("Name", "Unknown Title")

        # Check if entry needs updating
        if entry_key not in processed_data[category] or not is_entry_cache_valid(processed_data[category][entry_key]):
            items_to_process.append(item)

    needed_requests = len(items_to_process)

    if needed_requests == 0:
        logger.info("No items need updating, skipping API calls")
        return True

    logger.info(f"Found {len(media_items)} total items, {needed_requests} need TMDB API calls")

    # Process items concurrently - align with connection pool size
    max_workers = min(25, needed_requests)  # Limit maximum concurrent workers (slightly less than pool size)

    # Split items into batches for periodic saving
    batch_size = min(50, needed_requests)
    batches = [items_to_process[i:i + batch_size] for i in range(0, needed_requests, batch_size)]

    processed_count = 0
    for batch_idx, batch in enumerate(batches):
        results = []

        # Process batch concurrently
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_item = {executor.submit(process_item, item): item for item in batch}

            for future in future_to_item:
                try:
                    result = future.result()
                    if result:
                        results.append(result)
                        processed_count += 1
                        if processed_count % 5 == 0 or processed_count == needed_requests:  # Log every 5 items
                            logger.info(f"Processed TMDB API call {processed_count}/{needed_requests}")
                except Exception as e:
                    logger.error(f"Error processing item: {str(e)}")

        # Update processed data with results from this batch
        for result in results:
            category = result['category']
            entry_key = result['entry_key']

            entry_data = {
                "titles": result['titles'],
                "extracted_title": result['title'],
                "year": result['year'],
                "type": result['type'],
                "last_updated": datetime.now().isoformat()
            }

            if result['type'] != "boxset":
                entry_data["originaltitle"] = result['originaltitle']

            processed_data[category][entry_key] = entry_data

        # Save after each batch
        save_processed_data(processed_data)
        logger.info(f"Processed and saved batch {batch_idx + 1}/{len(batches)}")

    return True


if __name__ == "__main__":
    collect_titles()