import requests
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

def create_session(retries=5, user_agent=None) -> requests.Session:
    session = requests.Session()

    class CustomRetry(Retry):
        def sleep(self, response=None):
            retry_after = self.get_retry_after(response)
            backoff = self.get_backoff_time()
            delay_sec = retry_after if retry_after is not None else backoff
            msg = f'Retrying in {delay_sec:.2f}s' if response is None else f'Retrying ({response.status_code}) in {delay_sec:.2f}s'
            print(msg)
            super().sleep(response=response)

    retry_strategy = CustomRetry(
        total=retries,
        backoff_factor=1.5,
        status_forcelist=[500, 502, 503, 504, 429],
        allowed_methods=["HEAD", "GET", "OPTIONS", "POST"],
    )

    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    if user_agent:
        session.headers.update({'User-Agent': user_agent})
    else:
        session.headers.update({'User-Agent': 'RSSDumper/1.1.0 (+https://github.com/Ironics-Side-Projects/RSS-Dumper)'})

    print('User-Agent:', session.headers['User-Agent'])
    return session