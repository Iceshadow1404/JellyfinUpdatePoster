# Jellyfin Update Poster

Jellyfin Update Poster is a Python-based tool that helps organize and update cover images for your Jellyfin media server. It processes cover images, organizes them into appropriate directories, and updates the Jellyfin server with the new images.

## Features

- Organizes cover images for movies, TV shows, and collections
- Automatically processes new images added to the RawCover directory
- Updates Jellyfin server with new cover images
- Handles ZIP files containing multiple cover images from [ThePosterDB](https://theposterdb.com/)
- Handles Single image files

## Prerequisites

- Python 3.7 or higher
- Jellyfin server
- Jellyfin API key

## Installation

1. Clone the repository: `https://github.com/Iceshadow1404/JellyfinUpdatePoster`
2. Install the required dependencies: `pip install -r requirements.txt`
3. Open the `config.json` and edit it with your Jellyfin server URL and API key

## Usage

1. Place your cover images or ZIP files containing cover images in the `RawCover` directory.

2. Run the main script: `python main.py` To run the main function immediately after start: `main.py --main`

3. The script will process the images, organize them into the appropriate directories, and update your Jellyfin server.

4. Check the `processing.log` file for details on the script's operations.

5. If any folders are missing, they will be listed in the `missing_folders.txt` file.

## Directory Structure

- `RawCover`: Place new cover images or ZIP files here
- `Cover`: Organized cover images
  - `Poster`: Movie and TV show posters
  - `Collections`: Collection posters
- `Consumed`: Processed raw cover files
- `Replaced`: Backup of replaced cover images
