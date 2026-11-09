from quiettube.history_sync import HistorySync, PlaybackObservation
from quiettube.storage import Store
from quiettube.tasks import TaskResult


class Tasks:
    def __init__(self):
        self.generation = 0
        self.requests = []
        self.thread = None
        self.closed = False
    def submit(self, request):
        self.generation += 1
        self.requests.append(request)
    def cancel(self): self.generation += 1
    def close(self): self.closed = True; self.cancel()


def build(tmp_path):
    store = Store(tmp_path)
    store.set('account_mode', 'oauth')
    store.set('playback_session_enabled', True)
    store.playback_cookie_path.write_text('synthetic')
    tasks, clock, statuses = Tasks(), [0], []
    sync = HistorySync(store, lambda fn, *args: fn(*args), statuses.append, lambda: clock[0], tasks)
    return store, sync, tasks, clock, statuses


def observe(sync, clock, position, kind='position', playing=True, key='one', ident='jNQXAC9IVRw'):
    clock[0] += 1
    sync.observe(PlaybackObservation(key, ident, position, playing, kind))


def finish(sync, tasks, **fields):
    sync.on_result(TaskResult(tasks.generation, {'history_sent': True, 'video_id': 'jNQXAC9IVRw', **fields}))


def test_opt_in_actual_playback_throttle_and_pause(tmp_path):
    store, sync, tasks, clock, statuses = build(tmp_path)
    observe(sync, clock, 123, 'share', False)
    assert not tasks.requests
    store.set('share_watch_history', True)
    observe(sync, clock, 0, 'start', False)
    observe(sync, clock, 0, 'loaded')
    for position in range(1, 31): observe(sync, clock, position)
    assert len(tasks.requests) == 1
    assert tasks.requests[0]['position'] < 31
    assert tasks.requests[0]['session'] == str(store.playback_cookie_path)
    assert 'account_mode' not in tasks.requests[0]
    finish(sync, tasks)
    observe(sync, clock, 31)
    observe(sync, clock, 31, 'pause', False)
    assert tasks.requests[-1]['position'] == 31
    finish(sync, tasks)
    clock[0] += 86400
    observe(sync, clock, 31, 'pause', False)
    assert len(tasks.requests) == 2
    assert 'sent' in statuses[-1]
    sync.close(); store.close()


def test_loading_failure_and_seek_are_not_watches(tmp_path):
    store, sync, tasks, clock, _ = build(tmp_path)
    store.set('share_watch_history', True)
    observe(sync, clock, 0, 'start', False)
    observe(sync, clock, 0, 'boundary', False)
    assert not tasks.requests
    observe(sync, clock, 0, 'loaded')
    observe(sync, clock, 500)
    observe(sync, clock, 500, 'pause', False)
    assert not tasks.requests
    # Resuming a genuinely played range reports the position, never the skipped gap.
    observe(sync, clock, 500, 'resume')
    observe(sync, clock, 501)
    observe(sync, clock, 502, 'pause', False)
    assert tasks.requests[-1]['position'] == 502
    sync.close(); store.close()


def test_coalesces_without_cancelling_inflight_and_ignores_stale(tmp_path):
    store, sync, tasks, clock, _ = build(tmp_path)
    store.set('share_watch_history', True)
    observe(sync, clock, 10, 'share')
    observe(sync, clock, 20, 'share')
    observe(sync, clock, 30, 'share')
    assert len(tasks.requests) == 1
    assert len(sync.pending) == 1
    sync.on_result(TaskResult(tasks.generation-1, {'history_sent':True}))
    assert sync.inflight['position'] == 10
    finish(sync, tasks)
    assert len(tasks.requests) == 2 and tasks.requests[-1]['position'] == 30
    store.set('share_watch_history', False)
    sync.reset()
    finish(sync, tasks)
    assert not sync.pending and sync.inflight is None
    observe(sync, clock, 45, 'share')
    assert len(tasks.requests) == 2
    sync.close(); store.close()


def test_no_missing_session_no_retries_and_bounded_pending(tmp_path):
    store, sync, tasks, clock, statuses = build(tmp_path)
    store.set('share_watch_history', True)
    store.playback_cookie_path.unlink()
    observe(sync, clock, 20, 'share')
    assert not tasks.requests and 'connect playback' in statuses[-1]
    store.playback_cookie_path.write_text('synthetic')
    observe(sync, clock, 20, 'share')
    sync.on_result(TaskResult(tasks.generation, error='failure'))
    assert len(tasks.requests) == 1
    assert 'failed' in statuses[-1]
    observe(sync, clock, 21, 'share')
    for n in range(100): observe(sync, clock, 22, 'share', key=str(n), ident=str(n))
    assert len(sync.pending) == sync.MAX_PENDING
    assert len(tasks.requests) == 2
    sync.close(); store.close()
