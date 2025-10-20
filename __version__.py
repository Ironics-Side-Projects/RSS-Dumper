DUMPER_VERSION = '1.3.2'

try:
    from utils.exceptions import VersionOutdatedError
except ImportError:
    from .utils.exceptions import VersionOutdatedError


def get_latest_version():
    '''Returns the latest version of RSS Dumper.'''
    project_url_github = 'https://api.github.com/repos/Ironics-Side-Projects/RSS-Dumper/releases/latest'

    import requests
    try:
        response = requests.get(project_url_github, timeout=5, headers={'Accept': 'application/json'})
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        print('Warning: Could not get latest version of RSS Dumper from GitHub. (Timeout or connection error)')
        return None

    if response.status_code == 200:
        data = response.json()
        latest_version = data.get('tag_name', '').lstrip('v')
        return latest_version
    else:
        print(f'Warning: Could not get latest version of RSS Dumper (HTTP {response.status_code}).')
        return None


def rss_dumper_outdated_check():
    latest_version = get_latest_version()
    if latest_version is None:
        return

    if latest_version != DUMPER_VERSION:
        print('=' * 47)
        print(f'Warning: You are using an outdated version of RSS Dumper ({DUMPER_VERSION}).')
        print(f'         The latest version is {latest_version}.')
        print(f'         Update with: pip3 install --upgrade rss-dumper')
        print('=' * 47, end='\n\n')
        raise VersionOutdatedError(version=DUMPER_VERSION)

    print(f'You are using the latest version of RSS Dumper.')