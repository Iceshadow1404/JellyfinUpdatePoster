# Auto Update Posters for Jellyfin
This tool converts .zip files from https://theposterdb.com/ into dedicated folders and updates the posters in Jellyfin.

## Requirements: Python 3.11 or newer

Steps to install:

1. Clone this repository with `git clone https://github.com/Iceshadow1404/JellyfinUpdatePoster/`.
2. Navigate into the folder with `cd JellyfinUpdatePoster`.
3. Install all the required packages with `pip install Pillow requests watchdog`.
4. Add your Jellyfin IP:PORT and API key to config.json.
5. Start the script with `python main.py`.
6. ## The Script might crash on the first launch but these folders should have been created:

- Cover
  - Poster
  - Collections
- Consumed
- RawCover
- Replaced

7.  Start the script again with `python main.py`.
8. Add Files to the RawCover Folder. 


Check the root folder for a newly created file named missing_folders.txt. You can refer to this file to see the exact names of the required folders. Note that not all folders need to be present for the script to function correctly.

## Features:

Converts and renames .zip and Single Image Files into Folders

Auto Updates Jellyfin Posters

Checks Jellyfin every 30sec for new Items 


## Current Limitations: No support for Season Images outside of zip files. 

Place the zip files into the RawCover folder.

## How to use

Start the script again with `python main.py` and add .zip or single images files into the RawCover Folder
