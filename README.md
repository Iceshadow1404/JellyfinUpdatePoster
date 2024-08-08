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
- TMDB API key (optional, for English title lookup)

## Installation

1. Clone the repository: `https://github.com/Iceshadow1404/JellyfinUpdatePoster`
2. Install the required dependencies: `pip install -r requirements.txt`
3. Open the `config.json` and edit it with your Jellyfin server URL and API key
4. (Optional) Add your TMDB API key to config.json if you want to use the English title lookup feature

## Configuration
Edit the config.json file to include the following: 
```
{
  "jellyfin_url": "your_jellyfin_url",
  "api_key": "your_jellyfin_api_key",
  "tmdb_api_key": "your_tmdb_api_key",
  "use_tmdb": true
}
```
Set `use_tmdb` to `false` if you don't want to use TMDB for English title lookups.

## Usage

1. Place your cover images or ZIP files containing cover images in the `RawCover` directory.

2. Run the main script: `python main.py` To run the main function immediately after start: `main.py --main`

3. The script will process the images, organize them into the appropriate directories, and update your Jellyfin server.

4. If TMDB integration is enabled, it will attempt to fetch and use English titles for non-English content.

5. Check the `processing.log` file for details on the script's operations.

6. If any folders are missing, they will be listed in the `missing_folders.txt` file.

## Directory Structure

- `RawCover`: Place new cover images or ZIP files here
- `Cover`: Organized cover images
  - `Poster`: Movie and TV show posters
  - `Collections`: Collection posters
- `Consumed`: Processed raw cover files
- `Replaced`: Backup of replaced cover images

## English Title Feature


When enabled, the script will attempt to fetch English titles for non-English content using TMDB. This allows for easier organization and searching of content, especially for libraries with mixed-language media. The script will look for folders using both the original title and the English title (if available).

## Note

The TMDB integration and English title lookup are optional features. If you don't provide a TMDB API key or set use_tmdb to false in the config, the script will function normally without these features.

## Rare Bug / Limitation 

If the path is longer than 255 bytes, the script will crash due to file system limitation.

To prevent this:

- Change the name/original title in Jellyfin
- Or switch to NTFS, because the path limit there is 255 characters.
