# RSS Dumper

A comprehensive RSS/Atom feed archiver that downloads and preserves feeds with all associated media content, then uploads them to the Internet Archive for long-term preservation.

## Features

### 🎯 Complete Feed Archival
- Downloads and preserves the original RSS/XML feed
- Extracts and saves all feed metadata in structured JSON
- Archives all feed items with full metadata preservation
- Supports both JSON and Markdown output formats

### 📸 Media Downloading
- **Images**: Downloads all images from feed items, including:
  - Images embedded in HTML content
  - `media:thumbnail` elements
  - `media:content` images
  - iTunes podcast artwork
  - Google Play podcast images
  - Channel/feed logos
  - Automatic favicon fetching as fallback
  - ICO to PNG conversion (requires Pillow)

- **Audio/Video**: Downloads podcast episodes and video content
  - Enclosures (standard podcast episodes)
  - `media:content` audio/video files
  - Preserves metadata (duration, bitrate, file size)

- **Documents**: Archives supplementary content
  - Podcast transcripts
  - Chapter files
  - PDF attachments
  - Other document enclosures

### 🔧 Namespace Support
Comprehensive support for RSS extensions and namespaces:
- **Standard RSS 2.0** - All core elements
- **Atom** - Atom syndication format
- **Dublin Core** (`dc:`) - Metadata elements
- **Content** (`content:`) - Encoded content
- **Media RSS** (`media:`) - Yahoo Media RSS
- **iTunes** (`itunes:`) - Apple Podcasts metadata
- **Google Play** (`googleplay:`) - Google Podcasts
- **Podcast 2.0** (`podcast:`) - Modern podcast namespace
- **Creative Commons** (`creativeCommons:`) - Licensing
- **Syndication** (`sy:`) - Update frequency
- **RawVoice** (`rawvoice:`) - PowerPress/Blubrry
- **GeoRSS** (`georss:`) - Geographic data

### 🏛️ Internet Archive Integration
- Automatic upload to Internet Archive
- Duplicate detection to avoid re-uploading
- Metadata preservation
- Collection organization
- Logo/favicon upload

## Installation

### Requirements
```bash
# Core dependencies
pip install feedparser requests internetarchive

# Optional but recommended
pip install Pillow  # For ICO to PNG conversion

# For Internet Archive upload
sudo apt-get install p7zip-full  # Or your OS equivalent
```

### Clone Repository
```bash
git clone https://github.com/yourusername/RSS-Dumper.git
cd RSS-Dumper
```

## Usage

### Downloading RSS Feeds

Basic usage:
```bash
python3 -m RSS-Dumper.rssdumper https://example.com/feed.rss
```

With options:
```bash
# Skip Internet Archive check
python3 -m RSS-Dumper.rssdumper https://example.com/feed.rss --no-ia-check

# Custom output directory
python3 -m RSS-Dumper.rssdumper https://example.com/feed.rss --output my_archive

# Markdown format for items
python3 -m RSS-Dumper.rssdumper https://example.com/feed.rss --format md

# Custom User-Agent
python3 -m RSS-Dumper.rssdumper https://example.com/feed.rss --user-agent "MyBot/1.0"
```

For edge cases (experimental feeds):
```bash
EDGECASE_OK=1 python3 -m RSS-Dumper.rssdumper https://example.com/feed.rss
```

### Uploading to Internet Archive

First, create an IA keys file:
```bash
echo "YOUR_ACCESS_KEY" > ~/.rss_uploader_ia_keys
echo "YOUR_SECRET_KEY" >> ~/.rss_uploader_ia_keys
```

Upload a dump:
```bash
python3 -m RSS-Dumper.rssuploader ./example.com_20251019_232222
```

With options:
```bash
# Use test collection (auto-deletes after 30 days)
python3 -m RSS-Dumper.rssuploader ./example.com_20251019_232222 -c test_collection

# Pack dumpMeta directory
python3 -m RSS-Dumper.rssuploader ./example.com_20251019_232222 -p

# No compression for images (faster)
python3 -m RSS-Dumper.rssuploader ./example.com_20251019_232222 -n images

# Delete local copy after upload
python3 -m RSS-Dumper.rssuploader ./example.com_20251019_232222 -d
```

## Output Structure

```
example.com_20251019_232222/
├── feed.json           # Parsed feed metadata
├── feed.rss           # Original raw RSS/XML feed
├── items/             # Individual feed items
│   ├── 2025-10-19 — Article Title.json
│   └── 2025-10-18 — Another Article.json
├── images/            # Downloaded images
│   ├── thumbnail1.jpg
│   ├── logo.png
│   └── favicon.png
├── audio/             # Podcast episodes (if applicable)
│   └── episode1.mp3
├── video/             # Video content (if applicable)
│   └── video1.mp4
├── documents/         # Transcripts, chapters, etc.
│   └── transcript.txt
├── media/             # Other media files
└── dumpMeta/          # Dump metadata
    └── config.json    # Dump configuration

```

## What Gets Downloaded

### Feed Level
- Feed title, description, language
- Copyright information
- Generator, webmaster, managing editor
- Publication dates
- Feed image/logo (with favicon fallback)
- iTunes/Google Play podcast metadata
- Categories and tags

### Item Level
- Title, link, description, author
- Publication date, GUID
- Full content (content:encoded)
- All embedded images
- Media thumbnails
- Audio/video enclosures
- Transcripts and chapter files
- iTunes episode information
- Geographic data (if present)

### Media Processing
- **Images**: Downloaded and paths rewritten in HTML
- **ICO files**: Automatically converted to PNG
- **Favicons**: Fetched if no feed image exists
- **Audio/Video**: Downloaded with metadata preserved
- **Documents**: PDF, transcripts, chapters preserved

## Internet Archive Upload

Files are organized and compressed before upload:
- `items.7z` - All feed items (high compression)
- `images.7z` - All images (low compression)
- `audio.7z` - Audio files (if present)
- `video.7z` - Video files (if present)
- `documents.7z` - Documents (if present)
- `feed.json` - Parsed metadata
- `feed.rss` - Original feed

## Advanced Features

### Duplicate Detection
The tool checks Internet Archive for recent dumps of the same feed to avoid duplicates.

### Lock Files
Prevents multiple simultaneous dumps of the same feed.

### Error Handling
- Automatic retries for failed downloads
- Graceful handling of malformed feeds
- Detailed error logging

### Compression Optimization
- Smart compression levels based on file type
- JSON/text: High compression
- Media files: Low/no compression
- Documents: Medium compression

## Examples

### Archive a blog feed
```bash
python3 -m RSS-Dumper.rssdumper https://example.blog/feed.xml
```

### Archive a podcast
```bash
python3 -m RSS-Dumper.rssdumper https://podcast.example.com/rss
```

### Archive and upload to IA
```bash
# Download
python3 -m RSS-Dumper.rssdumper https://news.site.com/rss.xml

# Upload
python3 -m RSS-Dumper.rssuploader ./news.site.com_20251020_120000
```

## Contributing

This project was AI-generated based on [DokuWiki Dumper](https://github.com/saveweb/dokuwiki-dumper) and [wikiteam3](https://github.com/saveweb/wikiteam3) code patterns.

Pull requests welcome for:
- Additional namespace support
- Performance improvements
- Bug fixes
- Documentation improvements
- Everything and anything

## Acknowledgments

- Inspired by [wikiteam3](https://github.com/saveweb/wikiteam3) and [DokuWiki Dumper](https://github.com/saveweb/dokuwiki-dumper)
- Uses [feedparser](https://github.com/kurtmckee/feedparser) for RSS parsing
- Uploads via [internetarchive](https://github.com/jjjake/internetarchive) Python library