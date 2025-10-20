#!/usr/bin/env python3
"""
RSS Dumper — Full archival tool for RSS feeds with image downloading and Internet Archive support.

Usage:
    python rssdumper.py https://example.com/feed.xml
"""

import os
import sys
import argparse
import signal
import json
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urlparse

script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# Hybrid imports — work in both script and module mode
try:
    from __version__ import DUMPER_VERSION as UPLOADER_VERSION, rss_dumper_outdated_check
except ImportError:
    from .__version__ import DUMPER_VERSION as UPLOADER_VERSION, rss_dumper_outdated_check

try:
    from utils.exceptions import HTTPStatusError, show_edge_case_warning
except ImportError:
    from .utils.exceptions import HTTPStatusError, show_edge_case_warning

try:
    from utils.config import get_config, update_config
except ImportError:
    from .utils.config import get_config, update_config

try:
    from utils.dump_lock import DumpLock
except ImportError:
    from .utils.dump_lock import DumpLock

try:
    from utils.ia_checker import any_recent_ia_item_exists
except ImportError:
    from .utils.ia_checker import any_recent_ia_item_exists

try:
    from utils.session import create_session
except ImportError:
    from .utils.session import create_session

try:
    from utils.util import smkdirs, standardize_url, print_with_lock as print
except ImportError:
    from .utils.util import smkdirs, standardize_url, print_with_lock as print

try:
    from rssarchiver_core import download_rss_feed
except ImportError:
    from .rssarchiver_core import download_rss_feed


def signal_handler(sig, frame):
    print("\n🛑 Received interrupt. Exiting gracefully...")
    sys.exit(0)


def setup_output_dir(url: str, custom_output: str = None) -> Path:
    """Create dated output directory."""
    if custom_output:
        output_dir = Path(custom_output)
    else:
        domain = urlparse(url).netloc.replace(':', '_')
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # CHANGED: Removed "rss_dump_" prefix
        output_dir = Path(f"{domain}_{timestamp}")

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output directory: {output_dir}")
    return output_dir


def main():
    parser = argparse.ArgumentParser(description="RSS Dumper — Archive RSS feeds with images and IA checks.")
    parser.add_argument("url", help="URL of the RSS feed to archive")
    parser.add_argument("--output", "-o", default=None, help="Custom output directory")
    parser.add_argument("--format", "-f", choices=['json', 'md'], default='json',
                        help="Item output format (default: json)")
    parser.add_argument("--no-ia-check", action="store_true", help="Skip Internet Archive check")
    parser.add_argument("--user-agent", default=None, help="Custom User-Agent header")

    args = parser.parse_args()

    # Check for updates
    try:
        rss_dumper_outdated_check()
    except Exception as e:
        print(f"[!] Version check failed: {e}")

    # Setup signal handler
    signal.signal(signal.SIGINT, signal_handler)

    # Standardize URL
    url = standardize_url(args.url)

    # Setup output dir
    output_dir = setup_output_dir(url, args.output)

    # Acquire lock
    try:
        with DumpLock(str(output_dir)):
            pass
    except Exception as e:
        print(f"[!] {e}")
        sys.exit(1)

    # Check Internet Archive (unless skipped)
    if not args.no_ia_check:
        print("🔍 Checking Internet Archive for recent dumps...")
        if any_recent_ia_item_exists(url, days=365):
            if input("📥 Recent dump found on IA. Continue local dump anyway? (y/N): ").lower() != 'y':
                print("👋 Exiting.")
                sys.exit(0)

    # Create session
    session = create_session(user_agent=args.user_agent)

    # Load existing config
    config = get_config(str(output_dir))
    config.update({
        'source_url': url,
        'UPLOADER_VERSION': UPLOADER_VERSION,
        'started_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'item_format': args.format,
    })

    # Save initial config
    update_config(str(output_dir), config)

    # Download feed + images
    try:
        stats = download_rss_feed(
            url=url,
            output_dir=output_dir,
            session=session,
            item_format=args.format
        )
    except Exception as e:
        print(f"[!] Failed to download feed: {e}")
        show_edge_case_warning(version=UPLOADER_VERSION, error=str(e), url=url)
        sys.exit(1)

    config.update({
        'completed_at': datetime.utcnow().isoformat() + 'Z',
        'items_downloaded': stats.get('items', 0),
        'images_downloaded': stats.get('images', 0),
        'status': 'success' if stats.get('items', 0) > 0 else 'failed'
    })
    update_config(str(output_dir), config)

    print(f"\n✅ Done! Archived {stats.get('items', 0)} items and {stats.get('images', 0)} images.")
    print(f"📂 Output: {output_dir}")
    print(f"📁 Command: python3 -m RSS-Dumper.rssuploader ./{output_dir}")


if __name__ == "__main__":
    main()