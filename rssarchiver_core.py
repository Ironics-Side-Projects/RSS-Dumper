import re
import requests
import json
from pathlib import Path
from email.utils import parsedate_to_datetime
from datetime import timezone, datetime
from urllib.parse import urljoin, urlparse
import feedparser

from .utils.util import uopen, smkdirs
from .utils.patch import SessionMonkeyPatch


def download_image(image_url, images_dir, referer=None):
    """Download image and return local path relative to output dir."""
    if not image_url:
        return None

    try:
        if not image_url.startswith(('http://', 'https://')):
            print(f"[!] Skipping non-http image: {image_url}")
            return None

        parsed = urlparse(image_url)
        filename = Path(parsed.path).name
        if not filename or '.' not in filename:
            filename = f"image_{abs(hash(image_url)) % 1000000}{Path(parsed.path).suffix or '.jpg'}"

        # Remove ALL control characters and problematic chars
        safe_filename = ''.join(c for c in filename if ord(c) >= 32 and c not in '\0\r\n')
        safe_filename = safe_filename.replace('/', '∕')

        local_path = images_dir / safe_filename

        if local_path.exists():
            print(f"[i] Image already exists: {local_path.name}")
            # Return clean relative path without leading ./
            return f"images/{safe_filename}"

        print(f"[↓] Downloading image: {image_url} → {local_path.name}")

        headers = {'Referer': referer} if referer else {}
        response = requests.get(image_url, headers=headers, timeout=30)
        response.raise_for_status()

        content_type = response.headers.get('content-type', '')
        if not content_type.startswith('image/'):
            print(f"[!] Not an image (Content-Type: {content_type}): {image_url}")
            return None

        with open(local_path, 'wb') as f:
            f.write(response.content)

        return f"images/{safe_filename}"

    except Exception as e:
        print(f"[!] Failed to download image {image_url}: {e}")
        return None


def fetch_favicon(site_url, images_dir, session=None):
    """Fetch favicon from website homepage."""
    try:
        print(f"🔍 Looking for favicon at {site_url}")
        
        # Parse the URL to get base domain
        parsed = urlparse(site_url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Try to fetch the homepage
        if session:
            response = session.get(base_url, timeout=10)
        else:
            response = requests.get(base_url, timeout=10)
        response.raise_for_status()
        
        html = response.text
        favicon_url = None
        
        # Look for various favicon declarations in order of preference
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
        
        # If no explicit favicon found, try common locations
        if not favicon_url:
            common_paths = ['/favicon.ico', '/favicon.png', '/apple-touch-icon.png']
            for path in common_paths:
                test_url = urljoin(base_url, path)
                try:
                    if session:
                        test_response = session.head(test_url, timeout=5)
                    else:
                        test_response = requests.head(test_url, timeout=5)
                    if test_response.status_code == 200:
                        favicon_url = path
                        break
                except:
                    continue
        
        if favicon_url:
            # Make absolute URL
            favicon_url = urljoin(base_url, favicon_url)
            print(f"✅ Found favicon: {favicon_url}")
            
            # Download it
            local_path = download_image(favicon_url, images_dir, referer=base_url)
            return favicon_url, local_path
        else:
            print(f"❌ No favicon found for {base_url}")
            return None, None
            
    except Exception as e:
        print(f"⚠️ Failed to fetch favicon: {e}")
        return None, None


def extract_media_thumbnails(entry, images_dir, base_url):
    """Extract and download media:thumbnail elements from RSS entry."""
    downloaded = []
    
    # Check for media:thumbnail
    if hasattr(entry, 'media_thumbnail'):
        for thumb in entry.media_thumbnail:
            thumb_url = thumb.get('url')
            if thumb_url:
                local_path = download_image(thumb_url, images_dir, referer=base_url)
                if local_path:
                    downloaded.append({
                        'original_url': thumb_url,
                        'local_path': local_path,
                        'width': thumb.get('width'),
                        'height': thumb.get('height')
                    })
    
    # Check for media:content (sometimes contains images)
    if hasattr(entry, 'media_content'):
        for media in entry.media_content:
            if media.get('medium') == 'image' or (media.get('type', '').startswith('image/')):
                media_url = media.get('url')
                if media_url:
                    local_path = download_image(media_url, images_dir, referer=base_url)
                    if local_path:
                        downloaded.append({
                            'original_url': media_url,
                            'local_path': local_path,
                            'type': media.get('type'),
                            'medium': media.get('medium')
                        })
    
    # Check for enclosures (another way images can be included)
    if hasattr(entry, 'enclosures'):
        for enclosure in entry.enclosures:
            if enclosure.get('type', '').startswith('image/'):
                enc_url = enclosure.get('href') or enclosure.get('url')
                if enc_url:
                    local_path = download_image(enc_url, images_dir, referer=base_url)
                    if local_path:
                        downloaded.append({
                            'original_url': enc_url,
                            'local_path': local_path,
                            'type': enclosure.get('type')
                        })
    
    return downloaded


def extract_and_download_images_in_html(html, base_url, images_dir):
    """Find all <img> tags, download images, return rewritten HTML."""
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


def save_feed_metadata(feed, output_dir, images_dir, session=None):
    """Save channel metadata and download channel image or favicon."""
    f = feed.feed
    metadata = {
        'title': getattr(f, 'title', ''),
        'link': getattr(f, 'link', ''),
        'description': getattr(f, 'description', ''),
        'language': getattr(f, 'language', ''),
        'copyright': getattr(f, 'copyright', ''),
        'pubDate': getattr(f, 'published', ''),
        'lastBuildDate': getattr(f, 'published_parsed', None),
        'generator': getattr(f, 'generator', ''),
        'image': {},
        'fetched_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'items_count': len(feed.entries),
    }

    # Try to get channel image from feed
    feed_image = getattr(f, 'image', None)
    img_url = None
    local_img = None
    
    if feed_image:
        img_url = getattr(feed_image, 'href', '') or getattr(feed_image, 'url', '')
        if img_url:
            print(f"📷 Found feed image: {img_url}")
            # Download image
            local_img = download_image(img_url, images_dir, referer=metadata['link'])
    
    # If no feed image, try to get favicon
    if not local_img and metadata['link']:
        print("🔎 No feed image found, trying to fetch favicon...")
        favicon_url, favicon_local = fetch_favicon(metadata['link'], images_dir, session)
        if favicon_local:
            img_url = favicon_url
            local_img = favicon_local
            
    # Store image metadata
    if local_img:
        # Clean any potential null characters
        clean_local_img = ''.join(c for c in local_img if c != '\0')
        metadata['image'] = {
            'url': img_url,
            'local_path': clean_local_img,
            'title': getattr(feed_image, 'title', '') if feed_image else 'Site Favicon',
            'link': getattr(feed_image, 'link', '') if feed_image else metadata['link'],
            'is_favicon': not bool(feed_image)  # Track if this was a favicon fallback
        }

    meta_file = output_dir / "feed.json"
    with uopen(meta_file, 'w') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"[+] Saved feed metadata to: {meta_file}")

    return metadata


def save_items_as_files(feed, output_dir, images_dir, format='json'):
    """Save each item, download embedded images AND media thumbnails."""
    items_dir = output_dir / "items"
    items_dir.mkdir(exist_ok=True)
    image_count = 0

    for i, entry in enumerate(feed.entries):
        title = getattr(entry, 'title', f'item_{i}')
        pubdate_str = getattr(entry, 'published', '')
        guid = getattr(entry, 'id', getattr(entry, 'link', f'item_{i}'))
        base_url = getattr(entry, 'link', getattr(feed.feed, 'link', ''))

        # Parse date
        date_str = f"item_{i}"
        if pubdate_str:
            try:
                dt = parsedate_to_datetime(pubdate_str)
                date_str = dt.strftime('%Y-%m-%d')
            except Exception:
                pass

        safe_title = title.replace('/', '∕').replace('\0', '')
        filename = f"{date_str} — {safe_title}.{format}"
        filepath = items_dir / filename

        # Process description HTML
        description = getattr(entry, 'description', '')
        content_encoded = ""
        if hasattr(entry, 'content') and len(entry.content) > 0:
            content_encoded = entry.content[0].get('value', '')

        html_to_process = content_encoded if content_encoded.strip() else description
        rewritten_html, html_images = extract_and_download_images_in_html(
            html_to_process, base_url, images_dir
        )
        
        # Download media:thumbnail and other media elements
        media_images = extract_media_thumbnails(entry, images_dir, base_url)
        
        # Combine all downloaded images
        all_downloaded_images = html_images + media_images
        image_count += len(all_downloaded_images)

        final_description = rewritten_html if html_to_process == description else description
        final_content = rewritten_html if html_to_process == content_encoded else content_encoded

        item_data = {
            'title': title,
            'link': getattr(entry, 'link', ''),
            'description': final_description,
            'author': getattr(entry, 'author', ''),
            'guid': guid,
            'pubDate': pubdate_str,
            'downloaded_images': all_downloaded_images,
        }

        # Add content:encoded if it exists and is different from description
        if content_encoded and content_encoded != description:
            item_data['content_encoded'] = final_content

        if format == 'json':
            with uopen(filepath, 'w') as f:
                json.dump(item_data, f, indent=2, ensure_ascii=False)
        elif format == 'md':
            md_content = f"""# {title}

**Link:** {item_data['link']}  
**Published:** {pubdate_str}  
**GUID:** {guid}  

---

{final_description}

"""
            if all_downloaded_images:
                md_content += "\n**Images:**\n"
                for img in all_downloaded_images:
                    md_content += f"- ![{title}]({img['local_path']})\n"

            with uopen(filepath, 'w') as f:
                f.write(md_content)

        print(f"[+] Saved item: {filepath.name}")

    return len(feed.entries), image_count


def download_rss_feed(url: str, output_dir: Path, session: requests.Session, item_format: str = 'json'):
    """Main download function — called by rssdumper.py"""
    print(f"📡 Fetching RSS feed: {url}")

    try:
        response = session.get(url, timeout=30)
        if response.status_code != 200:
            raise HTTPStatusError(response.status_code, url)
        feed = feedparser.parse(response.content)
    except Exception as e:
        raise Exception(f"Failed to parse feed: {e}")

    if not feed.entries:
        raise Exception("No items found in feed.")

    # Create images dir
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)

    # Save metadata (now with favicon support)
    save_feed_metadata(feed, output_dir, images_dir, session)

    # Save items with media thumbnail support
    item_count, image_count = save_items_as_files(feed, output_dir, images_dir, format=item_format)

    return {'items': item_count, 'images': image_count}