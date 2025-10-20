import builtins
import os
import re
import sys
import threading
from typing import Any, Optional, List, Union, overload
from urllib.parse import unquote, urlparse, urljoin

from rich import print as rprint

USE_RICH = True

fileLock = threading.Lock()
printLock = threading.Lock()


@overload
def check_int(s: str) -> Optional[str]: ...
@overload
def check_int(s: int) -> int: ...
@overload
def check_int(s: float) -> float: ...
@overload
def check_int(s: None) -> None: ...
@overload
def check_int(s: Any) -> Optional[Any]: ...

def check_int(s: Union[int, float, str, None, Any]) -> Union[int, float, str, None]:
    try:
        int(s)  # type: ignore
        return s
    except Exception:
        return None


def print_with_lock(*args, **kwargs):
    with printLock:
        if USE_RICH:
            try:
                rich_args = [re.sub(r'```math```math', '"', str(arg)) for arg in args]
                rich_args = [re.sub(r'``````', '"', str(arg)) for arg in rich_args]
                rprint(*rich_args, **kwargs)
            except Exception:
                builtins.print(*args, **kwargs)
        else:
            builtins.print(*args, **kwargs)


def smkdirs(parent: str, *child: str) -> Optional[str]:
    """Safe mkdir. Returns path if created, None if existed."""
    if parent is None:
        raise ValueError('parent must be specified')

    child = [c.lstrip('/') for c in child]
    dir_path = os.path.join(parent, *child)

    with fileLock:
        if not os.path.exists(dir_path):
            os.makedirs(dir_path)
            return dir_path
    return None


def standardize_url(url: str) -> str:
    url = url.strip()
    url = unquote(url, encoding='utf-8', errors='replace')

    if not url.startswith(('http://', 'https://')):
        print('⚠️  URL scheme missing — assuming https://')
        url = 'https://' + url

    parsed = urlparse(url)
    assert parsed.hostname, "Invalid URL — no hostname"

    idna_hostname = parsed.hostname.encode('idna').decode('utf-8')
    if parsed.hostname != idna_hostname:
        print(f'🌍 Converting domain to IDNA: {parsed.hostname} → {idna_hostname}')
        url = url.replace(parsed.hostname, idna_hostname, 1)

    if (parsed.port == 80 and parsed.scheme == 'http') or (parsed.port == 443 and parsed.scheme == 'https'):
        url = url.replace(f':{parsed.port}', '', 1)

    return url


def build_base_url(url: str = '') -> str:
    parsed = urlparse(url)
    path = parsed.path
    if path and path != '/' and not path.endswith('/'):
        path = path[:path.rfind('/') + 1]
    return parsed.scheme + '://' + parsed.netloc + path


def uopen(*args, **kwargs):
    return open(*args, encoding='UTF-8', **kwargs)


class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
        return cls._instances[cls]