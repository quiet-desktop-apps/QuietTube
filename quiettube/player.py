from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time

from .storage import atomic_private_write
from .diagnostics import codec_name


@dataclass(frozen=True)
class PlayerEvent:
    generation: int
    kind: str
    value: object = None


def playback_format(height: int) -> str:
    if height not in {480, 720, 1080, 1440, 2160}:
        raise ValueError("Unsupported playback quality")
    # Some YouTube videos advertise direct streams that reject playback with
    # HTTP 403, while their HLS streams work. Keep both audio and video on HLS
    # when available, with direct streams for videos that don't offer HLS.
    video = f"bestvideo[height<={height}]"
    combined = f"best[height<={height}]"
    return (f"{video}[protocol^=m3u8]+bestaudio[protocol^=m3u8]/"
            f"{combined}[protocol^=m3u8]/{video}+bestaudio/{combined}")


class PlaybackDiagnostics:
    """Retain only a fixed error category, never raw logs or signed media URLs.

    Log wording is best-effort diagnostic context, not a playback/queue signal.
    Only mpv's structured end-file event decides failure or completion.
    """

    MESSAGES = {
        "forbidden": "YouTube rejected the media stream (HTTP 403). Try Play again for a fresh stream.",
        "limited": "YouTube is limiting requests (HTTP 429). Wait a few minutes before retrying.",
        "account": "YouTube requires a valid session for this video. Reconnect your account and retry.",
        "network": "The media server could not be reached. Check your connection and retry.",
        "format": "No playable stream was available at this quality. Try another quality or update with setup.sh.",
        "decode": "The video decoder reported a problem. Use Reload video to retry at your current position.",
        "unknown": "Playback failed. Try Play again; if it persists, reconnect your account or run setup.sh.",
    }

    def __init__(self):
        self.category = "unknown"

    def observe(self, message: str):
        # Higher-priority errors are not overwritten by generic follow-up logs.
        message = message[:16_384].lower()
        category = "unknown"
        if re.search(r"(?:http(?: error)?|server returned)\s+403\b", message):
            category = "forbidden"
        elif re.search(r"(?:http(?: error)?|server returned)\s+429\b", message):
            category = "limited"
        elif any(value in message for value in ("sign in to", "login required", "authentication required")):
            category = "account"
        elif any(value in message for value in ("connection timed out", "failed to resolve", "network is unreachable")):
            category = "network"
        elif "requested format is not available" in message:
            category = "format"
        elif any(value in message for value in ("error decoding", "invalid frame", "corrupt", "failed to decode")):
            category = "decode"
        priority = ("unknown", "format", "decode", "network", "account", "forbidden", "limited")
        if priority.index(category) > priority.index(self.category):
            self.category = category
        return category

    def error(self) -> str:
        return self.MESSAGES[self.category] + " Your video, position and queue are preserved."


def mpv_command(socket_path: str, height: int, session: Path | None = None) -> list[str]:
    selected_format = playback_format(height)
    extractor = Path(sys.executable).parent / "yt-dlp"
    if not extractor.exists():
        extractor = Path(shutil.which("yt-dlp") or "yt-dlp")
    command = [
        "mpv", "--no-config", "--idle=yes", "--force-window=yes",
        "--title=QuietTube — ${media-title}", f"--input-ipc-server={socket_path}",
        # Automatic GPU decoding can report success while displaying corrupt
        # VP9 frames. Software decoding keeps the HLS fix without that path.
        "--hwdec=no", "--cache=yes", "--cache-secs=20",
        "--demuxer-max-bytes=64MiB", "--demuxer-max-back-bytes=8MiB",
        "--save-position-on-quit=no", "--keep-open=no", "--autofit=960x540",
        f"--ytdl-format={selected_format}",
        f"--script-opts=ytdl_hook-ytdl_path={extractor}",
        "--msg-level=all=no",
    ]
    raw_options = "js-runtimes=node"
    if session:
        raw_options += f",cookies={session}"
    command.append(f"--ytdl-raw-options={raw_options}")
    return command


class MpvPlayer:
    SNAPSHOT_INTERVAL = 10
    SNAPSHOT_PROPERTIES = ("audio-pts", "avsync", "decoder-frame-drop-count", "frame-drop-count",
                           "demuxer-cache-duration", "paused-for-cache", "seeking",
                           "video-codec", "hwdec-current", "current-vo")

    def __init__(self, callback, log=None):
        self.callback = callback
        self.log = log
        self.generation = 0
        self.process = None
        self.connection = None
        self.temp = None
        self.thread = None
        self.send_lock = threading.Lock()

    def _emit(self, generation, kind, value=None):
        if generation == self.generation:
            if kind in {"loaded", "closed", "finished", "error"}:
                self._log(kind, generation)
            self.callback(PlayerEvent(generation, kind, value))

    def _log(self, event, generation, **fields):
        if self.log:
            self.log.write(event, generation, **fields)

    def start(self, url: str, position: float = 0, height: int = 720,
              session: Path | None = None, extra_args: list[str] | None = None) -> int:
        self.stop()
        generation = self.generation
        self._log("start", generation, position=position, height=height)
        self.temp = tempfile.TemporaryDirectory(prefix="quiettube-player-")
        socket_path = str(Path(self.temp.name) / "mpv.sock")
        private_session = None
        if session and session.is_file():
            private_session = Path(self.temp.name) / "youtube.txt"
            atomic_private_write(private_session, session.read_bytes())
        try:
            process = subprocess.Popen(
                mpv_command(socket_path, height, private_session) + (extra_args or []),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError:
            self.temp.cleanup()
            self.temp = None
            self._emit(generation, "error", "mpv is not installed or could not start. Run setup.sh.")
            return generation
        self.process = process
        self.thread = threading.Thread(target=self._listen,
            args=(process, socket_path, generation, url, position), daemon=True)
        self.thread.start()
        return generation

    def _listen(self, process, socket_path, generation, url, position):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            deadline = time.monotonic() + 12
            while generation == self.generation:
                try:
                    connection.connect(socket_path)
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    if process.poll() is not None or time.monotonic() > deadline:
                        self._emit(generation, "error", "The video player could not open its control connection.")
                        return
                    time.sleep(0.04)
            if generation != self.generation:
                return
            connection.settimeout(0.25)
            self.connection = connection
            diagnostics = PlaybackDiagnostics()
            self.command(["request_log_messages", "warn"])
            for index, name in enumerate(("time-pos", "duration", "pause"), 1):
                self.command(["observe_property", index, name])
            # mpv 0.38 added a positional index before options. Named arguments
            # preserve the start position on both Ubuntu's 0.37 and newer mpv.
            if not self.command({"name": "loadfile", "url": url, "flags": "replace",
                                 "options": {"start": str(max(0, position))}}, request_id=100):
                self._emit(generation, "error", "The video player could not accept the playback request.")
                return
            buffer = b""
            ended = False
            snapshot = {}
            pending_snapshot = set()
            next_snapshot = 0
            pause_started = None
            last_warning = None
            warning_at = 0
            while generation == self.generation:
                if self.log and time.monotonic() >= next_snapshot:
                    if pending_snapshot:
                        self._log("snapshot", generation, **snapshot)
                    pending_snapshot = set(range(len(self.SNAPSHOT_PROPERTIES)))
                    for index, prop in enumerate(self.SNAPSHOT_PROPERTIES):
                        self.command(["get_property", prop], request_id=1000 + index)
                    next_snapshot = time.monotonic() + self.SNAPSHOT_INTERVAL
                try:
                    chunk = connection.recv(65536)
                except socket.timeout:
                    if process.poll() is not None:
                        break
                    continue
                if not chunk:
                    break
                buffer += chunk
                if len(buffer) > 1024 * 1024:
                    self._emit(generation, "error", "The player sent an oversized response.")
                    return
                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    name = event.get("event")
                    request = event.get("request_id")
                    if request == 100 and event.get("error") != "success":
                        ended = True
                        self._emit(generation, "error", "The video player rejected the playback request. Check your mpv installation. Your queue is preserved.")
                        return
                    if isinstance(request, int) and 1000 <= request < 1000 + len(self.SNAPSHOT_PROPERTIES):
                        index = request - 1000
                        prop = self.SNAPSHOT_PROPERTIES[index]
                        value = event.get("data")
                        snapshot[prop] = codec_name(value) if prop == "video-codec" else value
                        pending_snapshot.discard(index)
                        if not pending_snapshot:
                            self._log("snapshot", generation, **snapshot)
                    if name == "log-message":
                        category = diagnostics.observe(str(event.get("text", "")))
                        now = time.monotonic()
                        if category != last_warning or now - warning_at >= 10:
                            self._log("warning", generation, category=category)
                            last_warning, warning_at = category, now
                    elif name == "file-loaded":
                        next_snapshot = 0
                        self._emit(generation, "loaded")
                    elif name in {"seek", "playback-restart"}:
                        self._log("seek" if name == "seek" else "seeked", generation, **snapshot)
                    elif name == "property-change" and event.get("data") is not None:
                        if event["name"] in {"time-pos", "duration", "pause"}:
                            snapshot[event["name"]] = event["data"]
                        if event["name"] == "pause":
                            now = time.monotonic()
                            elapsed = now - pause_started if pause_started is not None else 0
                            if event["data"]:
                                pause_started = now
                            else:
                                pause_started = None
                            self._log("pause", generation, **snapshot, pause_seconds=elapsed)
                            next_snapshot = 0
                        self._emit(generation, event["name"], event["data"])
                    elif name == "end-file":
                        reason = event.get("reason")
                        if reason == "eof":
                            ended = True
                            self._emit(generation, "finished")
                        elif reason == "error":
                            ended = True
                            self._emit(generation, "error", diagnostics.error())
            if not ended:
                self._emit(generation, "closed")
        except OSError:
            self._emit(generation, "closed")
        finally:
            self._log("ipc_closed", generation, exit_code=process.poll())
            connection.close()
            if generation == self.generation:
                self.connection = None

    def command(self, command: list | dict, request_id=None) -> bool:
        with self.send_lock:
            if not self.connection:
                return False
            try:
                message = {"command": command}
                if request_id is not None:
                    message["request_id"] = request_id
                self.connection.sendall((json.dumps(message) + "\n").encode())
                return True
            except OSError:
                return False

    def stop(self):
        if self.process:
            self._log("stop", self.generation)
        self.generation += 1
        process, self.process = self.process, None
        if self.connection:
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            self.connection = None
        if process and process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=2)
            except ProcessLookupError:
                pass
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join(timeout=1)
        self.thread = None
        self.connection = None
        if self.temp:
            self.temp.cleanup()
            self.temp = None
