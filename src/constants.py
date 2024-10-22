import os
from pathlib import Path

RAW_COVER_DIR = Path('./RawCover')
COVER_DIR = Path('./Cover')
POSTER_DIR = COVER_DIR / 'Poster'
COLLECTIONS_DIR = COVER_DIR / 'Collections'
CONSUMED_DIR = Path('./Consumed')
REPLACED_DIR = Path('./Replaced')
NO_MATCH_FOLDER = './Cover/No-Match'

OUTPUT_FILENAME = './src/sorted_series.json'
BLACKLIST_FILENAME = './src/blacklist.json'
CONTENT_IDS_FILE = './src/content_id.json'
MISSING = "./missing_folders.txt"
EXTRA_FOLDER = "./extra_folders.txt"
LANGUAGE_DATA_FILENAME = "./src/language.json"
MEDIUX_FILE = './mediux.txt'