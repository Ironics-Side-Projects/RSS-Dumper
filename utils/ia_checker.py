import datetime
import logging
from typing import List, Optional
import urllib.parse

from internetarchive import ArchiveSession, Search

IA_MAX_RETRY = 5
logger = logging.getLogger(__name__)


def ia_s3_tasks_load_avg(session: ArchiveSession) -> float:
    api = "https://s3.us.archive.org/?check_limit=1"
    r = session.get(api, timeout=16)
    r.raise_for_status()
    r_json = r.json()
    total_tasks_queued = r_json["detail"]["total_tasks_queued"]
    total_global_limit = r_json["detail"]["total_global_limit"]
    logger.info(f"IA S3 Load Avg: {total_tasks_queued} / {total_global_limit}")
    return total_tasks_queued / total_global_limit

def search_ia(ori_url: str, addeddate_intervals: Optional[List[str]] = None):
    ia_session = ArchiveSession()

    subject = 'RSSDumper'
    ori_url = ori_url.lower()
    domain = urllib.parse.urlparse(ori_url).netloc.lower()

    # URL variants
    variants = [
        ori_url,
        ori_url.rstrip('/'),
        ori_url.rstrip('/') + '/',
    ]

    # Add parent path variant
    parsed = urllib.parse.urlparse(ori_url)
    if parsed.path and parsed.path != '/':
        parent_path = parsed.path.rsplit('/', 1)[0] or '/'
        parent_url = urllib.parse.urlunparse((
            parsed.scheme, parsed.netloc, parent_path, '', '', ''
        ))
        variants.extend([
            parent_url,
            parent_url.rstrip('/'),
            parent_url.rstrip('/') + '/',
        ])

    # Remove duplicates
    variants = list(set(variants))

    # Build query
    url_conditions = " OR ".join([f'originalurl:"{v}"' for v in variants])
    identifier_condition = f'identifier:"rss-*{domain}*"'

    query = f'(subject:"{subject}" AND ({url_conditions} OR {identifier_condition}))'

    if addeddate_intervals:
        query += f' AND addeddate:[{addeddate_intervals[0]} TO {addeddate_intervals[1]}]'

    search = Search(
        ia_session, query=query,
        fields=['identifier', 'addeddate', 'title', 'subject', 'originalurl', 'uploader', 'item_size'],
        sorts=['addeddate desc'],
        max_retries=IA_MAX_RETRY,
    )

    for result in search:
        original_url_stored = result.get('originalurl', '').lower()
        normalized_ori = ori_url.rstrip('/')
        normalized_stored = original_url_stored.rstrip('/')

        # Match conditions
        exact_match = normalized_ori == normalized_stored
        parent_match = (
            normalized_ori.startswith(normalized_stored + '/') or
            normalized_stored == normalized_ori.rsplit('/', 1)[0]
        )
        identifier_match = domain in result.get('identifier', '').lower()

        if exact_match or parent_match or identifier_match:
            logger.info(f'Match found: {result}')
            yield result
        else:
            logger.warning(f'No match: stored={normalized_stored}, searching={normalized_ori}, identifier={result.get("identifier")}')

def search_ia_recent(ori_url: str, days: int = 365):
    now_utc = datetime.datetime.utcnow()
    now_utc_iso = now_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    one_year_ago = now_utc - datetime.timedelta(days=days)
    one_year_ago_iso = one_year_ago.strftime("%Y-%m-%dT%H:%M:%SZ")

    yield from search_ia(ori_url, [one_year_ago_iso, now_utc_iso])


def any_recent_ia_item_exists(ori_url: str, days: int = 365) -> bool:
    for item in search_ia_recent(ori_url, days):
        print('✅ Found existing dump at Internet Archive:')
        print(item)
        print(f'https://archive.org/details/{item["identifier"]}')
        return True
    return False


def search_ia_all(ori_url: str):
    yield from search_ia(ori_url)