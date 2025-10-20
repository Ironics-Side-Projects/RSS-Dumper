import os
import traceback

class VersionOutdatedError(Exception):
    """Raised when RSS Dumper is outdated."""
    def __init__(self, version):
        self.version = version

    def __str__(self):
        return f"RSS Dumper is outdated: {self.version}"


class HTTPStatusError(Exception):
    """Raised when HTTP response has unexpected status code."""
    def __init__(self, status_code, url):
        self.status_code = status_code
        self.url = url

    def __str__(self):
        return f"HTTP Status Code: {self.status_code}, URL: {self.url}"


class DispositionHeaderMissingError(Exception):
    """Raised when Content-Disposition header is missing (for file downloads)."""
    def __init__(self, url):
        self.url = url

    def __str__(self):
        return f"Content-Disposition header missing, URL: {self.url}"


def show_edge_case_warning(version: str = "unknown", **context):
    if os.environ.get('EDGECASE_OK'):
        return

    print(
        "[WARNING]\n"
        "--------------------------------------------\n"
        "The program is about to enter an edge case code, "
        "which lacks real world testing. I'm not sure if the next code will handle it properly.\n"
        "Please paste the following details to help improve RSS Dumper:\n"
        "→ https://github.com/Ironics-Side-Projects/RSS-Dumper/discussions\n"
        "Thanks!"
    )
    print("------------------------------------------")
    calledfrom = traceback.extract_stack(limit=2)[0]
    print("VERSION:", version)  # ← Passed in from caller
    print("LOCATION:", f'{calledfrom.filename}:{calledfrom.lineno}')
    print("FUNCTION:", calledfrom.name)
    print("CONTEXT:", context)
    print("------------------------------------------")
    print("To continue anyway, re-run with: EDGECASE_OK=1")
    os._exit(13)