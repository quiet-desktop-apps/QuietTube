from io import BytesIO
import threading

from quiettube.models import Video
from quiettube.thumbnails import Thumbnails


def test_thumbnail_cache_is_bounded_and_hits_skip_network(monkeypatch):
    calls = []
    def fetch(request, timeout):
        calls.append(request.full_url)
        return BytesIO(b"image data")
    monkeypatch.setattr("quiettube.thumbnails.urlopen", fetch)
    cache = Thumbnails(lambda callback: callback())
    received = []
    try:
        for index in range(90):
            cache.load(Video(f"{index:011d}", "Test"), received.append)
        for future in cache.futures:
            future.result(timeout=2)
        assert len(received) == 90
        assert len(cache.cache) == cache.LIMIT
        before = len(calls)
        cache.load(Video("00000000089", "Test"), received.append)
        assert len(calls) == before
        assert len(received) == 91
    finally:
        cache.close()


def test_oversized_thumbnail_is_discarded(monkeypatch):
    monkeypatch.setattr("quiettube.thumbnails.urlopen", lambda *_args, **_kwargs: BytesIO(b"x" * (Thumbnails.MAX_BYTES + 1)))
    cache = Thumbnails(lambda callback: callback())
    received = []
    try:
        cache.load(Video("00000000001", "Test"), received.append)
        cache.futures[0].result(timeout=2)
        assert not received
        assert not cache.cache
    finally:
        cache.close()


def test_old_page_download_cannot_update_new_widgets(monkeypatch):
    started, finish = threading.Event(), threading.Event()
    def fetch(*_args, **_kwargs):
        started.set()
        assert finish.wait(timeout=2)
        return BytesIO(b"old thumbnail")
    monkeypatch.setattr("quiettube.thumbnails.urlopen", fetch)
    cache = Thumbnails(lambda callback: callback())
    received = []
    try:
        cache.load(Video("00000000001", "Test"), received.append)
        assert started.wait(timeout=2)
        old = cache.futures[0]
        cache.new_page()
        finish.set()
        old.result(timeout=2)
        assert received == []
        assert len(cache.cache) == 0
    finally:
        finish.set()
        cache.close()
