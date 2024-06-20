# Auto Update Posters for Jellyfin
This tool converts .zip files from https://theposterdb.com/ into dedicated folders and updates the posters in Jellyfin.

## Requirements: Python 3.11 

Steps to install:

1. Clone this repository with `git clone https://github.com/Iceshadow1404/JellyfinUpdatePoster/`.
2. Navigate into the folder with `cd JellyfinUpdatePoster`.
3. Install all the required packages with `pip install Pillow`.
4. Add your Jellyfin IP:PORT and API key to config.json.
5. Start the script with `python main.py`.
6. ## The Script will crash on the first launch but these folders should have been created:

- Cover
  - Movies
  - Shows
  - Collections
- Consumed
- RawCover

7.  Start the script again with `python main.py`.

Check the root folder for a newly created file named missing_folders.txt. You can refer to this file to see the exact names of the required folders. Note that not all folders need to be present for the script to function correctly.

Place the zip files into the RawCover folder.

# Current Limitations:
## No support for zip files containing movies and TV shows. Zip files with multiple movies or shows are no problem.
