# Jellyfin Update Poster

Jellyfin Update Poster is a Python-based tool that helps organize and update cover images for your Jellyfin media server. It processes cover images, organizes them into appropriate directories, and updates the Jellyfin server with the new images.

## Features

- Organizes cover images for movies, TV shows, Episodes, and collections
- Automatically processes new images added to the RawCover directory
- Updates Jellyfin server with new cover images
- Handles ZIP files containing multiple cover images from [ThePosterDB](https://theposterdb.com/) and [MediUX](https://mediux.pro)
- Handles Single image files
- Set Downloader for [MediUX](https://mediux.pro)

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
   "jellyfin_url": "http://your-jellyfin-url",
    "api_key": "your-api-key",
    "tmdb_api_key": "your-tmdb-api-key",
    "use_tmdb": false,
    "use_HA_webhook": false,
    "HA_webhook_id": "your-HA-webhook_id",
    "HA_webhook_url": "your-HA_webhook_url"
}
```
Set `use_tmdb` to `false` if you don't want to use TMDB for English title lookups.

Set `use_HA_webhook` to `false` if you don't want to use the Home Assistant Webhook Feature.

## Usage

1. Place your cover images or ZIP files containing cover images in the `RawCover` directory.

2. Write [MediUX](https://mediux.pro) **set** links in the Mediux.txt file if you want to download covers from them. One link per line.

3. Run the main script: `python main.py` To run the main function immediately after start: `main.py --main`

4. The script will process the images, organize them into the appropriate directories, and update your Jellyfin server.

5. If TMDB integration is enabled, it will attempt to fetch and use English titles for non-English content.

6. Check the `processing.log` file for details on the script's operations.

7. If any folders are missing, they will be listed in the `missing_folders.txt` file.

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

## Known Bugs


If u get an Error like this: 
```
IMDB or TVDB tags detected or unknown years found. Waiting 30 seconds before refreshing...

[2024-08-11 15:06:03] SUCCESS: Items with unknown years:
 
[2024-08-11 15:06:03] SUCCESS:   - Series: Star Trek: Raumschiff Voyager (ID: 82d420d4780f0f362e5066a79ee5304b)
```

Go to the corresponding TV show or movie and add the year.

![](https://github.com/Iceshadow1404/JellyfinUpdatePoster/blob/main/assets/year.gif)


## Rare Bug / Limitation 

If you encounter a 'file name too long' error, it may be due to limitations of the ext4 file system (or similar). Consider switching to NTFS or shortening the file name or OriginalTitle in Jellyfin.

## Credits

Huge thanks to @Druidblack for the Logo
@nea89o for the MediuxDownloader and general help 
