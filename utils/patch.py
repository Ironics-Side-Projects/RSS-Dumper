import requests
from .delay import Delay

class SessionMonkeyPatch:
    """Monkey patch `requests.Session.send` to add delay and hard retries."""

    def __init__(self, session: requests.Session, msg=None, delay: float = 0.0, hard_retries=3):
        self.session = session
        self.msg = msg
        self.delay = delay
        self.hard_retries = hard_retries
        self.old_send_method = None

    def hijack(self):
        self.old_send_method = self.session.send

        def new_send(request, **kwargs):
            retries = self.hard_retries + 1
            while retries > 0:
                try:
                    if self.delay > 0:
                        Delay(msg=self.msg, delay=self.delay)
                    return self.old_send_method(request, **kwargs)
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    retries -= 1
                    if retries <= 0:
                        raise e
                    print(f'🔁 Hard retry ({retries}) due to: {e}')

        self.session.send = new_send

    def release(self):
        if self.old_send_method:
            self.session.send = self.old_send_method