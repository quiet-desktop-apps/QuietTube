"""Small, private playback logs. Only allowlisted metadata reaches disk."""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import threading
from uuid import uuid4

from .storage import private_directory


class PlaybackLog:
    MAX_BYTES = 1024 * 1024
    EVENTS = {"start", "stop", "loaded", "closed", "finished", "error", "pause",
              "snapshot", "warning", "seek", "seeked", "ipc_closed"}
    NUMBERS = {"position", "height", "time-pos", "duration", "audio-pts", "avsync",
               "decoder-frame-drop-count", "frame-drop-count", "demuxer-cache-duration",
               "pause_seconds", "exit_code"}
    FLAGS = {"pause", "seeking", "paused-for-cache"}
    ENUMS = {
        "category": {"unknown", "forbidden", "limited", "account", "network", "format", "decode"},
        "video-codec": {"vp9", "h264", "av1", "hevc", "other"},
        "hwdec-current": {"no", "vaapi", "vaapi-copy", "vulkan", "vulkan-copy", "nvdec", "nvdec-copy", "other"},
        "current-vo": {"gpu", "gpu-next", "x11", "null", "other"},
    }

    def __init__(self, directory: Path):
        self.path = directory / "playback.jsonl"
        self.run = uuid4().hex[:12]
        self.lock = threading.Lock()
        self.available = True

    def write(self, event, generation, **fields):
        if event not in self.EVENTS:
            return
        safe = {}
        for key, value in fields.items():
            if key in self.NUMBERS and type(value) in (float, int) and math.isfinite(value):
                safe[key] = round(value, 3)
            elif key in self.FLAGS and type(value) is bool:
                safe[key] = value
            elif key in self.ENUMS and isinstance(value, str) and value in self.ENUMS[key]:
                safe[key] = value
        row = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "run": self.run, "generation": int(generation), "event": event, **safe}
        data = (json.dumps(row) + "\n").encode()
        with self.lock:
            try:
                private_directory(self.path.parent)
                if self.path.exists() and self.path.stat().st_size + len(data) > self.MAX_BYTES:
                    older = self.path.with_name("playback.2.jsonl")
                    previous = self.path.with_name("playback.1.jsonl")
                    if previous.exists():
                        os.replace(previous, older)
                    os.replace(self.path, previous)
                fd = os.open(self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
                with os.fdopen(fd, "ab") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(data)
                self.available = True
            except OSError:
                # Disk-full/permission failures must never interrupt playback.
                self.available = False


def codec_name(value):
    value = str(value).lower()
    for needle, name in (("vp9", "vp9"), ("h.264", "h264"), ("h264", "h264"),
                         ("av1", "av1"), ("hevc", "hevc"), ("h.265", "hevc")):
        if needle in value:
            return name
    return "other"
