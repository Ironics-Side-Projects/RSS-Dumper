import re
import requests
import json
from pathlib import Path
from email.utils import parsedate_to_datetime
from datetime import timezone, datetime
from urllib.parse import urljoin, urlparse
import feedparser
from io import BytesIO
import mimetypes
import hashlib
import uuid

# WARC imports
from warcio.warcwriter import WARCWriter
from warcio.statusandheaders import StatusAndHeaders

# Make imports work both when this file is executed as part of package
# (relative imports) and when running scripts directly from the repo
# (absolute imports). Try relative imports first, then fall back.
try:
    from .utils.util import uopen, smkdirs
    from .utils.patch import SessionMonkeyPatch
    from .__version__ import DUMPER_VERSION
except Exception:
    from utils.util import uopen, smkdirs
    from utils.patch import SessionMonkeyPatch
    from __version__ import DUMPER_VERSION

# Try to import PIL for image conversion
try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("⚠️ Pillow not installed. ICO files won't be converted to PNG.")


def get_safe_filename(url, default_ext='bin'):
    """Generate a safe filename from URL."""
    parsed = urlparse(url)
    filename = Path(parsed.path).name
    
    if not filename or '.' not in filename:
        # Generate filename from URL hash
        filename = f"file_{abs(hash(url)) % 1000000}.{default_ext}"
    
    # Remove control characters
    safe_filename = ''.join(c for c in filename if ord(c) >= 32 and c not in '\0\r\n')
    safe_filename = safe_filename.replace('/', '∕')
    
    return safe_filename

def create_warc_record(url, response, warc_writer):
    """Create WARC record from HTTP response."""
    try:
        # Create WARC response record
        headers_list = []
        for name, value in response.headers.items():
            headers_list.append((name, value))
        
        http_headers = StatusAndHeaders(f'{response.status_code} {response.reason}', 
                                       headers_list, protocol='HTTP/1.1')
        
        record = warc_writer.create_warc_record(
            url,
            'response',
            payload=BytesIO(response.content),
            length=len(response.content),
            http_headers=http_headers
        )
        
        warc_writer.write_record(record)
        
        # Also create request record
        request_headers = []
        if hasattr(response, 'request'):
            for name, value in response.request.headers.items():
                request_headers.append((name, value))
            
            request_http_headers = StatusAndHeaders(
                f'{response.request.method} {response.request.path_url} HTTP/1.1',
                request_headers,
                protocol='HTTP/1.1'
            )
            
            request_record = warc_writer.create_warc_record(
                url,
                'request',
                http_headers=request_http_headers
            )
            warc_writer.write_record(request_record)
            
    except Exception as e:
        print(f"⚠️ Failed to write WARC record for {url}: {e}")

def download_file(file_url, output_dir, subfolder=None, referer=None, convert_ico=True):
    """Generic file downloader that handles any file type."""
    if not file_url:
        return None
    
    try:
        if not file_url.startswith(('http://', 'https://')):
            print(f"[!] Skipping non-http file: {file_url}")
            return None
        
        # Determine output directory
        if subfolder:
            target_dir = output_dir / subfolder
            target_dir.mkdir(exist_ok=True)
        else:
            target_dir = output_dir
        
        filename = get_safe_filename(file_url)
        
        # Check if it's an ICO file and we should convert
        is_ico = filename.lower().endswith('.ico')
        if is_ico and convert_ico and PIL_AVAILABLE:
            filename = filename[:-4] + '.png'
        
        local_path = target_dir / filename
        
        # Build relative path for storage
        if subfolder:
            relative_path = f"{subfolder}/{filename}"
        else:
            relative_path = filename
        
        if local_path.exists():
            print(f"[i] File already exists: {local_path.name}")
            return relative_path
        
        print(f"[↓] Downloading: {file_url} → {local_path.name}")
        
        headers = {'User-Agent': f'RSS-Dumper/{DUMPER_VERSION}', 'Referer': referer} if referer else {'User-Agent': f'RSS-Dumper/{DUMPER_VERSION}'}
        response = requests.get(file_url, headers=headers, timeout=30, stream=False)
        response.raise_for_status()
        
        content = response.content
        
        # Convert ICO to PNG if needed
        if is_ico and convert_ico and PIL_AVAILABLE:
            try:
                print(f"🔄 Converting ICO to PNG...")
                ico_image = Image.open(BytesIO(content))
                png_buffer = BytesIO()
                ico_image.save(png_buffer, format='PNG')
                content = png_buffer.getvalue()
                print(f"✅ Converted ICO to PNG")
            except Exception as e:
                print(f"⚠️ Failed to convert ICO: {e}")
        
        with open(local_path, 'wb') as f:
            f.write(content)
        
        return relative_path
        
    except Exception as e:
        print(f"[!] Failed to download {file_url}: {e}")
        return None


def download_file_with_warc(file_url, output_dir, subfolder=None, referer=None, convert_ico=True, warc_writer=None):
    """Generic file downloader that handles any file type and optionally writes to WARC."""
    if not file_url:
        return None
    
    try:
        if not file_url.startswith(('http://', 'https://')):
            print(f"[!] Skipping non-http file: {file_url}")
            return None
        
        # Determine output directory
        if subfolder:
            target_dir = output_dir / subfolder
            target_dir.mkdir(exist_ok=True)
        else:
            target_dir = output_dir
        
        filename = get_safe_filename(file_url)
        
        # Check if it's an ICO file and we should convert
        is_ico = filename.lower().endswith('.ico')
        if is_ico and convert_ico and PIL_AVAILABLE:
            filename = filename[:-4] + '.png'
        
        local_path = target_dir / filename
        
        # Build relative path for storage
        if subfolder:
            relative_path = f"{subfolder}/{filename}"
        else:
            relative_path = filename
        
        if local_path.exists():
            print(f"[i] File already exists: {local_path.name}")
            return relative_path
        
        print(f"[↓] Downloading: {file_url} → {local_path.name}")
        
        headers = {'User-Agent': f'RSS-Dumper/{DUMPER_VERSION}', 'Referer': referer} if referer else {'User-Agent': f'RSS-Dumper/{DUMPER_VERSION}'}
        response = requests.get(file_url, headers=headers, timeout=30, stream=False)
        response.raise_for_status()
        
        # Write to WARC if writer provided
        if warc_writer:
            create_warc_record(file_url, response, warc_writer)
        
        content = response.content
        
        # Convert ICO to PNG if needed
        if is_ico and convert_ico and PIL_AVAILABLE:
            try:
                print(f"🔄 Converting ICO to PNG...")
                ico_image = Image.open(BytesIO(content))
                png_buffer = BytesIO()
                ico_image.save(png_buffer, format='PNG')
                content = png_buffer.getvalue()
                print(f"✅ Converted ICO to PNG")
            except Exception as e:
                print(f"⚠️ Failed to convert ICO: {e}")
        
        with open(local_path, 'wb') as f:
            f.write(content)
        
        return relative_path
        
    except Exception as e:
        print(f"[!] Failed to download {file_url}: {e}")
        return None


def download_image(image_url, images_dir, referer=None):
    """Download image - wrapper for backward compatibility."""
    return download_file(image_url, images_dir.parent, 'images', referer, convert_ico=True)


def extract_all_media(entry, output_dir, base_url):
    """Extract ALL media types from an RSS entry including all namespace elements."""
    downloaded = {
        'images': [],
        'audio': [],
        'video': [],
        'documents': [],
        'other': []
    }
    
    # 1. Media:thumbnail
    if hasattr(entry, 'media_thumbnail'):
        for thumb in entry.media_thumbnail:
            thumb_url = thumb.get('url')
            if thumb_url:
                local_path = download_file(thumb_url, output_dir, 'images', referer=base_url)
                if local_path:
                    downloaded['images'].append({
                        'original_url': thumb_url,
                        'local_path': local_path,
                        'width': thumb.get('width'),
                        'height': thumb.get('height')
                    })
    
    # 2. Media:content (can be image, audio, or video)
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            media_url = media.get('url')
            media_type = media.get('type', '')
            media_medium = media.get('medium', '')
            
            if media_url:
                # Determine subfolder based on type
                if 'image' in media_type or media_medium == 'image':
                    subfolder = 'images'
                    category = 'images'
                elif 'audio' in media_type or media_medium == 'audio':
                    subfolder = 'audio'
                    category = 'audio'
                elif 'video' in media_type or media_medium == 'video':
                    subfolder = 'video'
                    category = 'video'
                else:
                    subfolder = 'media'
                    category = 'other'
                
                local_path = download_file(media_url, output_dir, subfolder, referer=base_url)
                if local_path:
                    downloaded[category].append({
                        'original_url': media_url,
                        'local_path': local_path,
                        'type': media_type,
                        'medium': media_medium,
                        'filesize': media.get('filesize'),
                        'duration': media.get('duration'),
                        'bitrate': media.get('bitrate'),
                        'width': media.get('width'),
                        'height': media.get('height')
                    })
    
    # 3. Enclosures (typically podcast audio/video)
    if hasattr(entry, 'enclosures'):
        for enclosure in entry.enclosures:
            enc_url = enclosure.get('href') or enclosure.get('url')
            enc_type = enclosure.get('type', '')
            
            if enc_url:
                # Determine file type
                if 'image' in enc_type:
                    subfolder = 'images'
                    category = 'images'
                elif 'audio' in enc_type:
                    subfolder = 'audio'
                    category = 'audio'
                elif 'video' in enc_type:
                    subfolder = 'video'
                    category = 'video'
                elif 'pdf' in enc_type or 'document' in enc_type:
                    subfolder = 'documents'
                    category = 'documents'
                else:
                    subfolder = 'media'
                    category = 'other'
                
                local_path = download_file(enc_url, output_dir, subfolder, referer=base_url)
                if local_path:
                    downloaded[category].append({
                        'original_url': enc_url,
                        'local_path': local_path,
                        'type': enc_type,
                        'length': enclosure.get('length')
                    })
    
    # 4. iTunes image
    if hasattr(entry, 'itunes_image'):
        itunes_img = entry.itunes_image
        if isinstance(itunes_img, dict):
            img_url = itunes_img.get('href')
        else:
            img_url = str(itunes_img) if itunes_img else None
        
        if img_url:
            local_path = download_file(img_url, output_dir, 'images', referer=base_url)
            if local_path:
                downloaded['images'].append({
                    'original_url': img_url,
                    'local_path': local_path,
                    'source': 'itunes:image'
                })
    
    # 5. Google Play image
    if hasattr(entry, 'googleplay_image'):
        gp_img = entry.googleplay_image
        if isinstance(gp_img, dict):
            img_url = gp_img.get('href')
        else:
            img_url = str(gp_img) if gp_img else None
        
        if img_url:
            local_path = download_file(img_url, output_dir, 'images', referer=base_url)
            if local_path:
                downloaded['images'].append({
                    'original_url': img_url,
                    'local_path': local_path,
                    'source': 'googleplay:image'
                })
    
    # 6. Podcast chapters
    if hasattr(entry, 'podcast_chapters'):
        chapters = entry.podcast_chapters
        if isinstance(chapters, dict):
            chapters_url = chapters.get('url')
            if chapters_url:
                local_path = download_file(chapters_url, output_dir, 'documents', referer=base_url)
                if local_path:
                    downloaded['documents'].append({
                        'original_url': chapters_url,
                        'local_path': local_path,
                        'type': 'chapters',
                        'mime_type': chapters.get('type')
                    })
    
    # 7. Podcast transcript
    if hasattr(entry, 'podcast_transcript'):
        transcripts = entry.podcast_transcript
        if not isinstance(transcripts, list):
            transcripts = [transcripts]
        
        for transcript in transcripts:
            if isinstance(transcript, dict):
                trans_url = transcript.get('url')
                if trans_url:
                    local_path = download_file(trans_url, output_dir, 'documents', referer=base_url)
                    if local_path:
                        downloaded['documents'].append({
                            'original_url': trans_url,
                            'local_path': local_path,
                            'type': 'transcript',
                            'mime_type': transcript.get('type'),
                            'language': transcript.get('language')
                        })
    
    # 8. RawVoice/PowerPress media
    if hasattr(entry, 'rawvoice_poster'):
        poster_url = entry.rawvoice_poster
        if poster_url:
            local_path = download_file(poster_url, output_dir, 'images', referer=base_url)
            if local_path:
                downloaded['images'].append({
                    'original_url': poster_url,
                    'local_path': local_path,
                    'source': 'rawvoice:poster'
                })
    
    return downloaded


def extract_full_item_metadata(entry):
    """Extract ALL metadata from an RSS item including all namespaces."""
    metadata = {}
    
    # Basic RSS elements
    basic_fields = [
        'title', 'link', 'description', 'author', 'guid', 'pubDate',
        'comments', 'source'
    ]
    for field in basic_fields:
        if hasattr(entry, field):
            value = getattr(entry, field)
            if value:
                metadata[field] = value
    
    # Category (can be multiple)
    if hasattr(entry, 'tags'):
        metadata['categories'] = [tag.term for tag in entry.tags if hasattr(tag, 'term')]
    
    # Dublin Core elements
    dc_fields = [
        'dc_creator', 'dc_date', 'dc_description', 'dc_subject',
        'dc_publisher', 'dc_contributor', 'dc_rights', 'dc_language',
        'dc_format', 'dc_identifier', 'dc_source', 'dc_relation',
        'dc_coverage', 'dc_type'
    ]
    for field in dc_fields:
        if hasattr(entry, field):
            value = getattr(entry, field)
            if value:
                metadata[field] = value
    
    # Content:encoded
    if hasattr(entry, 'content'):
        if entry.content and len(entry.content) > 0:
            metadata['content_encoded'] = entry.content[0].get('value', '')
    
    # Syndication (sy) namespace
    sy_fields = [
        'sy_updateperiod', 'sy_updatefrequency', 'sy_updatebase'
    ]
    for field in sy_fields:
        if hasattr(entry, field):
            value = getattr(entry, field)
            if value:
                metadata[field] = value
    
    # GeoRSS
    if hasattr(entry, 'georss_point'):
        metadata['georss_point'] = entry.georss_point
    if hasattr(entry, 'where'):
        metadata['georss_where'] = str(entry.where)
    
    # iTunes podcast elements
    itunes_fields = [
        'itunes_author', 'itunes_block', 'itunes_duration', 'itunes_episode',
        'itunes_episodetype', 'itunes_explicit', 'itunes_keywords',
        'itunes_season', 'itunes_subtitle', 'itunes_summary', 'itunes_title',
        'itunes_type', 'itunes_order'
    ]
    for field in itunes_fields:
        if hasattr(entry, field):
            value = getattr(entry, field)
            if value:
                metadata[field] = value
    
    # Google Play podcast elements
    googleplay_fields = [
        'googleplay_author', 'googleplay_description', 'googleplay_explicit',
        'googleplay_block'
    ]
    for field in googleplay_fields:
        if hasattr(entry, field):
            value = getattr(entry, field)
            if value:
                metadata[field] = value
    
    # Creative Commons
    cc_fields = [
        'creativecommons_license', 'creativecommons_attribution',
        'creativecommons_commercialuse', 'creativecommons_derivatives'
    ]
    for field in cc_fields:
        if hasattr(entry, field):
            value = getattr(entry, field)
            if value:
                metadata[field] = value
    
    # RawVoice/PowerPress elements
    rawvoice_fields = [
        'rawvoice_rating', 'rawvoice_location', 'rawvoice_frequency',
        'rawvoice_subscribe', 'rawvoice_donate'
    ]
    for field in rawvoice_fields:
        if hasattr(entry, field):
            value = getattr(entry, field)
            if value:
                metadata[field] = value
    
    # Podcast 2.0 elements
    podcast_fields = [
        'podcast_episode', 'podcast_guid', 'podcast_season',
        'podcast_trailer', 'podcast_license', 'podcast_location',
        'podcast_person', 'podcast_value', 'podcast_alternateenclosure',
        'podcast_socialinteract', 'podcast_txt', 'podcast_images'
    ]
    for field in podcast_fields:
        if hasattr(entry, field):
            value = getattr(entry, field)
            if value:
                metadata[field] = value
    
    # Media RSS elements
    media_fields = [
        'media_title', 'media_description', 'media_keywords',
        'media_category', 'media_credit', 'media_copyright',
        'media_text', 'media_restriction', 'media_rating',
        'media_hash', 'media_player', 'media_scenes',
        'media_status', 'media_price', 'media_license'
    ]
    for field in media_fields:
        if hasattr(entry, field):
            value = getattr(entry, field)
            if value:
                metadata[field] = value
    
    # Atom elements
    if hasattr(entry, 'links'):
        metadata['atom_links'] = entry.links
    if hasattr(entry, 'updated'):
        metadata['atom_updated'] = entry.updated
    if hasattr(entry, 'id'):
        metadata['atom_id'] = entry.id
    if hasattr(entry, 'published_parsed'):
        metadata['published_parsed'] = entry.published_parsed
    
    return metadata


def save_feed_metadata(feed, output_dir, images_dir, session=None):
    """Save comprehensive channel/feed metadata with all namespace support."""
    f = feed.feed
    
    # Get namespace declarations from feed
    namespaces = {}
    if hasattr(feed, 'namespaces'):
        namespaces = feed.namespaces
    
    # Extract all channel-level metadata
    metadata = {
        'namespaces': namespaces,
        'title': getattr(f, 'title', ''),
        'link': getattr(f, 'link', ''),
        'description': getattr(f, 'description', ''),
        'language': getattr(f, 'language', ''),
        'copyright': getattr(f, 'copyright', ''),
        'managingEditor': getattr(f, 'managingeditor', ''),
        'webMaster': getattr(f, 'webmaster', ''),
        'pubDate': getattr(f, 'published', ''),
        'lastBuildDate': getattr(f, 'updated', ''),
        'generator': getattr(f, 'generator', ''),
        'docs': getattr(f, 'docs', ''),
        'ttl': getattr(f, 'ttl', ''),
        'rating': getattr(f, 'rating', ''),
        'image': {},
        'fetched_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'items_count': len(feed.entries),
    }
    
    # Syndication (sy) namespace - update frequency
    sy_fields = [
        'sy_updateperiod', 'sy_updatefrequency', 'sy_updatebase'
    ]
    for field in sy_fields:
        if hasattr(f, field):
            value = getattr(f, field)
            if value:
                metadata[field] = value
    
    # Cloud element
    if hasattr(f, 'cloud'):
        metadata['cloud'] = f.cloud
    
    # Text input
    if hasattr(f, 'textinput'):
        metadata['textInput'] = f.textinput
    
    # Skip days/hours
    if hasattr(f, 'skipdays'):
        metadata['skipDays'] = f.skipdays
    if hasattr(f, 'skiphours'):
        metadata['skipHours'] = f.skiphours
    
    # Categories
    if hasattr(f, 'tags'):
        metadata['categories'] = [tag.term for tag in f.tags if hasattr(tag, 'term')]
    
    # Atom link
    if hasattr(f, 'links'):
        metadata['atom_links'] = f.links
    
    # Dublin Core
    dc_fields = [
        'dc_creator', 'dc_rights', 'dc_publisher', 'dc_contributor',
        'dc_date', 'dc_language', 'dc_format', 'dc_identifier',
        'dc_source', 'dc_relation', 'dc_coverage', 'dc_type'
    ]
    for field in dc_fields:
        if hasattr(f, field):
            value = getattr(f, field)
            if value:
                metadata[field] = value
    
    # iTunes podcast metadata
    itunes_fields = [
        'itunes_author', 'itunes_block', 'itunes_category', 'itunes_complete',
        'itunes_explicit', 'itunes_new_feed_url', 'itunes_owner',
        'itunes_subtitle', 'itunes_summary', 'itunes_type', 'itunes_keywords'
    ]
    for field in itunes_fields:
        if hasattr(f, field):
            value = getattr(f, field)
            if value:
                metadata[field] = value
    
    # iTunes image (separate from RSS image)
    if hasattr(f, 'itunes_image'):
        itunes_img = f.itunes_image
        if isinstance(itunes_img, dict):
            img_url = itunes_img.get('href')
        else:
            img_url = str(itunes_img) if itunes_img else None
        
        if img_url:
            local_img = download_file(img_url, output_dir, 'images', referer=metadata['link'])
            if local_img:
                metadata['itunes_image'] = {
                    'url': img_url,
                    'local_path': local_img
                }
    
    # Google Play podcast metadata
    googleplay_fields = [
        'googleplay_author', 'googleplay_category', 'googleplay_description',
        'googleplay_email', 'googleplay_explicit', 'googleplay_block',
        'googleplay_owner'
    ]
    for field in googleplay_fields:
        if hasattr(f, field):
            value = getattr(f, field)
            if value:
                metadata[field] = value
    
    # Google Play image
    if hasattr(f, 'googleplay_image'):
        gp_img = f.googleplay_image
        if isinstance(gp_img, dict):
            img_url = gp_img.get('href')
        else:
            img_url = str(gp_img) if gp_img else None
        
        if img_url:
            local_img = download_file(img_url, output_dir, 'images', referer=metadata['link'])
            if local_img:
                metadata['googleplay_image'] = {
                    'url': img_url,
                    'local_path': local_img
                }
    
    # Creative Commons licensing
    cc_fields = [
        'creativecommons_license', 'creativecommons_attribution',
        'creativecommons_commercialuse', 'creativecommons_derivatives'
    ]
    for field in cc_fields:
        if hasattr(f, field):
            value = getattr(f, field)
            if value:
                metadata[field] = value
    
    # RawVoice/PowerPress metadata
    rawvoice_fields = [
        'rawvoice_rating', 'rawvoice_location', 'rawvoice_frequency',
        'rawvoice_subscribe', 'rawvoice_donate', 'rawvoice_poster'
    ]
    for field in rawvoice_fields:
        if hasattr(f, field):
            value = getattr(f, field)
            if value:
                metadata[field] = value
    
    # RawVoice poster image
    if hasattr(f, 'rawvoice_poster'):
        poster_url = f.rawvoice_poster
        if poster_url:
            local_img = download_file(poster_url, output_dir, 'images', referer=metadata['link'])
            if local_img:
                metadata['rawvoice_poster_local'] = local_img
    
    # Podcast 2.0 namespace
    podcast_fields = [
        'podcast_funding', 'podcast_license', 'podcast_locked',
        'podcast_location', 'podcast_guid', 'podcast_value',
        'podcast_person', 'podcast_trailer', 'podcast_liveitem',
        'podcast_medium', 'podcast_images', 'podcast_block',
        'podcast_txt', 'podcast_remote', 'podcast_chat',
        'podcast_socialinteract', 'podcast_previousurl'
    ]
    for field in podcast_fields:
        if hasattr(f, field):
            value = getattr(f, field)
            if value:
                metadata[field] = value
    
    # Media RSS channel elements
    media_fields = [
        'media_copyright', 'media_rating', 'media_thumbnail',
        'media_keywords', 'media_category'
    ]
    for field in media_fields:
        if hasattr(f, field):
            value = getattr(f, field)
            if value:
                metadata[field] = value
    
    # Regular RSS image
    feed_image = getattr(f, 'image', None)
    img_url = None
    local_img = None
    
    if feed_image:
        img_url = getattr(feed_image, 'href', '') or getattr(feed_image, 'url', '')
        if img_url:
            print(f"📷 Found feed image: {img_url}")
            local_img = download_file(img_url, output_dir, 'images', referer=metadata['link'])
    
    # Fallback to favicon if no feed image
    if not local_img and metadata['link']:
        print("🔎 No feed image found, trying to fetch favicon...")
        favicon_url, favicon_local = fetch_favicon(metadata['link'], images_dir, session)
        if favicon_local:
            img_url = favicon_url
            local_img = favicon_local
    
    # Store main image metadata
    if local_img:
        clean_local_img = ''.join(c for c in local_img if c != '\0')
        metadata['image'] = {
            'url': img_url,
            'local_path': clean_local_img,
            'title': getattr(feed_image, 'title', '') if feed_image else 'Site Favicon',
            'link': getattr(feed_image, 'link', '') if feed_image else metadata['link'],
            'width': getattr(feed_image, 'width', '') if feed_image else '',
            'height': getattr(feed_image, 'height', '') if feed_image else '',
            'is_favicon': not bool(feed_image)
        }
    
    # Save metadata
    meta_file = output_dir / "feed.json"
    with uopen(meta_file, 'w') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"[+] Saved feed metadata to: {meta_file}")
    
    return metadata


def fetch_favicon(site_url, images_dir, session=None):
    """Fetch favicon from website homepage."""
    try:
        print(f"🔍 Looking for favicon at {site_url}")
        
        parsed = urlparse(site_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        if session:
            response = session.get(base_url, timeout=10)
        else:
            response = requests.get(base_url, timeout=10)
        response.raise_for_status()
        
        html = response.text
        favicon_url = None
        
        # Look for various favicon declarations
        patterns = [
            r'<link[^>]*rel=["\']apple-touch-icon["\'][^>]*href=["\']([^"\']+)["\']',
            r'<link[^>]*href=["\']([^"\']+)["\'][^>]*rel=["\']apple-touch-icon["\']',
            r'<link[^>]*rel=["\']icon["\'][^>]*href=["\']([^"\']+)["\']',
            r'<link[^>]*href=["\']([^"\']+)["\'][^>]*rel=["\']icon["\']',
            r'<link[^>]*rel=["\']shortcut icon["\'][^>]*href=["\']([^"\']+)["\']',
            r'<link[^>]*href=["\']([^"\']+)["\'][^>]*rel=["\']shortcut icon["\']',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                favicon_url = match.group(1)
                break
        
        # Try common locations if no explicit favicon found
        if not favicon_url:
            common_paths = ['/favicon.ico', '/favicon.png', '/apple-touch-icon.png']
            for path in common_paths:
                test_url = urljoin(base_url, path)
                try:
                    test_response = session.head(test_url, timeout=5) if session else requests.head(test_url, timeout=5)
                    if test_response.status_code == 200:
                        favicon_url = path
                        break
                except:
                    continue
        
        if favicon_url:
            favicon_url = urljoin(base_url, favicon_url)
            print(f"✅ Found favicon: {favicon_url}")
            local_path = download_image(favicon_url, images_dir, referer=base_url)
            return favicon_url, local_path
        else:
            print(f"❌ No favicon found for {base_url}")
            return None, None
            
    except Exception as e:
        print(f"⚠️ Failed to fetch favicon: {e}")
        return None, None


def extract_and_download_images_in_html(html, base_url, images_dir):
    """Find all <img> tags in HTML and download images."""
    if not html:
        return html, []
    
    img_pattern = r'<img\s+[^>]*src\s*=\s*["\']([^"\']+)["\'][^>]*>'
    matches = list(re.finditer(img_pattern, html, re.IGNORECASE))
    downloaded = []
    
    new_html = html
    offset = 0
    
    for match in matches:
        img_url = match.group(1)
        full_url = urljoin(base_url, img_url)
        local_path = download_image(full_url, images_dir, referer=base_url)
        
        if local_path:
            start, end = match.span()
            replacement = match.group(0).replace(img_url, local_path)
            adjusted_start = start + offset
            adjusted_end = end + offset
            new_html = new_html[:adjusted_start] + replacement + new_html[adjusted_end:]
            offset += len(replacement) - len(match.group(0))
            downloaded.append({'original_url': full_url, 'local_path': local_path})
    
    return new_html, downloaded


def save_items_as_files(feed, output_dir, images_dir, format='json'):
    """Save each item with ALL metadata and media."""
    items_dir = output_dir / "items"
    items_dir.mkdir(exist_ok=True)
    
    total_media_count = {
        'images': 0,
        'audio': 0,
        'video': 0,
        'documents': 0,
        'other': 0
    }
    
    for i, entry in enumerate(feed.entries):
        # Extract full metadata
        item_metadata = extract_full_item_metadata(entry)
        
        # Get basic fields for filename
        title = item_metadata.get('title', f'item_{i}')
        pubdate_str = item_metadata.get('pubDate', '')
        base_url = item_metadata.get('link', getattr(feed.feed, 'link', ''))
        
        # Parse date for filename
        date_str = f"item_{i}"
        if pubdate_str:
            try:
                dt = parsedate_to_datetime(pubdate_str)
                date_str = dt.strftime('%Y-%m-%d')
            except Exception:
                pass
        
        safe_title = title.replace('/', '∕').replace('\0', '')[:100]  # Limit length
        filename = f"{date_str} — {safe_title}.{format}"
        filepath = items_dir / filename
        
        # Process HTML content
        description = item_metadata.get('description', '')
        content_encoded = item_metadata.get('content_encoded', '')
        
        html_to_process = content_encoded if content_encoded.strip() else description
        rewritten_html, html_images = extract_and_download_images_in_html(
            html_to_process, base_url, images_dir
        )
        
        # Download ALL media types
        all_media = extract_all_media(entry, output_dir, base_url)
        
        # Add HTML images to media collection
        for img in html_images:
            all_media['images'].append(img)
        
        # Update counts
        for media_type, items in all_media.items():
            if isinstance(items, list):
                total_media_count[media_type] += len(items)
        
        # Update description with rewritten HTML
        if html_to_process == description:
            item_metadata['description'] = rewritten_html
        elif html_to_process == content_encoded:
            item_metadata['content_encoded'] = rewritten_html
        
        # Add downloaded media to metadata
        item_metadata['downloaded_media'] = all_media
        
        # Save item
        if format == 'json':
            with uopen(filepath, 'w') as f:
                json.dump(item_metadata, f, indent=2, ensure_ascii=False)
        elif format == 'md':
            md_content = f"""# {title}

**Link:** {item_metadata.get('link', '')}  
**Published:** {pubdate_str}  
**GUID:** {item_metadata.get('guid', '')}  
"""
            # Add additional metadata
            if item_metadata.get('author'):
                md_content += f"**Author:** {item_metadata['author']}  \n"
            if item_metadata.get('itunes_duration'):
                md_content += f"**Duration:** {item_metadata['itunes_duration']}  \n"
            if item_metadata.get('itunes_episode'):
                md_content += f"**Episode:** {item_metadata['itunes_episode']}  \n"
            if item_metadata.get('itunes_season'):
                md_content += f"**Season:** {item_metadata['itunes_season']}  \n"
            if item_metadata.get('googleplay_description'):
                md_content += f"**Google Play Description:** {item_metadata['googleplay_description']}  \n"
            
            md_content += f"\n---\n\n{rewritten_html or description}\n\n"
            
            # Add media references
            if all_media['images']:
                md_content += "\n**Images:**\n"
                for img in all_media['images']:
                    md_content += f"- ![Image]({img['local_path']})\n"
            
            if all_media['audio']:
                md_content += "\n**Audio files:**\n"
                for audio in all_media['audio']:
                    md_content += f"- [{audio.get('type', 'Audio')}]({audio['local_path']})\n"
            
            if all_media['video']:
                md_content += "\n**Video files:**\n"
                for video in all_media['video']:
                    md_content += f"- [{video.get('type', 'Video')}]({video['local_path']})\n"
            
            if all_media['documents']:
                md_content += "\n**Documents:**\n"
                for doc in all_media['documents']:
                    md_content += f"- [{doc.get('type', 'Document')}]({doc['local_path']})\n"
            
            with uopen(filepath, 'w') as f:
                f.write(md_content)
        
        print(f"[+] Saved item: {filepath.name}")
        
        # Print media stats for this item
        media_stats = []
        for media_type, items in all_media.items():
            if isinstance(items, list) and items:
                media_stats.append(f"{len(items)} {media_type}")
        if media_stats:
            print(f"    Downloaded: {', '.join(media_stats)}")
    
    return len(feed.entries), total_media_count


def download_rss_feed(url: str, output_dir: Path, session: requests.Session, item_format: str = 'json', save_warc: bool = False):
    """Main download function with comprehensive RSS/Podcast support and optional WARC capture."""
    print(f"📡 Fetching RSS feed: {url}")
    
    # Setup WARC writer if requested
    warc_writer = None
    warc_file = None
    if save_warc:
        warc_path = output_dir / "feed.warc.gz"
        warc_file = open(warc_path, 'wb')
        warc_writer = WARCWriter(warc_file, gzip=True)
        
        # Write WARC info record
        info_record = warc_writer.create_warcinfo_record(
            warc_path.name,
            {
                'software': f'RSS-Dumper/{DUMPER_VERSION}',
                'format': 'WARC File Format 1.0',
                'conformsTo': 'http://bibnum.bnf.fr/WARC/WARC_ISO_28500_version1_latestdraft.pdf'
            }
        )
        warc_writer.write_record(info_record)
        print(f"📼 Creating WARC archive: feed.warc.gz")
    
    try:
        # Use custom headers
        headers = {'User-Agent': f'RSS-Dumper/{DUMPER_VERSION}'}
        response = session.get(url, timeout=30, headers=headers)
        if response.status_code != 200:
            from .utils.exceptions import HTTPStatusError
            raise HTTPStatusError(response.status_code, url)
        
        # Write main feed to WARC
        if warc_writer:
            create_warc_record(url, response, warc_writer)
        
        # Save the raw RSS feed as backup
        feed_backup_path = output_dir / "feed.rss"
        with open(feed_backup_path, 'wb') as f:
            f.write(response.content)
        print(f"💾 Saved raw RSS feed to: feed.rss")
        
        # Parse the feed
        feed = feedparser.parse(response.content)
    except Exception as e:
        if warc_file:
            warc_file.close()
        raise Exception(f"Failed to parse feed: {e}")
    
    if not feed.entries:
        if warc_file:
            warc_file.close()
        raise Exception("No items found in feed.")
    
    # Print detected namespaces
    if hasattr(feed, 'namespaces'):
        print(f"📋 Detected namespaces: {', '.join(feed.namespaces.keys())}")
    
    # Create directory structure
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)
    
    # Create additional directories for different media types
    for media_dir in ['audio', 'video', 'documents', 'media']:
        (output_dir / media_dir).mkdir(exist_ok=True)
    
    # Monkey-patch download_file to use WARC writer
    if warc_writer:
        global download_file
        original_download_file = download_file
        download_file = lambda *args, **kwargs: download_file_with_warc(*args, **kwargs, warc_writer=warc_writer)
    
    try:
        # Save comprehensive metadata
        save_feed_metadata(feed, output_dir, images_dir, session)
        
        # Save items with all media
        item_count, media_counts = save_items_as_files(feed, output_dir, images_dir, format=item_format)
    finally:
        # Restore original download_file
        if warc_writer:
            download_file = original_download_file
            warc_file.close()
    
    # Calculate total media count
    total_media = sum(media_counts.values())
    
    # Print summary
    print(f"\n📊 Download Summary:")
    print(f"  • Items: {item_count}")
    print(f"  • Raw RSS feed: feed.rss")
    if save_warc:
        print(f"  • WARC archive: feed.warc.gz")
    for media_type, count in media_counts.items():
        if count > 0:
            print(f"  • {media_type.capitalize()}: {count}")
    
    return {
        'items': item_count,
        'images': media_counts.get('images', 0),
        'total_media': total_media,
        'media_breakdown': media_counts,
        'has_raw_feed': True,
        'has_warc': save_warc
    }