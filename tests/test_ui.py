import os
from pathlib import Path
import time
from uuid import uuid4

import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("DISPLAY"), reason="Run with xvfb-run for GTK integration tests")


def drain():
    from gi.repository import GLib
    for _ in range(20):
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        time.sleep(0.005)


@pytest.fixture
def window(tmp_path, monkeypatch):
    from quiettube.ui import QuietTubeApp
    monkeypatch.setattr("quiettube.ui.suggested_profile", lambda browser: "")
    app = QuietTubeApp(tmp_path, demo=True)
    app.set_application_id("ch.aboimpinto.QuietTube.Test" + uuid4().hex)
    app.register(None)
    app.activate()
    drain()
    yield app.window
    app.window.close()
    drain()
    app.quit()


def test_native_window_queue_controls_and_middle_insertion(window):
    from quiettube.ui import DEMO_VIDEOS
    initial = list(window.controller.queue.upcoming)
    window.queue_list.select_row(window.queue_list.get_row_at_index(1))
    window.insert_selected(DEMO_VIDEOS[0])
    items = window.controller.queue.upcoming
    assert items[0].key == initial[0].key
    assert items[1].video == DEMO_VIDEOS[0]
    assert items[2].key == initial[1].key
    window.queue_list.select_row(window.queue_list.get_row_at_index(1))
    window.move_selected(1)
    assert window.controller.queue.upcoming[2].video == DEMO_VIDEOS[0]
    window.move_position.set_value(1)
    window.move_to_position()
    assert window.controller.queue.upcoming[0].video == DEMO_VIDEOS[0]
    window.remove_selected()
    assert len(window.controller.queue.upcoming) == len(initial)


def test_demo_search_and_no_account_access(window):
    window.search_entry.set_text("animation")
    window.search()
    assert len(window.videos) == 2
    window.open_account()
    assert window.account_window is None
    assert not window.store.cookie_path.exists()


def test_quality_and_volume_persist(window):
    window.quality.set_selected(2)
    window.volume.set_value(32)
    assert window.store.get("quality") == 1080
    assert window.store.get("volume") == 32


def test_reload_control_preserves_position_and_queue(window):
    from test_controller import FakePlayer
    from quiettube.ui import DEMO_VIDEOS
    window.demo = False
    window.player = window.controller.player = FakePlayer()
    window.controller.play_now(DEMO_VIDEOS[0])
    window.controller.queue.current.position = 71.5
    key = window.controller.queue.current.key
    upcoming = list(window.controller.queue.upcoming)
    window.reload_video_button.emit("clicked")
    assert window.player.starts[-1][1] == 71.5
    assert window.controller.queue.current.key == key
    assert window.controller.queue.upcoming == upcoming


def test_wall_defaults_to_newest_and_hides_completed_on_refresh(window):
    from quiettube.models import Video
    old = Video("11111111111", "Old", published="20260101")
    new = Video("22222222222", "New", published="20261101")
    unknown = Video("33333333333", "Unknown")
    window.store.record(new, 120, completed=True)
    window.show_videos([unknown, old, new])
    assert window.videos == [old, unknown]
    window.show_videos([unknown, old, new])  # Refresh can return the same server results.
    assert window.videos == [old, unknown]
    window.hide_watched.set_active(False)
    assert window.videos == [new, old, unknown]
    assert new.id in window.watched_ids
    window.wall_order.set_selected(1)
    assert window.videos == [unknown, old, new]
    assert window.store.get("wall_newest") is False
    assert window.store.get("wall_hide_watched") is False


def test_fully_watched_page_keeps_pagination_and_can_be_shown_again(window):
    from quiettube.models import Video
    video = Video("11111111111", "Completed")
    window.store.record(video, 30, completed=True)
    window.has_more = True
    window.show_videos([video])
    assert window.videos == []
    assert window.next_button.get_sensitive()
    assert "1 watched hidden" in window.page_label.get_text()
    window.hide_watched.set_active(False)
    assert window.videos == [video]
    assert window.has_more


@pytest.mark.parametrize("feed", ["history", "playlist", "search", "video", "later", "liked"])
def test_wall_options_do_not_hide_or_reorder_other_feeds(window, feed):
    from quiettube.models import Video
    old = Video("11111111111", "Old", published="20260101")
    new = Video("22222222222", "New", published="20261101")
    window.store.record(old, 120, completed=True)
    window.feed = feed
    window.show_videos([old, new])
    assert window.videos == [old, new]
    assert not window.wall_controls.get_visible()


def test_eof_hides_finished_video_but_errors_and_stale_events_do_not(window):
    from quiettube.models import Video
    from quiettube.player import PlayerEvent
    from test_controller import FakePlayer
    first, second = Video("11111111111", "First"), Video("22222222222", "Second")
    player = FakePlayer()
    window.player = window.controller.player = player
    window.controller.queue.upcoming.clear()
    window.controller.play_now(first)
    window.show_videos([first, second])
    window.on_player(PlayerEvent(player.generation - 1, "finished"))
    assert window.videos == [first, second]
    window.on_player(PlayerEvent(player.generation, "error", "Offline"))
    assert window.videos == [first, second]
    assert window.store.completed_ids() == set()
    window.controller.play()
    window.on_player(PlayerEvent(player.generation, "finished"))
    assert window.videos == [second]
    assert window.store.completed_ids() == {first.id}


def test_rendered_window_screenshot(window):
    from PIL import ImageGrab
    drain()
    if os.environ.get("QUIETTUBE_SCREENSHOT"):
        target = Path(os.environ["QUIETTUBE_SCREENSHOT"])
        target.parent.mkdir(parents=True, exist_ok=True)
        ImageGrab.grab(bbox=(0, 0, window.get_width(), window.get_height()),
                       xdisplay=os.environ["DISPLAY"]).save(target)
    assert window.get_width() >= 1000
    assert window.get_height() >= 660


def test_real_account_screen_opens_without_reading_browser(window):
    window.demo = False
    window.open_account()
    drain()
    assert window.account_window is not None
    assert window.pending != "connect"
    assert not window.store.cookie_path.exists()
    window.account_window.close()


def test_search_and_link_requests_use_the_expected_feed(window, monkeypatch):
    window.demo = False
    requests = []
    monkeypatch.setattr(window.tasks, "submit", lambda request: requests.append(request))
    window.search_entry.set_text("native Linux video")
    window.search()
    assert requests[-1]["kind"] == "search"
    window.search_entry.set_text("https://youtu.be/jNQXAC9IVRw?t=42")
    window.search()
    assert requests[-1]["kind"] == "video"
    assert requests[-1]["query"] == "jNQXAC9IVRw"
    window.search_entry.set_text("https://www.youtube.com/playlist?list=PL_test")
    window.search()
    assert requests[-1]["kind"] == "playlist"
    count = len(requests)
    window.search_entry.set_text("https://attacker.example/video")
    window.search()
    assert len(requests) == count


def test_account_failure_visible_and_cancellation_does_not_connect(window, monkeypatch):
    from quiettube.tasks import TaskResult
    window.demo = False
    monkeypatch.setattr(window.tasks, "submit", lambda request: None)
    window.open_account()
    window.connect_browser()
    assert window.pending == "connect"
    assert not window.account_actions.get_sensitive()
    window.on_result(TaskResult(window.tasks.generation, error="Session expired"))
    assert window.account_progress.get_text() == "Session expired"
    assert window.account_actions.get_sensitive()
    assert not window.store.cookie_path.exists()
    window.connect_browser()
    window.account_window.close()
    assert window.pending == ""
    assert not window.busy


def test_disconnect_removes_session_and_feed_but_preserves_local_queue(window):
    window.demo = False
    window.store.cookie_path.write_text("synthetic fixture, not a real cookie")
    count = len(window.controller.queue.upcoming)
    window.open_account()
    window.disconnect()
    assert not window.store.cookie_path.exists()
    assert not window.videos
    assert len(window.controller.queue.upcoming) == count
    assert window.account_button.get_label() == "Connect YouTube"


def test_stale_feed_response_cannot_replace_current_page(window):
    from quiettube.tasks import TaskResult
    original = list(window.videos)
    window.tasks.cancel()
    window.on_result(TaskResult(window.tasks.generation - 1, {"videos": [], "ok": True}))
    assert window.videos == original


def test_repeated_feed_replacement_has_bounded_memory(tmp_path):
    import subprocess
    import sys
    result = subprocess.run([sys.executable, "scripts/memory_check.py"], capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr


def test_card_menu_action_inserts_and_closes_popover(window):
    import gc
    flow = window.feed_container.get_first_child()
    card = flow.get_child_at_index(0).get_child()
    menu = card.get_first_child().get_last_child().get_last_child()
    popover = menu.get_popover()
    popover.popup()
    drain()
    gc.collect()
    before = len(window.controller.queue.upcoming)
    popover.get_child().get_first_child().emit("clicked")
    drain()
    assert len(window.controller.queue.upcoming) == before + 1
    assert not popover.get_visible()


def test_preview_keeps_16_9_and_actions_overlay_thumbnail(window):
    from gi.repository import Gtk
    for width in (1380, 1900):
        window.set_default_size(width, 880)
        drain()
        card = window.feed_container.get_first_child().get_child_at_index(0).get_child()
        preview = card.get_first_child()
        picture = preview.get_child()
        assert abs(picture.get_height() - picture.get_width() * 9 / 16) <= 1
        actions = preview.get_last_child()
        assert actions.get_orientation() == Gtk.Orientation.VERTICAL
        assert actions.get_halign() == Gtk.Align.END
        action_bounds = actions.compute_bounds(preview)[1]
        assert action_bounds.get_y() + action_bounds.get_height() <= preview.get_height()
        before = len(window.controller.queue.upcoming)
        actions.get_first_child().get_next_sibling().emit("clicked")
        assert len(window.controller.queue.upcoming) == before + 1


def test_wide_windows_add_columns_without_enlarging_previews(window):
    from quiettube.models import Video
    from quiettube.ui import VIDEO_CARD_WIDTH
    window.show_videos([Video(f"{n:011d}", f"Video {n}", "Layout fixture", 120) for n in range(30)])
    measurements = []
    for width in (1380, 1920, 2560, 3440, 5120, 1380):
        window.set_default_size(width, 880)
        drain()
        assert window.get_width() >= width - 32, "Run this layout check on a 5120px virtual display (./test.sh)."
        flow = window.feed_container.get_first_child()
        cards = [flow.get_child_at_index(n).get_child() for n in range(30)]
        positions = [card.compute_bounds(flow)[1] for card in cards]
        columns = sum(abs(rect.get_y() - positions[0].get_y()) < 1 for rect in positions)
        preview_widths = [card.get_first_child().get_child().get_width() for card in cards]
        # get_width excludes CSS padding/borders; bounds is the visible card size.
        assert all(abs(rect.get_width() - VIDEO_CARD_WIDTH) <= 1 for rect in positions)
        assert len(set(preview_widths)) == 1
        measurements.append((width, columns, preview_widths[0]))
    assert measurements[0][1] == 2
    assert measurements[1][1] >= 3
    assert measurements[2][1] >= 4
    assert measurements[3][1] >= 6
    assert measurements[4][1] >= 10
    assert len({measurement[2] for measurement in measurements}) == 1
    assert measurements[-1] == measurements[0]


def test_copy_link_and_paste_link_uses_clipboard(window, monkeypatch):
    from quiettube.ui import DEMO_VIDEOS
    window.demo = False
    requests = []
    monkeypatch.setattr(window.tasks, "submit", lambda request: requests.append(request))
    window.copy_link(DEMO_VIDEOS[0])
    window.paste_link()
    drain()
    assert window.search_entry.get_text() == DEMO_VIDEOS[0].url
    assert requests[-1]["query"] == DEMO_VIDEOS[0].id
    assert window.pending == "open_video"
    window.get_clipboard().set("not a video link")
    window.paste_link()
    drain()
    assert len(requests) == 1
    assert "Copy a YouTube video link first" in window.status.get_text()


def test_play_or_queue_preserves_running_video_and_position(window):
    from quiettube.ui import DEMO_VIDEOS
    from test_controller import FakePlayer
    window.demo = False
    player = FakePlayer()
    window.controller.player = player
    window.controller.play_now(DEMO_VIDEOS[0])
    window.controller.state = "playing"
    window.controller.queue.current.position = 42
    window.play_video(DEMO_VIDEOS[1])
    assert window.play_choice is not None
    assert len(player.starts) == 1
    window.finish_play_choice("queue", DEMO_VIDEOS[1])
    assert window.controller.queue.current.video == DEMO_VIDEOS[0]
    assert window.controller.queue.current.position == 42
    assert window.controller.queue.upcoming[-1].video == DEMO_VIDEOS[1]
    assert len(player.starts) == 1
    window.play_video(DEMO_VIDEOS[2])
    window.finish_play_choice("play", DEMO_VIDEOS[2])
    assert window.controller.queue.current.video == DEMO_VIDEOS[2]
    assert window.controller.queue.upcoming[0].position == 42
    assert len(player.starts) == 2


def test_empty_player_and_queue_play_immediately(window):
    from quiettube.ui import DEMO_VIDEOS
    from test_controller import FakePlayer
    window.demo = False
    window.controller.player = FakePlayer()
    window.controller.queue.upcoming.clear()
    window.play_video(DEMO_VIDEOS[0])
    assert window.play_choice is None
    assert window.controller.queue.current.video == DEMO_VIDEOS[0]
    assert len(window.controller.player.starts) == 1


def test_pasted_video_resolution_opens_choice_but_feed_refresh_does_not(window, monkeypatch):
    from dataclasses import asdict
    from quiettube.tasks import TaskResult
    from quiettube.ui import DEMO_VIDEOS
    window.demo = False
    monkeypatch.setattr(window.thumbnails, "load", lambda *_: None)
    result = TaskResult(window.tasks.generation, {"videos": [asdict(DEMO_VIDEOS[0])], "ok": True})
    window.pending = "open_video"
    window.on_result(result)
    assert window.play_choice is not None
    window.finish_play_choice("cancel", DEMO_VIDEOS[0])
    window.pending = "feed"
    window.on_result(result)
    assert window.play_choice is None


def test_like_only_changes_button_after_confirmation_and_survives_browsing(window, monkeypatch):
    from quiettube.tasks import TaskResult
    from quiettube.ui import DEMO_VIDEOS
    window.demo = False
    window.store.cookie_path.write_text("synthetic fixture")
    requests = []
    monkeypatch.setattr(window.rating_tasks, "submit", lambda request: requests.append(request))
    window.like_video(DEMO_VIDEOS[0])
    assert window.like_pending == DEMO_VIDEOS[0].id
    assert DEMO_VIDEOS[0].id not in window.liked_ids
    window.like_video(DEMO_VIDEOS[1])
    assert len(requests) == 1
    window.tasks.cancel()  # navigating a feed must not cancel the independent write
    window.on_like_result(TaskResult(window.rating_tasks.generation,
                                    {"video_id": DEMO_VIDEOS[0].id, "liked": True}))
    assert DEMO_VIDEOS[0].id in window.liked_ids
    assert window.like_pending is None
    button = window.like_buttons[DEMO_VIDEOS[0].id][0]()
    assert button.get_tooltip_text() == "Liked on YouTube"
    assert not button.get_sensitive()


def test_failed_like_remains_retryable_and_signed_out_like_opens_connection(window, monkeypatch):
    from quiettube.tasks import TaskResult
    from quiettube.ui import DEMO_VIDEOS
    window.demo = False
    window.store.cookie_path.write_text("synthetic fixture")
    monkeypatch.setattr(window.rating_tasks, "submit", lambda request: None)
    window.like_video(DEMO_VIDEOS[0])
    window.on_like_result(TaskResult(window.rating_tasks.generation, error="Reconnect your account"))
    assert not window.liked_ids
    assert window.like_buttons[DEMO_VIDEOS[0].id][0]().get_sensitive()
    assert "not confirmed" in window.status.get_text()
    window.store.cookie_path.unlink()
    window.like_video(DEMO_VIDEOS[0])
    assert window.account_window is not None
    assert window.like_pending is None
    window.account_window.close()


def test_oauth_setup_has_precise_steps_and_clears_pasted_values(window, monkeypatch):
    from quiettube.oauth_help import SETUP_STEPS, SCOPES_TEXT
    from quiettube.tasks import TaskResult
    window.demo = False
    window.store.cookie_path.write_text('synthetic browser session')
    window.open_account()
    requests = []
    monkeypatch.setattr(window.tasks, 'submit', lambda request: requests.append(request))
    assert len(SETUP_STEPS) == 7
    assert SCOPES_TEXT.endswith('/youtube.force-ssl')
    assert not window.oauth_client_secret.get_visibility()
    window.oauth_client_id.set_text('synthetic-test.apps.googleusercontent.com')
    window.oauth_client_secret.set_text('synthetic-secret')
    window.save_oauth_client()
    assert requests[-1]['action'] == 'oauth_configure'
    assert 'session' not in requests[-1]
    assert requests[-1]['client_secret'] == 'synthetic-secret'
    assert window.oauth_client_secret.get_text() == ''
    assert window.oauth_client_id.get_text() == ''
    assert not window.oauth_actions.get_sensitive()
    window.on_result(TaskResult(window.tasks.generation, {'configured': True, 'client_changed': True}))
    assert window.store.get('oauth_configured')
    assert not window.oauth_mode()  # configuring isn't signing in or switching
    assert window.store.cookie_path.exists()
    assert window.oauth_actions.get_sensitive()
    assert 'keyring' in window.oauth_progress.get_text()
    values = str(window.store.db.execute('SELECT * FROM state').fetchall())
    assert 'synthetic-secret' not in values and 'synthetic-test.apps' not in values
    window.account_window.close()


def test_oauth_connection_routes_feed_and_likes_without_browser_cookies(window, monkeypatch):
    from quiettube.tasks import TaskResult
    from quiettube.ui import DEMO_VIDEOS
    window.demo = False
    window.store.cookie_path.write_text('synthetic browser session')
    window.open_account()
    requests, likes = [], []
    monkeypatch.setattr(window.tasks, 'submit', lambda request: requests.append(request))
    monkeypatch.setattr(window.rating_tasks, 'submit', lambda request: likes.append(request))
    window.oauth_request('oauth_connect')
    assert window.pending == 'oauth_connect'
    assert not window.oauth_mode()
    window.on_result(TaskResult(window.tasks.generation, {'connected': True, 'account_connected': True}))
    assert window.oauth_mode()
    assert window.account_window is None
    assert requests[-1]['kind'] == 'home'
    assert requests[-1]['account_mode'] == 'oauth'
    assert 'session' not in requests[-1]
    assert window.store.cookie_path.exists()  # retained only for explicit switching
    window.pending = ''
    window.like_video(DEMO_VIDEOS[0])
    assert likes[-1]['account_mode'] == 'oauth'
    assert 'session' not in likes[-1]


def test_oauth_error_never_falls_back_and_stale_completion_cannot_connect(window, monkeypatch):
    from quiettube.tasks import TaskResult
    window.demo = False
    window.store.cookie_path.write_text('synthetic browser session')
    window.open_account()
    requests = []
    monkeypatch.setattr(window.tasks, 'submit', lambda request: requests.append(request))
    window.oauth_request('oauth_connect')
    generation = window.tasks.generation
    window.account_window.close()
    window.on_result(TaskResult(generation, {'connected': True, 'account_connected': True}))
    assert not window.oauth_mode()
    window.store.set('account_mode', 'oauth')
    window.store.set('oauth_authorized', True)
    window.pending = 'feed'
    count = len(requests)
    window.on_result(TaskResult(window.tasks.generation, {'code': 'sign_in_required'}, 'Sign in again'))
    assert window.oauth_mode()
    assert not window.account_available()
    assert len(requests) == count
    assert window.store.cookie_path.exists()
    assert 'sign in needed' in window.account_button.get_label()


def test_oauth_forget_preserves_queue_and_does_not_activate_saved_browser_session(window, monkeypatch):
    from quiettube.tasks import TaskResult
    window.demo = False
    window.store.set('account_mode', 'oauth')
    window.store.set('oauth_authorized', True)
    window.store.cookie_path.write_text('synthetic browser session')
    before = window.controller.queue.to_dict()
    window.open_account()
    monkeypatch.setattr(window.tasks, 'submit', lambda request: None)
    window.oauth_request('oauth_forget')
    window.on_result(TaskResult(window.tasks.generation, {'forgotten': True}))
    assert window.controller.queue.to_dict() == before
    assert not window.account_available()
    assert window.oauth_mode()
    assert window.store.cookie_path.exists()
    assert not window.videos
    window.account_window.close()


def test_oauth_pagination_uses_tokens_and_refresh_resets_them(window, monkeypatch):
    from quiettube.tasks import TaskResult
    window.demo = False
    window.store.set('account_mode', 'oauth')
    window.store.set('oauth_authorized', True)
    window.feed = 'search'
    window.query = 'example'
    requests = []
    monkeypatch.setattr(window.tasks, 'submit', lambda request: requests.append(request))
    window.pending = 'feed'
    window.on_result(TaskResult(window.tasks.generation, {'videos': [], 'has_more': True, 'next_page_token': 'page-two'}))
    window.change_page(1)
    assert requests[-1]['page_token'] == 'page-two'
    window.reload()
    assert requests[-1]['page'] == 0 and requests[-1]['page_token'] == ''
    assert requests[-1]['refresh'] is True


def test_oauth_unsupported_feed_clears_previous_cards_without_signing_out(window, monkeypatch):
    from quiettube.tasks import TaskResult
    window.demo = False
    window.store.set('account_mode', 'oauth')
    window.store.set('oauth_authorized', True)
    window.oauth_verified = True
    before = window.controller.queue.to_dict()
    monkeypatch.setattr(window.tasks, 'submit', lambda request: None)
    assert window.videos
    window.load_feed('later')
    window.on_result(TaskResult(window.tasks.generation, {'code': 'unsupported'}, 'Watch Later is unavailable through this API.'))
    assert window.videos == [] and window.feed_videos == []
    assert not window.has_more
    assert window.oauth_verified and window.account_available()
    assert window.controller.queue.to_dict() == before
    assert 'Watch Later is unavailable' in window.status.get_text()


def test_playback_help_preserves_oauth_and_opens_browser_only_on_explicit_click(window, monkeypatch):
    from quiettube.player import PlayerEvent, PlaybackDiagnostics
    from quiettube.ui import DEMO_VIDEOS
    from test_controller import FakePlayer
    window.demo = False
    window.store.set('account_mode', 'oauth')
    window.store.set('oauth_authorized', True)
    window.oauth_verified = True
    window.player = window.controller.player = FakePlayer()
    window.controller.play_now(DEMO_VIDEOS[0])
    window.controller.event(PlayerEvent(window.player.generation, 'time-pos', 75.8))
    before = window.controller.queue.to_dict()
    opened = []
    monkeypatch.setattr('quiettube.ui.Gio.AppInfo.launch_default_for_uri', lambda url, context: opened.append(url))
    diagnostic = PlaybackDiagnostics()
    diagnostic.observe("Sign in to confirm you're not a bot")
    window.on_player(PlayerEvent(window.player.generation, 'error', diagnostic.error(), diagnostic.category))
    assert window.playback_help_button.get_visible()
    assert window.account_button.get_label() == 'Personal OAuth · connected'
    window.playback_help_button.emit('clicked')
    first = window.playback_help_window
    assert first is not None and opened == []
    window.open_playback_help()
    assert window.playback_help_window is first
    window.playback_browser_button.emit('clicked')
    assert opened == [DEMO_VIDEOS[0].url + '&t=75s']
    assert window.controller.queue.to_dict() == before
    assert window.oauth_verified and window.account_available()
    first.close()
    assert window.playback_help_window is None
    window.controller.reload()
    assert not window.playback_help_button.get_visible()
    assert window.player.starts[-1][1] == 75.8
    assert window.player.starts[-1][3] is None


def test_oauth_sign_in_is_reachable_at_top_of_account_dialog(window, monkeypatch):
    from gi.repository import Gtk
    window.demo = False
    window.store.set('account_mode', 'oauth')
    calls = []
    monkeypatch.setattr(window.tasks, 'submit', lambda request: calls.append(request))
    window.open_account()
    content = window.account_window.get_child().get_child()
    if isinstance(content, Gtk.Viewport):
        content = content.get_child()
    child = content.get_first_child()
    first_controls = []
    for _ in range(4):
        first_controls.append(child)
        child = child.get_next_sibling()
    signin = first_controls[-1]
    assert signin.get_label() == 'Sign in with Google for account feeds'
    signin.emit('clicked')
    assert calls[-1]['action'] == 'oauth_connect'
    assert not signin.get_sensitive()
    window.account_window.close()


def test_separate_playback_setup_preserves_oauth_feed_queue_and_ignores_stale_results(window, monkeypatch):
    from quiettube.tasks import TaskResult
    from quiettube.ui import DEMO_VIDEOS
    from test_controller import FakePlayer
    window.demo = False
    window.store.set('account_mode', 'oauth')
    window.store.set('oauth_authorized', True)
    window.oauth_verified = True
    window.player = window.controller.player = FakePlayer()
    window.controller.play_now(DEMO_VIDEOS[0])
    window.controller.queue.current.position = 75
    before = window.controller.queue.to_dict()
    feed = window.feed
    calls = []
    monkeypatch.setattr('quiettube.playback_connection.suggested_profile', lambda *_: '')
    window.open_playback_connection()
    dialog = window.playback_connection_window
    window.open_playback_connection()
    assert window.playback_connection_window is dialog
    monkeypatch.setattr(dialog.tasks, 'submit', lambda request: calls.append(request))
    dialog.connect_button.emit('clicked')
    assert calls[-1]['action'] == 'playback_connect'
    assert calls[-1]['session'] == str(window.store.playback_cookie_path)
    assert 'account_mode' not in calls[-1]
    assert not dialog.actions.get_sensitive()
    dialog.on_result(TaskResult(dialog.tasks.generation + 1, {'playback_session_saved': True}))
    assert not window.store.get('playback_session_enabled', False)
    dialog.on_result(TaskResult(dialog.tasks.generation, error='Synthetic import failure'))
    assert not window.store.get('playback_session_enabled', False)
    assert dialog.actions.get_sensitive()
    assert window.oauth_verified
    window.store.playback_cookie_path.write_text('synthetic session')
    dialog.on_result(TaskResult(dialog.tasks.generation, {'playback_session_saved': True}))
    assert window.store.get('playback_session_enabled')
    assert window.controller.queue.to_dict() == before
    assert window.feed == feed and window.oauth_verified
    assert window.store.get('account_mode') == 'oauth' and window.store.get('oauth_authorized')
    assert window.playback_connection_button.get_label() == 'Playback session · saved'
    window.controller.play()
    assert window.player.starts[-1][3] == window.store.playback_cookie_path
    dialog.remove_session()
    assert not window.store.playback_cookie_path.exists()
    assert not window.store.get('playback_session_enabled')
    assert window.controller.queue.to_dict() == before
    assert window.oauth_verified and window.store.get('oauth_authorized')
    dialog.close()
    assert window.playback_connection_window is None
    dialog.on_result(TaskResult(dialog.tasks.generation, {'playback_session_saved': True}))
    assert not window.store.get('playback_session_enabled')
