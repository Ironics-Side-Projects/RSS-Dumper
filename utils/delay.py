import threading
import asyncio

delaying_threads = 0
delaying_threads_lock = threading.Lock()

class Delay:
    done: bool = False
    lock: threading.Lock = threading.Lock()
    delay: float

    async def animate(self):
        while True:
            with self.lock:
                if self.done:
                    return
                with delaying_threads_lock:
                    if delaying_threads == 1:
                        print("\r" + self.ellipses, end="", flush=True)
                self.ellipses += "."
            await asyncio.sleep(0.35)

    def __init__(self, msg=None, delay: float = 0.0):
        if delay <= 0:
            return
        self.ellipses = "."
        self.delay = delay

        with delaying_threads_lock:
            global delaying_threads
            delaying_threads += 1

        if msg:
            self.ellipses = f"Delay {delay:.1f}s: {msg} " + self.ellipses
        else:
            self.ellipses = f"Delay {delay:.1f}s " + self.ellipses

        asyncio.run(self.async_tasks())

    async def async_tasks(self):
        task1 = asyncio.create_task(self.animate())
        task2 = asyncio.create_task(self.task_done())
        await task2
        task1.cancel()

    async def task_done(self):
        await asyncio.sleep(self.delay)
        with self.lock, delaying_threads_lock:
            self.done = True
            global delaying_threads
            delaying_threads -= 1
            if delaying_threads == 0:
                print("\r" + " " * len(self.ellipses) + "\r", end="", flush=True)