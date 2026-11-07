from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import threading
from urllib.request import Request, urlopen


class Thumbnails:
    """At most 64 compressed thumbnails and two network requests at a time."""
    LIMIT = 64
    MAX_BYTES = 192 * 1024

    def __init__(self, dispatch):
        self.dispatch = dispatch
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="thumbnail")
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        self.futures = []
        self.generation = 0
        self.closed = False

    def new_page(self):
        self.generation += 1
        for future in self.futures:
            future.cancel()
        self.futures.clear()

    def load(self, video, callback):
        if self.closed:
            return
        generation = self.generation
        with self.lock:
            data = self.cache.get(video.id)
            if data:
                self.cache.move_to_end(video.id)
        if data:
            callback(data)
            return

        def fetch():
            try:
                with urlopen(Request(video.thumbnail, headers={"User-Agent": "QuietTube/0.1"}), timeout=8) as response:
                    data = response.read(self.MAX_BYTES + 1)
                    if len(data) > self.MAX_BYTES:
                        return
                with self.lock:
                    if self.closed or generation != self.generation:
                        return
                    self.cache[video.id] = data
                    self.cache.move_to_end(video.id)
                    while len(self.cache) > self.LIMIT:
                        self.cache.popitem(last=False)

                def deliver():
                    if not self.closed and generation == self.generation:
                        callback(data)
                    return False
                self.dispatch(deliver)
            except (OSError, ValueError):
                pass  # a missing thumbnail must never prevent playback
        self.futures.append(self.pool.submit(fetch))

    def close(self):
        self.closed = True
        self.new_page()
        self.pool.shutdown(wait=False, cancel_futures=True)
        with self.lock:
            self.cache.clear()
