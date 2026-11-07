import shutil
import subprocess
import threading
import time
from functools import partial
from http.server import BaseHTTPRequestHandler, SimpleHTTPRequestHandler, ThreadingHTTPServer
from queue import SimpleQueue

import pytest
from PIL import Image, ImageChops, ImageStat

from quiettube.player import MpvPlayer, mpv_command
from quiettube.controller import PlaybackController
from quiettube.models import Video
from quiettube.storage import Store
from quiettube.diagnostics import PlaybackLog
import json

pytestmark = pytest.mark.skipif(not shutil.which("mpv") or not shutil.which("ffmpeg"), reason="mpv and ffmpeg required")


@pytest.fixture
def clip(tmp_path):
    path = tmp_path / "sample.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
                    "color=c=teal:s=320x180:r=15", "-t", "1.2", "-c:v", "mpeg4", str(path)], check=True)
    return path


def wait_for(predicate, timeout=8):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("Expected player event did not arrive")


def test_real_mpv_loads_reports_progress_and_eof(clip):
    events = []
    player = MpvPlayer(events.append)
    try:
        player.start(str(clip), extra_args=["--vo=null", "--ao=null", "--force-window=no"])
        wait_for(lambda: any(event.kind == "finished" for event in events))
        kinds = [event.kind for event in events]
        assert "loaded" in kinds
        assert "time-pos" in kinds
        assert "error" not in kinds
        process = player.process
    finally:
        player.stop()
    assert process.poll() is not None
    assert player.connection is None
    assert player.temp is None


def test_real_mpv_pause_resume_and_seek(clip, tmp_path):
    events = []
    log = PlaybackLog(tmp_path / "logs")
    player = MpvPlayer(events.append, log=log)
    player.SNAPSHOT_INTERVAL = 0.1
    try:
        player.start(str(clip), extra_args=["--vo=null", "--ao=null", "--force-window=no", "--pause=yes"])
        wait_for(lambda: any(event.kind == "loaded" for event in events))
        time.sleep(0.15)
        assert not any(event.kind == "finished" for event in events)
        assert player.command(["seek", 0.4, "absolute"])
        assert player.command(["set_property", "pause", False])
        wait_for(lambda: any(event.kind == "finished" for event in events))
    finally:
        player.stop()
    rows = [json.loads(line) for line in log.path.read_text().splitlines()]
    assert any(row["event"] == "snapshot" and row.get("hwdec-current") == "no" for row in rows)
    assert any(row["event"] == "pause" and row.get("pause") is True for row in rows)
    assert any(row["event"] == "pause" and row.get("pause") is False and row.get("pause_seconds", 0) > 0 for row in rows)
    assert any(row["event"] == "finished" for row in rows)
    assert str(clip) not in log.path.read_text()


def test_real_mpv_reopens_at_requested_position(clip):
    events = []
    player = MpvPlayer(events.append)
    try:
        for _ in range(2):
            events.clear()
            player.start(str(clip), position=0.6,
                         extra_args=["--vo=null", "--ao=null", "--force-window=no", "--pause=yes"])
            wait_for(lambda: any(e.kind == "time-pos" and e.value >= 0.5 for e in events))
            assert not any(e.kind == "error" for e in events)
            player.stop()
    finally:
        player.stop()


def test_real_mpv_missing_file_emits_error_not_completion(tmp_path):
    events = []
    player = MpvPlayer(events.append)
    try:
        player.start(str(tmp_path / "missing.mp4"), extra_args=["--vo=null", "--ao=null", "--force-window=no"])
        wait_for(lambda: any(event.kind == "error" for event in events))
        assert not any(event.kind == "finished" for event in events)
    finally:
        player.stop()


def test_stopping_player_does_not_emit_completion(clip):
    events = []
    player = MpvPlayer(events.append)
    player.start(str(clip), extra_args=["--vo=null", "--ao=null", "--force-window=no", "--pause=yes"])
    wait_for(lambda: any(event.kind == "loaded" for event in events))
    player.stop()
    assert not any(event.kind == "finished" for event in events)


def test_player_has_explicit_buffer_bounds_and_safe_arguments():
    command = mpv_command("/tmp/test.sock", 720)
    assert "--demuxer-max-bytes=64MiB" in command
    assert "--demuxer-max-back-bytes=8MiB" in command
    assert "--no-config" in command
    assert "--hwdec=no" in command
    assert not any("youtube.com/watch" in arg for arg in command)
    with pytest.raises(ValueError):
        mpv_command("/tmp/test.sock", 999)


def test_rendered_vp9_hls_frames_survive_start_and_seek(tmp_path):
    """Check actual pixels, not merely loaded/time-pos events, on the HLS path."""
    playlist = tmp_path / "sample.m3u8"
    reference = tmp_path / "reference.png"
    source = "smptebars=size=320x180:rate=15"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", source,
                    "-t", "4", "-c:v", "libvpx-vp9", "-deadline", "realtime", "-cpu-used", "8",
                    "-g", "15", "-pix_fmt", "yuv420p", "-hls_segment_type", "fmp4",
                    "-hls_time", "1", "-hls_list_size", "0", str(playlist)], check=True)
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", source,
                    "-frames:v", "1", str(reference)], check=True)

    class Files(SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(Files, directory=str(tmp_path)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    events = []
    player = MpvPlayer(events.append)
    try:
        player.start(f"http://127.0.0.1:{server.server_port}/sample.m3u8",
                     extra_args=["--vo=x11", "--ao=null", "--pause=yes", "--ytdl=no"])
        wait_for(lambda: any(e.kind == "loaded" for e in events))
        player.command(["observe_property", 4, "hwdec-current"])
        wait_for(lambda: any(e.kind == "hwdec-current" for e in events))
        assert next(e.value for e in events if e.kind == "hwdec-current") == "no"
        for index in range(2):
            if index:
                player.command(["seek", 2.2, "absolute+exact"])
                wait_for(lambda: any(e.kind == "time-pos" and e.value >= 2.2 for e in events))
            target = tmp_path / f"frame-{index}.png"
            player.command(["screenshot-to-file", str(target), "video"])

            def rendered():
                try:
                    with Image.open(target) as frame:
                        frame.load()
                    return True
                except (OSError, ValueError):
                    return False

            wait_for(rendered)
            with Image.open(target) as actual, Image.open(reference) as expected:
                assert actual.size == expected.size
                difference = ImageChops.difference(actual.convert("RGB"), expected.convert("RGB"))
                # Lossy encoding and colour conversion allow a small tolerance.
                assert max(ImageStat.Stat(difference).mean) < 6
        assert not any(e.kind == "error" for e in events)
    finally:
        player.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_real_http_rejection_reports_safe_reason():
    class Forbidden(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_error(403)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Forbidden)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    events = []
    player = MpvPlayer(events.append)
    try:
        player.start(f"http://127.0.0.1:{server.server_port}/video?token=SECRET",
                     extra_args=["--vo=null", "--ao=null", "--force-window=no", "--ytdl=no"])
        wait_for(lambda: any(e.kind == "error" for e in events))
        errors = [e.value for e in events if e.kind == "error"]
        assert "HTTP 403" in errors[-1]
        assert "SECRET" not in errors[-1]
        assert not any(e.kind == "finished" for e in events)
    finally:
        player.stop()
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def queued_player(tmp_path, clip):
    events = SimpleQueue()

    class LocalPlayer(MpvPlayer):
        def start(self, url, position=0, height=720, session=None):
            path = tmp_path / "missing.mp4" if url.endswith("00000000000") else clip
            return super().start(str(path), position, height,
                                 extra_args=["--vo=null", "--ao=null", "--force-window=no"])

    store = Store(tmp_path / "store")
    player = LocalPlayer(events.put)
    controller = PlaybackController(store, player)
    seen = []

    def pump_until(predicate):
        def pump():
            while not events.empty():
                event = events.get()
                seen.append(event)
                controller.event(event)
            return predicate()
        wait_for(pump, timeout=12)

    return store, player, controller, seen, pump_until


def test_real_queue_plays_two_consecutive_videos(clip, tmp_path):
    store, player, controller, seen, pump = queued_player(tmp_path, clip)
    try:
        for ident in ("11111111111", "22222222222"):
            controller.add(Video(ident, "Local queue clip"))
        controller.play()
        pump(lambda: controller.queue.current is None)
        assert controller.state == "stopped"
        assert len({e.generation for e in seen if e.kind == "loaded"}) == 2
        assert len([e for e in seen if e.kind == "finished"]) == 2
        assert not any(e.kind == "error" for e in seen)
        assert store.db.execute("SELECT count(*) FROM history WHERE completed=1").fetchone() == (2,)
    finally:
        controller.close()
        store.close()


def test_real_queue_failure_preserves_items_and_play_now_recovers(clip, tmp_path):
    store, player, controller, seen, pump = queued_player(tmp_path, clip)
    try:
        for ident in ("11111111111", "00000000000", "22222222222"):
            controller.add(Video(ident, "Local recovery clip"))
        controller.play()
        pump(lambda: controller.state == "error")
        failed_key = controller.queue.current.key
        upcoming_key = controller.queue.upcoming[0].key
        assert controller.queue.current.video.id == "00000000000"
        assert store.load_queue().current.key == failed_key
        controller.play_now(Video("33333333333", "Replacement clip"))
        pump(lambda: controller.state == "playing")
        assert controller.queue.current.video.id == "33333333333"
        assert [item.key for item in controller.queue.upcoming] == [failed_key, upcoming_key]
        assert len({e.generation for e in seen if e.kind == "loaded"}) == 2
    finally:
        controller.close()
        store.close()
