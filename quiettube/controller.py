from __future__ import annotations

from .models import Video, finite_seconds
from .player import PlayerEvent


class PlaybackController:
    """Owns queue transitions. Only an explicit EOF event automatically advances."""

    def __init__(self, store, player, changed=lambda: None):
        self.store = store
        self.player = player
        self.changed = changed
        self.queue = store.load_queue()
        self.state = "stopped"
        self.error = ""
        self.duration = 0.0
        self.height = store.get("quality", 720)
        if self.height not in {480, 720, 1080, 1440, 2160}:
            self.height = 720
        self.volume = min(100, max(0, finite_seconds(store.get("volume", 70))))

    def save(self):
        self.store.save_queue(self.queue)

    def add(self, video: Video, index=None):
        self.queue.add(video, index)
        self.save()
        self.changed()

    def remove(self, key):
        self.queue.remove(key)
        self.save()
        self.changed()

    def move(self, key, index):
        self.queue.move(key, index)
        self.save()
        self.changed()

    def play_now(self, video):
        if self.queue.current and self.queue.current.video.id == video.id:
            # Reopening the current video is a resume, not a duplicate at zero.
            self._start()
            return
        self.queue.play_now(video)
        self._start()

    def reload(self):
        if self.queue.current:
            self._start()

    def play(self):
        if self.state in {"playing", "paused"}:
            self.player.command(["cycle", "pause"])
        elif self.state != "loading":
            if not self.queue.current:
                self.queue.advance()
            self._start()

    def _start(self):
        self.error = ""
        self.duration = 0
        self.save()
        if not self.queue.current:
            self.player.stop()
            self.state = "stopped"
        else:
            self.state = "loading"
            item = self.queue.current
            self.player.start(item.video.url, item.position, self.height, self.store.cookie_path)
        self.changed()

    def next(self, completed=False):
        if self.queue.current:
            item = self.queue.current
            self.store.record(item.video, item.position, completed)
        self.queue.advance()
        self._start()

    def stop(self):
        self.player.stop()
        self.state = "stopped"
        self.save()
        self.changed()

    def event(self, event: PlayerEvent):
        if event.generation != self.player.generation or not self.queue.current:
            return
        if event.kind == "time-pos":
            self.queue.current.position = finite_seconds(event.value)
        elif event.kind == "duration":
            self.duration = finite_seconds(event.value)
        elif event.kind == "loaded":
            self.state = "playing"
            self.player.command(["set_property", "volume", self.volume])
        elif event.kind == "pause" and self.state in {"playing", "paused"}:
            self.state = "paused" if event.value else "playing"
            self.save()
        elif event.kind == "finished":
            self.next(completed=True)
            return
        elif event.kind == "error":
            self.player.stop()
            self.state = "error"
            self.error = str(event.value)
            self.save()
        elif event.kind == "closed":
            self.player.stop()
            self.state = "stopped"
            self.save()
        self.changed()

    def checkpoint(self):
        self.save()
        if self.queue.current:
            item = self.queue.current
            self.store.record(item.video, item.position)

    def close(self):
        self.checkpoint()
        self.player.stop()
