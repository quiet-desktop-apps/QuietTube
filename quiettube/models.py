from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import math
import re
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}


def video_id(value: str) -> str:
    value = value.strip()
    if VIDEO_ID.fullmatch(value):
        return value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ValueError("Paste a YouTube video link or an 11-character video ID.")
    host = parsed.hostname
    candidate = ""
    if host == "youtu.be":
        candidate = parsed.path.strip("/").split("/")[0]
    elif host in YOUTUBE_HOSTS:
        parts = parsed.path.strip("/").split("/")
        if parsed.path == "/watch":
            candidate = parse_qs(parsed.query).get("v", [""])[0]
        elif len(parts) == 2 and parts[0] in {"shorts", "live", "embed"}:
            candidate = parts[1]
    if not VIDEO_ID.fullmatch(candidate):
        raise ValueError("This is not a supported YouTube video link.")
    return candidate


def playlist_url(value: str) -> str:
    parsed = urlparse(value.strip())
    ident = parse_qs(parsed.query).get("list", [""])[0]
    if (parsed.scheme not in {"http", "https"} or parsed.hostname not in YOUTUBE_HOSTS
            or parsed.username or parsed.password or not re.fullmatch(r"[A-Za-z0-9_-]{2,120}", ident)):
        raise ValueError("Paste a YouTube playlist link containing list=…")
    return f"https://www.youtube.com/playlist?list={ident}"


def finite_seconds(value: object) -> float:
    try:
        number = float(value)
        return max(0.0, number) if math.isfinite(number) else 0.0
    except (TypeError, ValueError):
        return 0.0


def publication_date(info: dict) -> str:
    """Keep time precision when supplied; old date-only saved records still work."""
    timestamp = finite_seconds(info.get("timestamp"))
    if timestamp:
        try:
            return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds")
        except (ValueError, OverflowError, OSError):
            pass
    return str(info.get("upload_date") or info.get("published") or "")[:30]


def published_label(value: str, now: datetime | None = None) -> str:
    """Compact elapsed time, without inventing a time for date-only metadata."""
    if not value:
        return ""
    now = now or datetime.now(timezone.utc)
    try:
        if re.fullmatch(r"\d{8}", value):
            published = datetime.strptime(value, "%Y%m%d").replace(tzinfo=timezone.utc)
            date_only = True
        else:
            published = datetime.fromisoformat(value.replace("Z", "+00:00"))
            date_only = len(value) == 10
            if published.tzinfo is None:
                published = published.replace(tzinfo=timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        seconds = ((now.date() - published.date()).days * 86400 if date_only
                   else (now - published).total_seconds())
    except (ValueError, TypeError, OverflowError):
        return ""
    if seconds < 0:
        return "Upcoming"
    if date_only and seconds == 0:
        return "Today"
    for unit, period in (("y", 365 * 86400), ("mo", 30 * 86400), ("w", 7 * 86400),
                         ("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= period:
            return f"{int(seconds // period)}{unit} ago"
    return "Just now"


def publication_sort_key(video) -> datetime:
    """Sort known dates newest first, keeping unknown dates at the end."""
    try:
        value = video.published
        date = (datetime.strptime(value, "%Y%m%d") if re.fullmatch(r"\d{8}", value)
                else datetime.fromisoformat(value.replace("Z", "+00:00")))
        return date.replace(tzinfo=timezone.utc) if date.tzinfo is None else date.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError, OverflowError):
        return datetime.min.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Video:
    id: str
    title: str
    channel: str = ""
    duration: float = 0
    published: str = ""

    def __post_init__(self):
        if not VIDEO_ID.fullmatch(self.id):
            raise ValueError("Invalid YouTube video ID")

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"

    @property
    def thumbnail(self) -> str:
        return f"https://i.ytimg.com/vi/{self.id}/mqdefault.jpg"

    @classmethod
    def from_info(cls, info: dict) -> Video:
        return cls(
            video_id(str(info.get("id", ""))),
            str(info.get("title") or "Untitled video")[:500],
            str(info.get("channel") or info.get("uploader") or "")[:200],
            finite_seconds(info.get("duration")),
            publication_date(info),
        )


@dataclass
class QueueItem:
    video: Video
    key: str = field(default_factory=lambda: uuid4().hex)
    position: float = 0

    def to_dict(self) -> dict:
        return {"video": asdict(self.video), "key": self.key, "position": self.position}

    @classmethod
    def from_dict(cls, data: dict) -> QueueItem:
        key = str(data["key"])
        if not re.fullmatch(r"[a-f0-9]{32}", key):
            raise ValueError("Invalid queue item key")
        return cls(Video(**data["video"]), key, finite_seconds(data.get("position")))


class PlaybackQueue:
    """Upcoming items plus one current item; item identity survives duplicate videos."""

    MAX_ITEMS = 1000

    def __init__(self, current: QueueItem | None = None, upcoming: list[QueueItem] | None = None):
        self.current = current
        self.upcoming = list(upcoming or [])

    def add(self, video: Video, index: int | None = None) -> QueueItem:
        if len(self.upcoming) >= self.MAX_ITEMS:
            raise ValueError("The queue is full (1,000 upcoming videos).")
        item = QueueItem(video)
        if index is None:
            self.upcoming.append(item)
        else:
            self.upcoming.insert(max(0, min(index, len(self.upcoming))), item)
        return item

    def remove(self, key: str) -> None:
        self.upcoming = [item for item in self.upcoming if item.key != key]

    def move(self, key: str, index: int) -> None:
        old = next((i for i, item in enumerate(self.upcoming) if item.key == key), None)
        if old is None:
            return
        item = self.upcoming.pop(old)
        self.upcoming.insert(max(0, min(index, len(self.upcoming))), item)

    def advance(self) -> QueueItem | None:
        self.current = self.upcoming.pop(0) if self.upcoming else None
        return self.current

    def play_now(self, video: Video) -> QueueItem:
        if self.current:
            if len(self.upcoming) >= self.MAX_ITEMS:
                raise ValueError("Remove an item from the full queue before switching videos.")
            self.upcoming.insert(0, self.current)
        self.current = QueueItem(video)
        return self.current

    def to_dict(self) -> dict:
        return {"current": self.current.to_dict() if self.current else None,
                "upcoming": [item.to_dict() for item in self.upcoming]}

    @classmethod
    def from_dict(cls, data: dict) -> PlaybackQueue:
        items = [QueueItem.from_dict(item) for item in data.get("upcoming", [])[:cls.MAX_ITEMS]]
        current = QueueItem.from_dict(data["current"]) if data.get("current") else None
        keys = [item.key for item in items] + ([current.key] if current else [])
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate queue item keys")
        return cls(current, items)


def duration_label(seconds: float) -> str:
    seconds = int(finite_seconds(seconds))
    if not seconds:
        return ""
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"
