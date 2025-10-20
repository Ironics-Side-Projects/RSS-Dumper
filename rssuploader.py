#!/usr/bin/env python3
"""
RSS Uploader — Upload RSS Dumper archives to Internet Archive.

Usage:
    python rssuploader.py ./rss_dump_omniarchive.uk_20251019_230000
"""

import argparse
import hashlib
import shutil
from io import BytesIO
import time
from urllib.parse import urlparse
import json
import re
import sys
import os
import subprocess
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from internetarchive import get_item, Item
import requests

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

try:
    from __version__ import DUMPER_VERSION as UPLOADER_VERSION
except ImportError:
    from .__version__ import DUMPER_VERSION as UPLOADER_VERSION

try:
    from utils.config import get_config
except ImportError:
    from .utils.config import get_config

try:
    from utils.util import smkdirs
except ImportError:
    from .utils.util import smkdirs


# Constants
DEFAULT_COLLECTION = 'opensource'
USER_AGENT = f'RSSUploader/{UPLOADER_VERSION}'
UPLOADED_MARK = 'uploaded_to_IA.mark'
BUFFER_SIZE = 65536

# Directories to compress
DIRS_TO_7Z = ["items", "images"]
MARK_FILES = {
    "items": "items/",      # We don't use mark files — just check dir existence
    "images": "images/",
}

# Compression levels
MEDIA_COMPRESSION_LEVEL = 1
DEFAULT_COMPRESSION_LEVEL = 5
NO_COMPRESSION_LEVEL = 0


@dataclass
class UploadConfig:
    """Configuration for upload process."""
    dump_dir: str
    path7z: str
    access_key: str
    secret_key: str
    collection: str
    pack_dumpMeta_dir: bool
    level0_no_compress: List[str]
    delete_after_upload: bool = False


@dataclass
class FeedMetadata:
    """RSS feed metadata container."""
    title: str
    url: Optional[str]
    description: Optional[str]
    language: Optional[str]
    copyright: Optional[str] = None
    image_url: Optional[str] = None
    local_image_path: Optional[str] = None
    logo_source_path: Optional[str] = None  # 👈 NEW
    generator: Optional[str] = None
    pubDate: Optional[str] = None


class IAUploader:
    """Internet Archive uploader for RSS dumps."""

    def __init__(self, config: UploadConfig):
        self.config = config
        self.headers = {"User-Agent": USER_AGENT}

    def upload_dump(self) -> None:
        """Main upload process."""
        if self._is_already_uploaded():
            print("This dump has already been uploaded.")
            print(f"If you want to upload it again, please remove the file '{UPLOADED_MARK}'.")
            return

        try:
            # Prepare metadata and files
            feed_meta = self._extract_feed_metadata()
            identifier = self._generate_identifier()
            files_to_upload = self._prepare_files(identifier)

            # Upload to Internet Archive
            item_metadata = self._create_item_metadata(feed_meta)
            self._upload_to_ia(identifier, files_to_upload, item_metadata)

            # Get item reference for logo upload
            remote_identifier = f"rss-{identifier}"
            item = get_item(remote_identifier)

            # Upload logo if available
            self._upload_logo(item, feed_meta)

            # Update metadata with URLs
            self._update_item_metadata(identifier, feed_meta)

            # Mark as uploaded
            self._mark_as_uploaded()

            # Cleanup if requested
            if self.config.delete_after_upload:
                self._cleanup_dump_dir()

            print(f"\n\n--Done--\nYou can find it in https://archive.org/details/rss-{identifier}")

        except Exception as e:
            print(f"Upload failed: {e}")
            raise

    def _is_already_uploaded(self) -> bool:
        """Check if dump is already uploaded."""
        return os.path.exists(os.path.join(self.config.dump_dir, UPLOADED_MARK))

    def _extract_feed_metadata(self) -> FeedMetadata:
        """Extract feed metadata from dump directory."""
        feed_json_path = os.path.join(self.config.dump_dir, "feed.json")
        if not os.path.exists(feed_json_path):
            raise FileNotFoundError("feed.json not found — is this a valid RSS dump?")

        with open(feed_json_path, 'r', encoding='utf-8') as f:
            feed_data = json.load(f)

        # Extract image URL (both original and local path)
        image_data = feed_data.get('image', {})
        image_url = image_data.get('url', '')
        local_image_path = image_data.get('local_path', '')
        
        # If we have a local copy, use that path for upload
        # Otherwise fall back to original URL
        logo_source_path = None
        if local_image_path:
            # Clean the path - remove ALL control characters including null bytes
            safe_local_path = ''.join(c for c in local_image_path if ord(c) >= 32 and c != '\0')
            
            # Debug output
            print(f"DEBUG: feed.json local_path: {repr(local_image_path)}")
            print(f"DEBUG: cleaned local_path: {repr(safe_local_path)}")
            
            # Try different possible locations
            possible_paths = []
            
            # 1. Direct join with dump_dir (most likely)
            possible_paths.append(os.path.join(self.config.dump_dir, safe_local_path))
            
            # 2. If path starts with ./, try without it
            if safe_local_path.startswith('./'):
                possible_paths.append(os.path.join(self.config.dump_dir, safe_local_path[2:]))
            
            # 3. Try just the basename in images directory
            if '/' in safe_local_path:
                basename = os.path.basename(safe_local_path)
                possible_paths.append(os.path.join(self.config.dump_dir, "images", basename))
            
            # 4. Try absolute path if it exists
            if os.path.isabs(safe_local_path):
                possible_paths.append(safe_local_path)
            
            # Remove duplicates and clean all paths
            possible_paths = list(dict.fromkeys(possible_paths))
            possible_paths = [''.join(c for c in p if ord(c) >= 32 and c != '\0') for p in possible_paths]
            
            print(f"DEBUG: Trying paths: {possible_paths}")
            
            # Find the first existing path
            for path in possible_paths:
                if os.path.exists(path):
                    logo_source_path = path
                    print(f"✅ Found logo at: {path}")
                    break
            
            if not logo_source_path:
                print(f"❌ None of the paths exist")

        return FeedMetadata(
            title=feed_data.get('title', 'Unknown RSS Feed'),
            url=feed_data.get('link', ''),
            description=feed_data.get('description', ''),
            language=feed_data.get('language', ''),
            copyright=feed_data.get('copyright', ''),
            image_url=image_url,
            local_image_path=local_image_path,
            logo_source_path=logo_source_path,
            generator=feed_data.get('generator', ''),
            pubDate=feed_data.get('pubDate', ''),
        )

    def _generate_identifier(self) -> str:
        """Generate identifier from dump directory name."""
        dump_dir_ab = os.path.abspath(self.config.dump_dir)
        dump_dir_basename = os.path.basename(dump_dir_ab)

        # Validate format: <domain>_<timestamp> OR rss_dump_<domain>_<timestamp> (legacy)
        parts = dump_dir_basename.split('_')
        
        # Handle both old format (rss_dump_domain_YYYYMMDD_HHMMSS) and new format (domain_YYYYMMDD_HHMMSS)
        if dump_dir_basename.startswith('rss_dump_'):
            # Legacy format
            if len(parts) < 4:
                raise ValueError(f'Invalid dump directory name: {dump_dir_basename}')
            timestamp_part = parts[-2] + parts[-1]  # e.g., "20251019_230000" → "20251019230000"
        else:
            # New format without rss_dump_ prefix
            if len(parts) < 3:
                raise ValueError(f'Invalid dump directory name: {dump_dir_basename}')
            timestamp_part = parts[-2] + parts[-1]  # e.g., "20251019_230000" → "20251019230000"

        try:
            timestamp = int(timestamp_part[:8])  # Just check YYYYMMDD part
            if timestamp < 20230101:
                raise ValueError(
                    f'Invalid dump directory name: {dump_dir_basename}, '
                    'created before RSS Dumper was born!?'
                )
        except ValueError as e:
            if "created before" not in str(e):
                raise ValueError(f'Invalid dump directory name: {dump_dir_basename}')
            raise

        # Slugify for IA — replace illegal chars
        safe_id = re.sub(r'[^a-zA-Z0-9._-]', '_', dump_dir_basename)
        return safe_id[:100]  # IA limits identifier length

    def _prepare_files(self, identifier: str) -> Dict[str, str]:
        """Prepare files for upload."""
        filedict = {}

        # Handle dumpMeta (config.json) if requested
        if self.config.pack_dumpMeta_dir:
            dumpmeta_dir = os.path.join(self.config.dump_dir, "dumpMeta")
            if os.path.exists(dumpmeta_dir):
                compressed_file = self._compress_directory(dumpmeta_dir, "dumpMeta")
                filedict[f"{identifier}-dumpMeta.7z"] = compressed_file
        else:
            # Upload individual files in dumpMeta
            self._add_dumpmeta_files(identifier, filedict)

        # Always include feed.json
        feed_path = os.path.join(self.config.dump_dir, "feed.json")
        if os.path.exists(feed_path):
            filedict[f"{identifier}-feed.json"] = feed_path
        
        # Include raw RSS feed backup
        raw_feed_path = os.path.join(self.config.dump_dir, "feed.rss")
        if os.path.exists(raw_feed_path):
            filedict[f"{identifier}-feed.rss"] = raw_feed_path
            print(f"📄 Including raw RSS feed: feed.rss")

        # Compress and add directories
        for dir_name in DIRS_TO_7Z:
            dir_path = os.path.join(self.config.dump_dir, dir_name)
            if os.path.isdir(dir_path) and os.listdir(dir_path):  # not empty
                compressed_file = self._compress_directory(dir_path, dir_name)
                filedict[f"{identifier}-{dir_name}.7z"] = compressed_file

        return filedict

    def _add_dumpmeta_files(self, identifier: str, filedict: Dict[str, str]) -> None:
        """Add individual dumpMeta files to upload list."""
        dumpmeta_dir = os.path.join(self.config.dump_dir, "dumpMeta")
        if os.path.exists(dumpmeta_dir):
            for item in os.listdir(dumpmeta_dir):
                item_path = os.path.join(dumpmeta_dir, item)
                remote_name = f"{identifier}-dumpMeta/{item}"
                filedict[remote_name] = item_path

    def _compress_directory(self, dir_path: str, dir_name: str) -> str:
        """Compress directory to 7z format."""
        print(f"📦 Compressing {dir_path}...")

        # Determine compression level
        if dir_name in self.config.level0_no_compress:
            level = NO_COMPRESSION_LEVEL
            print(f"🗜️  Packing {dir_name} with level 0 compression...")
        elif dir_name in ["images"]:
            level = MEDIA_COMPRESSION_LEVEL
        else:
            level = DEFAULT_COMPRESSION_LEVEL

        return self._compress_with_7z(dir_path, level)

    def _compress_with_7z(self, dir_path: str, level: int) -> str:
        """Compress directory using 7z."""
        dir_path = os.path.abspath(dir_path)
        output_file = f"{dir_path}.7z"
        temp_file = f"{output_file}.tmp"

        if os.path.exists(output_file):
            print(f"File {output_file} already exists. Skip compressing.")
            return output_file

        # Build command
        if level == NO_COMPRESSION_LEVEL:
            cmd = [
                self.config.path7z, "a", "-t7z", f"-mx={level}",
                "-scsUTF-8", "-ms=off", temp_file, dir_path
            ]
        else:
            cmd = [
                self.config.path7z, "a", "-t7z", "-m0=lzma2", f"-mx={level}",
                "-scsUTF-8", "-md=64m", "-ms=off", temp_file, dir_path
            ]

        subprocess.run(cmd, check=True)
        os.rename(temp_file, output_file)
        return output_file

    def _create_item_metadata(self, feed_meta: FeedMetadata) -> Dict[str, str]:
        """Create initial item metadata with full channel info."""
        config = get_config(self.config.dump_dir)

        keywords = ["rss", "feed", "rss feed", "RSSDumper", "Really Simple Syndication", "RDF Site Summary"]
        if feed_meta.title and feed_meta.title not in keywords:
            keywords.append(feed_meta.title)
        if feed_meta.url:
            keywords.append(self._url_to_keyword(feed_meta.url))

        # Build description with rich metadata
        description_parts = [
            f"<strong>RSS Feed Title:</strong> {feed_meta.title}<br>",
            f"<strong>Description:</strong> {feed_meta.description}<br>",
        ]

        if feed_meta.url:
            description_parts.append(f'<strong>Website:</strong> <a href="{feed_meta.url}" rel="nofollow">{feed_meta.url}</a><br>')

        if feed_meta.copyright:
            description_parts.append(f"<strong>Copyright:</strong> {feed_meta.copyright}<br>")

        if feed_meta.generator:
            description_parts.append(f"<strong>Generated by:</strong> {feed_meta.generator}<br>")

        if feed_meta.pubDate:
            description_parts.append(f"<strong>Published:</strong> {feed_meta.pubDate}<br>")

        description_parts.extend([
            "<br>",
            f"Dumped with RSS-Dumper v{config.get('dumper_version', UPLOADER_VERSION)}, ",
            f"and uploaded with RSSUploader v{UPLOADER_VERSION}."
        ])

        metadata = {
            "mediatype": "web",
            "collection": self.config.collection,
            "title": f"RSS Feed - {feed_meta.title}",
            "description": "\n".join(description_parts),
            "last-updated-date": time.strftime("%Y-%m-%d", time.gmtime()),
            "subject": "; ".join(keywords[:5]),
            "upload-state": "uploading",
        }

        # Set language if available
        if feed_meta.language:
            metadata["language"] = feed_meta.language

        # Set rights if copyright available
        if feed_meta.copyright:
            metadata["rights"] = feed_meta.copyright

        return metadata

    def _url_to_keyword(self, url: str) -> str:
        """Convert URL to keyword-safe string."""
        from urllib.parse import urlparse
        netloc = urlparse(url).netloc.replace(':', '_').replace('.', '_')
        return netloc

    def _upload_to_ia(self, identifier: str, files: Dict[str, str], metadata: Dict[str, str]) -> None:
        """Upload files to Internet Archive."""
        remote_identifier = f"rss-{identifier}"

        print(f"🆔 Identifier (Local): {identifier}")
        print(f"🌐 Identifier (Remote): {remote_identifier}")

        # Check for existing files
        item = get_item(remote_identifier)
        files_to_upload = self._filter_existing_files(item, files)

        print(f"📤 Uploading {len(files_to_upload)} files...")
        print(metadata)

        if files_to_upload:
            item.upload(
                files=files_to_upload,
                metadata=metadata,
                access_key=self.config.access_key,
                secret_key=self.config.secret_key,
                verbose=True,
                queue_derive=False,
            )

        print(f"✅ Uploading {len(files_to_upload)} files: Done.\n")

        # Wait for item to be created
        self._wait_for_item_creation(remote_identifier)

    def _filter_existing_files(self, item: Item, files: Dict[str, str]) -> Dict[str, str]:
        """Filter out files that already exist in the item."""
        if not item.exists:
            return files  # No existing files

        existing_files = {f["name"] for f in item.files}
        filtered_files = {}

        for remote_name, local_path in files.items():
            if remote_name in existing_files:
                print(f"⏭️  File {remote_name} already exists in item.")
            else:
                filtered_files[remote_name] = local_path

        return filtered_files

    def _wait_for_item_creation(self, identifier: str, max_tries: int = 30) -> None:
        """Wait for item to be created on Internet Archive."""
        tries = max_tries
        item = get_item(identifier)

        while not item.exists and tries > 0:
            print(f"⏳ Waiting for item to be created ({tries})...", end='\r')
            time.sleep(30)
            item = get_item(identifier)
            tries -= 1

    def _update_item_metadata(self, identifier: str, feed_meta: FeedMetadata) -> None:
        """Update item metadata with URLs and final information."""
        remote_identifier = f"rss-{identifier}"
        item = get_item(remote_identifier)

        print("📝 Updating description...")

        updates = {}

        # Update description with URL
        if (feed_meta.url and
            (feed_meta.url not in item.metadata.get("description", "") or
             'https://github.com/Ironics-Side-Projects/RSS-Dumper' not in item.metadata.get("description", ""))):

            description_with_url = (
                f'RSS Feed: <a href="{feed_meta.url}" rel="nofollow">{feed_meta.title}</a>\n'
                '<br>\n<br>\n'
                f'Dumped with <a href="https://github.com/Ironics-Side-Projects/RSS-Dumper" rel="nofollow">'
                f'RSS-Dumper</a> v{get_config(self.config.dump_dir).get("UPLOADER_VERSION", UPLOADER_VERSION)}, '
                f'and uploaded with RSSUploader v{UPLOADER_VERSION}.'
            )
            updates["description"] = description_with_url

        # Update other metadata fields
        current_date = time.strftime("%Y-%m-%d", time.gmtime())
        if item.metadata.get("last-updated-date") != current_date:
            updates["last-updated-date"] = current_date

        # Update subject with length limits
        subject = self._create_subject_string(feed_meta)
        if item.metadata.get("subject") != subject:
            updates["subject"] = subject

        if feed_meta.url and item.metadata.get("originalurl") != feed_meta.url:
            updates["originalurl"] = feed_meta.url

        if item.metadata.get("upload-state") != "uploaded":
            updates["upload-state"] = "uploaded"

        # Apply updates
        if updates:
            response = item.modify_metadata(
                metadata=updates,
                access_key=self.config.access_key,
                secret_key=self.config.secret_key
            )

            if isinstance(response, requests.Response):
                print(response.text)
                response.raise_for_status()
                print("✅ Updating description: Done.")
            else:
                print("⚠️  Unexpected response type during metadata update")
        else:
            print("ℹ️  Updating description: No need to update.")

    def _create_subject_string(self, feed_meta: FeedMetadata) -> str:
        """Create subject string respecting IA's 255 byte limit."""
        base_keywords = ["rss", "feed", "json", "markdown", "xml", "rss feed", "RSSDumper", "RDF Site Summary", "Really Simple Syndication"]
        all_keywords = base_keywords.copy()

        if feed_meta.title and feed_meta.title not in all_keywords:
            all_keywords.append(feed_meta.title)
        if feed_meta.url:
            all_keywords.append(self._url_to_keyword(feed_meta.url))

        # Try full keywords first
        full_subject = "; ".join(all_keywords)
        if len(full_subject.encode("utf-8")) <= 255:
            return full_subject

        # Try without title
        without_title = base_keywords + ([self._url_to_keyword(feed_meta.url)] if feed_meta.url else [])
        subject_without_title = "; ".join(without_title)
        if len(subject_without_title.encode("utf-8")) <= 255:
            return subject_without_title

        # Fallback to base keywords only
        return "; ".join(base_keywords)

    def _mark_as_uploaded(self) -> None:
        """Mark dump as uploaded."""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        mark_content = f"Uploaded to Internet Archive with RSSUploader v{UPLOADER_VERSION} on {timestamp}"

        mark_path = os.path.join(self.config.dump_dir, UPLOADED_MARK)
        with open(mark_path, "w", encoding='UTF-8') as f:
            f.write(mark_content)

    def _upload_logo(self, item: Item, feed_meta: FeedMetadata) -> None:
        """Upload channel logo like wikiteam3 does."""
        if not feed_meta.image_url:
            print("ℹ️  No channel logo found.")
            return

        # Generate logo filename based on actual local file if available
        if feed_meta.logo_source_path and os.path.exists(feed_meta.logo_source_path):
            # Get extension from the actual local file
            local_ext = os.path.splitext(feed_meta.logo_source_path)[1].lower()
            if local_ext.startswith('.'):
                local_ext = local_ext[1:]  # Remove leading dot
            if len(local_ext) > 5 or not local_ext.isalnum():
                local_ext = 'png'  # Default to PNG since we convert ICOs
            ext = local_ext
        else:
            # Fallback to parsing from URL if no local file
            parsed_url = urlparse(feed_meta.image_url)
            ext = parsed_url.path.split('.')[-1].lower() if '.' in parsed_url.path else 'jpg'
            if len(ext) > 5 or not ext.isalnum():
                ext = 'jpg'
        
        logo_name = f"{item.identifier}_logo.{ext}"
        
        # Check if logo already exists
        for file_info in item.files:
            if file_info["name"] == logo_name:
                print(f"⏭️  Logo {logo_name} already exists, skip")
                return

        try:
            logo_content = None
            
            # Try to get logo content
            if feed_meta.logo_source_path and os.path.exists(feed_meta.logo_source_path):
                print(f"📤 Uploading local logo: {feed_meta.logo_source_path}")
                # Read file directly into memory to avoid path issues
                try:
                    # Use BytesIO like wikiteam3 does
                    with open(feed_meta.logo_source_path, 'rb') as f:
                        logo_content = BytesIO(f.read())
                except Exception as e:
                    print(f"Failed to read local file: {e}, trying download instead")
                    logo_content = None
            
            # If local read failed or no local file, download from URL
            if logo_content is None:
                print(f"📥 Downloading logo from: {feed_meta.image_url}")
                response = requests.get(feed_meta.image_url, timeout=30)
                response.raise_for_status()
                logo_content = BytesIO(response.content)

            # Upload logo using BytesIO object (like wikiteam3)
            response = item.upload(
                {logo_name: logo_content},
                access_key=self.config.access_key,
                secret_key=self.config.secret_key,
                verbose=True,
            )
            
            for r in response:
                if isinstance(r, requests.Response):
                    r.raise_for_status()
                    
            print(f"✅ Logo uploaded as: {logo_name}")
            
        except Exception as e:
            print(f"⚠️  Failed to upload logo: {e}")
            print("Don't worry, it's optional.")

# Utility functions
def file_sha1(path: str) -> str:
    """Calculate SHA1 hash of a file."""
    buffer = bytearray(BUFFER_SIZE)
    view = memoryview(buffer)
    digest = hashlib.sha1()

    with open(path, mode="rb") as f:
        while True:
            n = f.readinto(buffer)
            if not n:
                break
            digest.update(view[:n])

    return digest.hexdigest()


def read_ia_keys(keysfile: str) -> Tuple[str, str]:
    """Read Internet Archive keys from file.

    Returns:
        Tuple of (access_key, secret_key)
    """
    keysfile = os.path.expanduser(keysfile)

    with open(keysfile, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    if len(lines) < 2:
        raise ValueError("Keys file must contain at least 2 lines")

    access_key = lines[0].strip()
    secret_key = lines[1].strip()

    return access_key, secret_key


def create_upload_config(args: argparse.Namespace) -> UploadConfig:
    """Create upload configuration from command line arguments."""
    access_key, secret_key = read_ia_keys(args.keysfile)

    return UploadConfig(
        dump_dir=args.dump_dir,
        path7z=args.path7z,
        access_key=access_key,
        secret_key=secret_key,
        collection=args.collection,
        pack_dumpMeta_dir=args.pack_dumpMeta,
        level0_no_compress=args.level0_no_compress or [],
        delete_after_upload=args.delete
    )


def create_argument_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        prog="rssuploader",
        description=f"Upload an RSS dump to Internet Archive. (Version: {UPLOADER_VERSION})."
    )

    parser.add_argument(
        "-kf", "--keysfile",
        default="~/.rss_uploader_ia_keys",
        help="Path to the IA S3 keys file. (first line: access key, second line: secret key) "
             "[default: ~/.rss_uploader_ia_keys]"
    )

    parser.add_argument(
        "-p7z", "--path7z",
        default="7z",
        help="Path to 7z binary. [default: 7z]"
    )

    parser.add_argument(
        "-c", "--collection",
        default=DEFAULT_COLLECTION,
        help="Collection to upload to. ('test_collection' for testing (auto-delete after 30 days)) "
             "[default: opensource]"
    )

    parser.add_argument(
        "-p", "--pack-dumpMeta",
        action="store_true",
        help="Pack the dumpMeta/ directory into a 7z file, then upload it. "
             "instead of uploading all files in dumpMeta/ directory individually. "
             "[default: False]"
    )

    parser.add_argument(
        '-n', '--level0-no-compress',
        default=[],
        dest='level0_no_compress',
        choices=['images'],
        nargs='?',
        action='append',
        help='Pack specified dir(s) into 7z file(s) without any compression. (level 0, copy mode)'
    )

    parser.add_argument(
        '-d', '--delete',
        action='store_true',
        dest='delete',
        help='Delete the dump dir after uploading. [default: False]'
    )

    parser.add_argument(
        "dump_dir",
        help="Path to the RSS dump directory."
    )

    return parser


def main(params: Optional[List[str]] = None) -> int:
    """Main entry point."""
    parser = create_argument_parser()
    args = parser.parse_args(params)

    try:
        config = create_upload_config(args)
        uploader = IAUploader(config)
        uploader.upload_dump()
        return 0

    except KeyboardInterrupt:
        print("\nUpload cancelled by user.")
        return 1
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        return 1


if __name__ == "__main__":
    exit(main())