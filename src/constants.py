import os
from pathlib import Path

RAW_COVER_DIR = Path('./RawCover')
COVER_DIR = Path('./Cover')
POSTER_DIR = COVER_DIR / 'Poster'
COLLECTIONS_DIR = COVER_DIR / 'Collections'
CONSUMED_DIR = Path('./Consumed')
REPLACED_DIR = Path('./Replaced')

OUTPUT_FILENAME = './src/sorted_series.json'
RAW_FILENAME = './src/raw.json'
ID_CACHE_FILENAME = './src/id_cache.json'
PROCESSING_LOG = "./processing.log"
MISSING = "./missing_folders.txt"
EXTRA_FOLDER = "./extra_folders.txt"
MEDIUX_FILE = "./mediux.txt"
BLACKLIST_FILE = './src/blacklisted_ids.json'