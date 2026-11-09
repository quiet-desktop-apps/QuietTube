"""Bounded, best-effort progress sharing. Playback never waits for the network."""
from collections import OrderedDict
from dataclasses import dataclass
import time

from .tasks import ExtractorTasks


@dataclass(frozen=True)
class PlaybackObservation:
    key: str
    video_id: str
    position: float
    playing: bool
    kind: str


class HistorySync:
    INTERVAL = 30
    MAX_PENDING = 5

    def __init__(self, store, dispatch, status=lambda text: None, clock=time.monotonic, tasks=None):
        self.store, self.status, self.clock = store, status, clock
        self.tasks = tasks or ExtractorTasks(lambda result: dispatch(self.on_result, result), timeout=30)
        self.pending = OrderedDict()
        self.inflight = None
        self.current = None
        self.last_sample = self.clock()
        self.last_attempt = self.clock()
        self.last_position_sent = None
        self.watched = 0.0
        self.closed = False

    def enabled(self):
        return bool(self.store.get('share_watch_history', False))

    def observe(self, event: PlaybackObservation):
        if self.closed or not self.enabled():
            return
        now = self.clock()
        previous = self.current
        if not previous or previous.key != event.key or event.kind == 'start':
            self.watched = 0.0
            self.last_attempt = now
            self.last_position_sent = None
        elif event.kind == 'position' and previous.playing and event.playing:
            delta, elapsed = event.position - previous.position, now - self.last_sample
            # A seek, stalled process or overnight pause must not manufacture watch time.
            if 0 < delta <= min(10, max(0, elapsed) * 4 + .5):
                self.watched += delta
        self.current, self.last_sample = event, now
        explicit = event.kind == 'share'
        boundary = event.kind in {'pause', 'boundary'}
        if (explicit or self.watched >= 1) and event.position > 0:
            if explicit or boundary or now - self.last_attempt >= self.INTERVAL:
                if explicit or self.last_position_sent != event.position:
                    self.enqueue(event)
                    self.last_attempt = now
                    self.last_position_sent = event.position

    def enqueue(self, event):
        session = self.store.playback_session()
        if not session or not session.is_file():
            self.status('History not sent · connect playback')
            return
        # Capture which session this update belongs to; account changes call reset.
        self.pending[event.video_id] = {'action': 'history_sync', 'video_id': event.video_id,
                                       'position': event.position, 'session': str(session)}
        self.pending.move_to_end(event.video_id)
        while len(self.pending) > self.MAX_PENDING:
            self.pending.popitem(last=False)
        self.pump()

    def pump(self):
        if self.closed or self.inflight or not self.pending or not self.enabled():
            return
        _, self.inflight = self.pending.popitem(last=False)
        self.status('Sharing watch history…')
        self.tasks.submit(self.inflight)

    def on_result(self, result):
        if self.closed or result.generation != self.tasks.generation or not self.inflight:
            return False
        sent, self.inflight = self.inflight, None
        data = result.data or {}
        if (not result.error and data.get('history_sent') is True
                and data.get('video_id') == sent['video_id']):
            # HTTP acceptance is not a per-update read-back verification.
            self.status('History update sent · resume on YouTube may take time')
        else:
            self.status('History update failed · playback continues')
            # No retry loop and no replay of stale positions after a restart.
        self.pump()
        return False

    def reset(self):
        self.tasks.cancel()
        self.pending.clear()
        self.inflight = self.current = None
        self.watched = 0
        self.last_position_sent = None

    def close(self):
        # Pause/Stop normally deliver before close. Give the in-flight final update
        # a bounded chance; do not freeze shutdown on network failure.
        if self.tasks.thread:
            self.tasks.thread.join(timeout=3)
        self.closed = True
        self.tasks.close()
        self.pending.clear()
        self.inflight = None
