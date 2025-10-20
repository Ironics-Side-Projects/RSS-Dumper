# Add these imports at the top
from warcio.warcwriter import WARCWriter
from warcio.statusandheaders import StatusAndHeaders
import hashlib
import uuid

# Add this function for WARC capture
def create_warc_record(url, response, warc_writer):
    """Create WARC record from HTTP response."""
    try:
        # Create WARC response record
        headers_list = []
        for name, value in response.headers.items():
            headers_list.append((name, value))
        
        http_headers = StatusAndHeaders(f'{response.status_code} {response.reason}', 
                                       headers_list, protocol='HTTP/1.1')
        
        # Create unique WARC-Record-ID
        warc_record_id = f'<urn:uuid:{uuid.uuid4()}>'
        
        record = warc_writer.create_warc_record(
            url,
            'response',
            payload=BytesIO(response.content),
            length=len(response.content),
            http_headers=http_headers,
            warc_record_id=warc_record_id
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
                http_headers=request_http_headers,
                warc_record_id=f'<urn:uuid:{uuid.uuid4()}>'
            )
            warc_writer.write_record(request_record)
            
    except Exception as e:
        print(f"⚠️ Failed to write WARC record for {url}: {e}")


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
        
        headers = {'User-Agent': 'RSS-Dumper/1.0', 'Referer': referer} if referer else {'User-Agent': 'RSS-Dumper/1.0'}
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


# Update the main download function
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
            http_headers=StatusAndHeaders('', [
                ('Software', f'RSS-Dumper/{UPLOADER_VERSION}'),
                ('Format', 'WARC/1.0'),
                ('Conformsto', 'http://bibnum.bnf.fr/WARC/WARC_ISO_28500_version1_latestdraft.pdf')
            ])
        )
        warc_writer.write_record(info_record)
        print(f"📼 Creating WARC archive: feed.warc.gz")
    
    try:
        # Use custom headers
        headers = {'User-Agent': f'RSS-Dumper/{UPLOADER_VERSION}'}
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