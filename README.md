# RSS Dumper

A comprehensive RSS/Atom feed archiver that downloads and preserves feeds with all associated media content, then uploads them to the Internet Archive for long-term preservation.

## Features

### 🎯 Complete Feed Archival
- Downloads and preserves the original RSS/XML feed
- Extracts and saves all feed metadata in structured JSON
- Archives all feed items with full metadata preservation
- Supports both JSON and Markdown output formats
- Optional WARC format for complete HTTP transaction preservation

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

### 📼 WARC Support (Web ARChive)
- Captures complete HTTP transactions
- Preserves all HTTP headers and response codes
- Records exact timestamps for each request
- Compatible with Wayback Machine replay tools
- Documents server infrastructure and CDN behavior
- Creates browsable archives with pywb or ReplayWeb.page

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
- Optional WARC upload to special collections for Wayback Machine ingestion

## Installation

### Requirements
```bash
# Core dependencies
pip install feedparser requests internetarchive

# Optional but recommended
pip install Pillow  # For ICO to PNG conversion
pip install warcio  # For WARC file creation

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

# Create WARC archive (captures all HTTP transactions)
python3 -m RSS-Dumper.rssdumper https://example.com/feed.rss --warc
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

# Upload WARC to special collection for potential Wayback Machine ingestion
python3 -m RSS-Dumper.rssuploader ./example.com_20251019_232222 --warc-collection archiveteam_urls
```

## Output Structure

```
example.com_20251019_232222/
├── feed.json           # Parsed feed metadata
├── feed.rss            # Original raw RSS/XML feed
├── feed.warc.gz        # WARC archive (if --warc used)
├── items/              # Individual feed items
│   ├── 2025-10-19 — Article Title.json
│   └── 2025-10-18 — Another Article.json
├── images/             # Downloaded images
│   ├── thumbnail1.jpg
│   ├── logo.png
│   └── favicon.png
├── audio/              # Podcast episodes (if applicable)
│   └── episode1.mp3
├── video/              # Video content (if applicable)
│   └── video1.mp4
├── documents/          # Transcripts, chapters, etc.
│   └── transcript.txt
├── media/              # Other media files
└── dumpMeta/           # Dump metadata
    └── config.json     # Dump configuration
```

## WARC Archive Contents

When using `--warc`, the `feed.warc.gz` file preserves:
- **HTTP Headers**: User-Agent, Server, Content-Type, Cache-Control, ETags
- **Response Codes**: 200 OK, 301 redirects, 304 not-modified
- **Timestamps**: Exact capture time for each request
- **Server Info**: CDN details, rate limits, compression
- **Complete Transactions**: Both requests and responses for all downloads

### Replaying WARC Files

```bash
# Using pywb (Python Wayback)
pip install pywb
wb-manager init my-collection
wb-manager add my-collection feed.warc.gz
wayback
# Browse at http://localhost:8080/my-collection/

# Using ReplayWeb.page (browser-based)
# Visit https://replayweb.page and drag-drop your WARC file
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
- Complete namespace declarations

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
- All namespace-specific metadata

### Media Processing
- **Images**: Downloaded and paths rewritten in HTML
- **ICO files**: Automatically converted to PNG
- **Favicons**: Fetched if no feed image exists
- **Audio/Video**: Downloaded with metadata preserved
- **Documents**: PDF, transcripts, chapters preserved
- **HTTP Transactions**: Captured in WARC if enabled

## Internet Archive Upload

Files are organized and compressed before upload:
- `items.7z` - All feed items (high compression)
- `images.7z` - All images (low compression)
- `audio.7z` - Audio files (if present)
- `video.7z` - Video files (if present)
- `documents.7z` - Documents (if present)
- `media.7z` - Other media files (if present)
- `feed.json` - Parsed metadata
- `feed.rss` - Original feed
- `feed.warc.gz` - WARC archive (if created)

### WARC Collections

For potential Wayback Machine ingestion, upload WARCs to special collections:
```bash
# Upload to archiveteam collection
python3 -m RSS-Dumper.rssuploader ./dump_dir --warc-collection archiveteam_urls

# Upload to your own collection
python3 -m RSS-Dumper.rssuploader ./dump_dir --warc-collection my-warc-collection
```

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
- JSON/text: High compression (level 5)
- Media files: Low compression (level 1)
- Documents: Medium compression (level 3)
- Optional no-compression mode for faster processing

### WARC Benefits
- **Complete Preservation**: Every HTTP transaction recorded
- **Research Value**: Headers show server infrastructure, CDNs, redirects
- **Legal Evidence**: Cryptographically verifiable timestamps
- **Wayback Compatible**: Can be replayed in any Wayback Machine
- **Future-Proof**: Preserves technical context for historical research

## Examples

### Archive a blog feed
```bash
python3 -m RSS-Dumper.rssdumper https://example.blog/feed.xml
```

### Archive a podcast with WARC
```bash
python3 -m RSS-Dumper.rssdumper https://podcast.example.com/rss --warc
```

### Archive and upload to IA with WARC collection
```bash
# Download with WARC
python3 -m RSS-Dumper.rssdumper https://news.site.com/rss.xml --warc

# Upload with WARC to special collection
python3 -m RSS-Dumper.rssuploader ./news.site.com_20251020_120000 --warc-collection archiveteam_urls
```

### Complete preservation workflow
```bash
# 1. Download with all preservation features
python3 -m RSS-Dumper.rssdumper https://important.feed/rss --warc --format json

# 2. Upload to Internet Archive with WARC collection
python3 -m RSS-Dumper.rssuploader ./important.feed_20251020_120000 --warc-collection my-feeds

# 3. The WARC can later be submitted for Wayback Machine ingestion
```

## Contributing

This project was AI-generated based on [DokuWiki Dumper](https://github.com/saveweb/dokuwiki-dumper) and [wikiteam3](https://github.com/saveweb/wikiteam3) code patterns.

Pull requests welcome for:
- Additional namespace support
- Performance improvements
- Bug fixes
- Documentation improvements
- WARC enhancements
- Everything and anything

## Acknowledgments

- Inspired by [wikiteam3](https://github.com/saveweb/wikiteam3) and [DokuWiki Dumper](https://github.com/saveweb/dokuwiki-dumper)
- Uses [feedparser](https://github.com/kurtmckee/feedparser) for RSS parsing
- Uploads via [internetarchive](https://github.com/jjjake/internetarchive) Python library
- WARC support via [warcio](https://github.com/webrecorder/warcio)