from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from .models import PlaybackQueue, Video


def data_directory() -> Path:
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "quiettube"


def private_directory(path: Path) -> Path:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)
    return path


def atomic_private_write(path: Path, content: bytes) -> None:
    private_directory(path.parent)
    fd, tmp = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Store:
    def __init__(self, directory: Path):
        self.directory = private_directory(directory)
        path = directory / "library.sqlite3"
        # Create with restricted permissions before SQLite opens it.
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        path.chmod(0o600)
        self.db = sqlite3.connect(path)
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS history (
                video_id TEXT PRIMARY KEY, video TEXT NOT NULL,
                position REAL NOT NULL, completed INTEGER NOT NULL, watched REAL NOT NULL);
        """)
        self.load_warning = ""

    @property
    def cookie_path(self) -> Path:
        return self.directory / "youtube-session.txt"

    @property
    def playback_cookie_path(self) -> Path:
        return self.directory / "youtube-playback-session.txt"

    def get(self, key: str, default=None):
        row = self.db.execute("SELECT value FROM state WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row[0])
        except (ValueError, TypeError):
            return default

    def set(self, key: str, value) -> None:
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO state VALUES (?, ?)", (key, json.dumps(value)))

    def load_queue(self) -> PlaybackQueue:
        try:
            return PlaybackQueue.from_dict(self.get("queue", {}))
        except (ValueError, TypeError, KeyError, AttributeError):
            self.load_warning = "The saved queue could not be read. A recovery copy is kept in the database."
            self.set("queue-recovery", self.get("queue"))
            return PlaybackQueue()

    def save_queue(self, queue: PlaybackQueue) -> None:
        self.set("queue", queue.to_dict())

    def record(self, video: Video, position: float, completed: bool = False) -> None:
        with self.db:
            self.db.execute("""INSERT INTO history VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET video=excluded.video,
                position=excluded.position, completed=MAX(history.completed, excluded.completed),
                watched=excluded.watched""",
                            (video.id, json.dumps(asdict(video)), position, int(completed), time.time()))
            self.db.execute("DELETE FROM history WHERE video_id NOT IN "
                            "(SELECT video_id FROM history ORDER BY watched DESC LIMIT 500)")

    def completed_ids(self) -> set[str]:
        return {row[0] for row in self.db.execute("SELECT video_id FROM history WHERE completed=1")}

    def history(self, limit: int = 40) -> list[Video]:
        return [Video(**json.loads(row[0])) for row in self.db.execute(
            "SELECT video FROM history ORDER BY watched DESC LIMIT ?", (min(limit, 500),))]

    def close(self) -> None:
        self.db.close()
