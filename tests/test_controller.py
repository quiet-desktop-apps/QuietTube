from quiettube.controller import PlaybackController
from quiettube.player import PlayerEvent
from quiettube.storage import Store
from test_models_storage import video


class FakePlayer:
    def __init__(self):
        self.generation = 0
        self.starts = []
        self.commands = []

    def start(self, *args):
        self.generation += 1
        self.starts.append(args)

    def stop(self):
        self.generation += 1

    def command(self, command):
        self.commands.append(command)


def build(tmp_path):
    store, player = Store(tmp_path), FakePlayer()
    controller = PlaybackController(store, player)
    controller.add(video(1))
    controller.add(video(2))
    controller.play()
    return store, player, controller


def test_eof_advances_and_marks_completed(tmp_path):
    store, player, controller = build(tmp_path)
    controller.event(PlayerEvent(player.generation, "loaded"))
    controller.event(PlayerEvent(player.generation, "time-pos", 120))
    controller.event(PlayerEvent(player.generation, "finished"))
    assert controller.queue.current.video == video(2)
    assert len(player.starts) == 2
    row = store.db.execute("SELECT completed FROM history WHERE video_id=?", (video(1).id,)).fetchone()
    assert row == (1,)
    controller.close()
    store.close()


def test_error_retains_current_position_and_next_items(tmp_path):
    store, player, controller = build(tmp_path)
    controller.event(PlayerEvent(player.generation, "time-pos", 33))
    controller.event(PlayerEvent(player.generation, "error", "Network unavailable"))
    assert controller.state == "error"
    assert controller.queue.current.video == video(1)
    assert controller.queue.current.position == 33
    assert controller.queue.upcoming[0].video == video(2)
    controller.play()
    assert player.starts[-1][1] == 33
    controller.close()
    store.close()


def test_unexpected_disconnect_keeps_queue_and_stale_eof_cannot_skip(tmp_path):
    store, player, controller = build(tmp_path)
    old_generation = player.generation
    controller.event(PlayerEvent(old_generation, "closed"))
    controller.event(PlayerEvent(old_generation, "finished"))
    assert controller.state == "stopped"
    assert controller.queue.current.video == video(1)
    assert len(player.starts) == 1
    controller.close()
    store.close()


def test_pause_seek_skip_and_end_of_queue(tmp_path):
    store, player, controller = build(tmp_path)
    controller.event(PlayerEvent(player.generation, "loaded"))
    controller.play()
    assert player.commands[-1] == ["cycle", "pause"]
    controller.event(PlayerEvent(player.generation, "pause", True))
    assert controller.state == "paused"
    controller.next()
    assert controller.queue.current.video == video(2)
    controller.event(PlayerEvent(player.generation, "finished"))
    assert controller.queue.current is None
    assert controller.state == "stopped"
    controller.close()
    store.close()


def test_playback_progress_does_not_write_database_on_every_event(tmp_path):
    store, player, controller = build(tmp_path)
    before = store.db.total_changes
    for n in range(200):
        controller.event(PlayerEvent(player.generation, "time-pos", n))
    assert store.db.total_changes == before
    controller.checkpoint()
    assert store.load_queue().current.position == 199
    controller.close()
    store.close()


def test_same_video_reopen_and_reload_keep_position_and_queue_identity(tmp_path):
    store, player, controller = build(tmp_path)
    key = controller.queue.current.key
    upcoming = list(controller.queue.upcoming)
    controller.event(PlayerEvent(player.generation, "time-pos", 235.5))
    controller.event(PlayerEvent(player.generation, "closed"))
    controller.play_now(video(1))
    assert player.starts[-1][1] == 235.5
    assert controller.queue.current.key == key
    assert controller.queue.upcoming == upcoming
    controller.reload()
    assert player.starts[-1][1] == 235.5
    assert store.load_queue().current.position == 235.5
    assert controller.queue.upcoming == upcoming
    controller.close()
    store.close()


def test_pause_saves_resume_position_immediately(tmp_path):
    store, player, controller = build(tmp_path)
    controller.event(PlayerEvent(player.generation, "loaded"))
    controller.event(PlayerEvent(player.generation, "time-pos", 95.25))
    controller.event(PlayerEvent(player.generation, "pause", True))
    assert store.load_queue().current.position == 95.25
    controller.close()
    store.close()


def test_personal_oauth_playback_never_receives_saved_browser_credentials(tmp_path):
    store, player, controller = build(tmp_path)
    store.cookie_path.write_text('synthetic browser session')
    store.set('account_mode', 'oauth')
    controller.reload()
    assert player.starts[-1][3] is None
    store.set('account_mode', 'browser')
    controller.reload()
    assert player.starts[-1][3] == store.cookie_path
    controller.close()
    store.close()


def test_playback_verification_preserves_oauth_and_queue_until_explicit_retry(tmp_path):
    store, player, controller = build(tmp_path)
    store.set('account_mode', 'oauth')
    store.set('oauth_authorized', True)
    controller.event(PlayerEvent(player.generation, 'time-pos', 75))
    before = controller.queue.to_dict()
    starts = len(player.starts)
    controller.event(PlayerEvent(player.generation, 'error', 'Verification needed', 'verification'))
    assert controller.error_category == 'verification'
    assert controller.queue.to_dict() == before
    assert store.get('oauth_authorized') and store.get('account_mode') == 'oauth'
    assert len(player.starts) == starts
    controller.reload()
    assert controller.error_category == ''
    assert player.starts[-1][1] == 75 and player.starts[-1][3] is None
    controller.close()
    store.close()


def test_oauth_playback_session_is_explicit_separate_and_persistent(tmp_path):
    store, player, controller = build(tmp_path)
    store.set('account_mode', 'oauth')
    store.set('oauth_authorized', True)
    store.cookie_path.write_text('synthetic feed session')
    store.playback_cookie_path.write_text('synthetic playback session')
    controller.queue.current.position = 31
    before = controller.queue.to_dict()
    controller.reload()
    assert player.starts[-1][3] is None  # a file alone is not consent
    store.set('playback_session_enabled', True)
    controller.reload()
    assert player.starts[-1][1] == 31
    assert player.starts[-1][3] == store.playback_cookie_path
    assert controller.queue.to_dict() == before
    controller.close()
    store.close()
    store = Store(tmp_path)
    controller = PlaybackController(store, player)
    controller.play()
    assert player.starts[-1][3] == store.playback_cookie_path
    store.set('playback_session_enabled', False)
    controller.reload()
    assert player.starts[-1][3] is None
    store.set('account_mode', 'browser')
    controller.reload()
    assert player.starts[-1][3] == store.cookie_path
    assert store.get('oauth_authorized')
    controller.close()
    store.close()


def test_history_observations_flush_old_video_before_queue_transition(tmp_path):
    store, player, controller = build(tmp_path)
    events = []
    controller.observe = events.append
    controller.event(PlayerEvent(player.generation, 'loaded'))
    controller.event(PlayerEvent(player.generation, 'time-pos', 22))
    controller.event(PlayerEvent(player.generation, 'pause', True))
    assert events[-1].kind == 'pause' and events[-1].position == 22
    assert not events[-1].playing
    old = controller.queue.current.video.id
    controller.event(PlayerEvent(player.generation, 'finished'))
    assert events[-2].kind == 'boundary' and events[-2].video_id == old
    assert events[-2].position == 22
    assert events[-1].kind == 'start' and events[-1].video_id != old
    count = len(events)
    controller.event(PlayerEvent(player.generation - 1, 'time-pos', 900))
    assert len(events) == count
    controller.close(); store.close()


def test_explicit_close_finishes_live_item_once_and_persists_next(tmp_path):
    from quiettube.models import Video
    store, player, controller = build(tmp_path)
    live = Video('livestream1', 'Synthetic live stream', duration=0)
    controller.queue.current.video = live
    controller.event(PlayerEvent(player.generation, 'loaded'))
    controller.event(PlayerEvent(player.generation, 'time-pos', 42))
    generation = player.generation
    controller.event(PlayerEvent(generation, 'dismissed'))
    assert controller.queue.current.video == video(2)
    assert store.load_queue().current.video == video(2)
    assert live.id in store.completed_ids()
    assert store.db.execute('SELECT position FROM history WHERE video_id=?', (live.id,)).fetchone() == (42,)
    assert len(player.starts) == 2
    for kind in ('dismissed', 'closed', 'finished', 'error'):
        controller.event(PlayerEvent(generation, kind))
    assert controller.queue.current.video == video(2) and len(player.starts) == 2
    controller.close(); store.close()
    store = Store(tmp_path)
    controller = PlaybackController(store, player)
    controller.play()
    assert controller.queue.current.video == video(2)
    assert live.id in store.completed_ids()
    controller.close(); store.close()


def test_close_last_item_finishes_without_reopening_and_reports_actual_position(tmp_path):
    store, player, controller = build(tmp_path)
    controller.queue.upcoming.clear()
    observations = []
    controller.observe = observations.append
    controller.event(PlayerEvent(player.generation, 'loaded'))
    controller.event(PlayerEvent(player.generation, 'time-pos', 12))
    controller.event(PlayerEvent(player.generation, 'dismissed'))
    assert controller.queue.current is None and controller.state == 'stopped'
    assert store.load_queue().current is None
    assert video(1).id in store.completed_ids()
    assert observations[-1].kind == 'boundary' and observations[-1].position == 12
    controller.play()
    assert len(player.starts) == 1
    controller.close(); store.close()


def test_pause_stop_reload_and_app_shutdown_never_finish_current(tmp_path):
    store, player, controller = build(tmp_path)
    controller.event(PlayerEvent(player.generation, 'loaded'))
    controller.event(PlayerEvent(player.generation, 'time-pos', 60))
    controller.event(PlayerEvent(player.generation, 'pause', True))
    before = controller.queue.to_dict()
    controller.stop()
    assert store.load_queue().to_dict() == before
    controller.reload()
    assert player.starts[-1][1] == 60
    controller.close()
    assert store.load_queue().to_dict() == before
    assert not store.completed_ids()
    store.close()


def test_explicit_restart_discards_only_current_resume_point(tmp_path):
    store, player, controller = build(tmp_path)
    controller.event(PlayerEvent(player.generation, 'time-pos', 6569))
    controller.event(PlayerEvent(player.generation, 'error', 'Unavailable'))
    old_generation = player.generation
    key = controller.queue.current.key
    upcoming = [item.to_dict() for item in controller.queue.upcoming]
    controller.restart_current()
    assert player.starts[-1][1] == 0
    assert controller.queue.current.key == key
    assert controller.queue.current.position == 0
    assert store.load_queue().current.position == 0
    assert [item.to_dict() for item in controller.queue.upcoming] == upcoming
    assert not store.completed_ids()
    controller.event(PlayerEvent(old_generation, 'error', 'Stale failure'))
    assert controller.state == 'loading'
    controller.close(); store.close()
