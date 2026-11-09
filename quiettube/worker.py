"""Short-lived extraction process. stdout is a small JSON result, never cookies."""
from __future__ import annotations

from dataclasses import asdict
import http.cookiejar
import json
import os
from pathlib import Path
import sys
import tempfile
import time

from .models import Video, playlist_url, video_id
from .browsers import suggested_profile
from .storage import atomic_private_write

FEEDS = {
    "home": "https://www.youtube.com/feed/recommended",
    "subscriptions": "https://www.youtube.com/feed/subscriptions",
    "later": "https://www.youtube.com/playlist?list=WL",
    "liked": "https://www.youtube.com/playlist?list=LL",
}
BROWSERS = {"chromium", "chrome", "brave", "edge", "firefox", "vivaldi", "opera"}
PAGE_SIZE = 30
MAX_PAGE = 10
MAX_COOKIE_BYTES = 2 * 1024 * 1024


class QuietLogger:
    def debug(self, *args, **kwargs): pass
    def info(self, *args, **kwargs): pass
    def warning(self, *args, **kwargs): pass
    def error(self, *args, **kwargs): pass


def is_youtube_cookie(cookie) -> bool:
    return cookie.domain.lstrip(".") in {"youtube.com", "www.youtube.com", "m.youtube.com"}


def filter_session(source, destination: Path) -> int:
    """Keep only YouTube cookies, never copy the browser's other website sessions."""
    from yt_dlp.cookies import YoutubeDLCookieJar
    jar = YoutubeDLCookieJar(str(destination))
    now = time.time()
    for cookie in source:
        if is_youtube_cookie(cookie) and (cookie.expires is None or cookie.expires > now):
            jar.set_cookie(cookie)
    names = {cookie.name for cookie in jar}
    if not names.intersection({"SAPISID", "__Secure-3PAPISID", "__Secure-1PAPISID"}):
        raise ValueError("No signed-in YouTube session found. Sign in to YouTube in that browser/profile first.")
    destination.touch(mode=0o600)
    destination.chmod(0o600)
    jar.save(ignore_discard=True, ignore_expires=True)
    return len(jar)


def fetch(request: dict, session: Path | None) -> dict:
    import yt_dlp
    kind = request["kind"]
    page = int(request.get("page", 0))
    if not 0 <= page < MAX_PAGE:
        raise ValueError("Browse up to 10 pages at a time. Refine your search for more results.")
    query = str(request.get("query", "")).strip()[:500]
    start, end = page * PAGE_SIZE + 1, (page + 1) * PAGE_SIZE
    if kind in FEEDS:
        if not session:
            raise ValueError("Connect your YouTube account to load this feed.")
        url = FEEDS[kind]
    elif kind == "search":
        if not query:
            raise ValueError("Enter a search term.")
        url = f"ytsearch{end}:{query}"
    elif kind == "video":
        url = f"https://www.youtube.com/watch?v={video_id(query)}"
    elif kind == "playlist":
        url = playlist_url(query)
    else:
        raise ValueError("Unknown feed")
    options = {
        "quiet": True, "no_warnings": True, "logger": QuietLogger(),
        "skip_download": True, "extract_flat": True, "lazy_playlist": True,
        "playlist_items": f"{start}:{end}", "socket_timeout": 15,
        "retries": 1, "extractor_retries": 1, "cachedir": False,
        "noplaylist": kind == "video", "ignoreerrors": False,
        "js_runtimes": {"node": {}},
        # Parse the publish age already present in feed cards; do not resolve
        # every video separately just to retrieve its upload time.
        "extractor_args": {"youtubetab": {"approximate_date": ["true"]}},
    }
    if session:
        options["cookiefile"] = str(session)
    with yt_dlp.YoutubeDL(options) as ydl:
        result = ydl.extract_info(url, download=False)
        if not result:
            raise ValueError("YouTube returned no result.")
        entries = result.get("entries") if "entries" in result else [result]
        videos = []
        for item in entries or []:
            if not item:
                continue
            try:
                video = Video.from_info(item)
            except ValueError:
                continue  # channel/playlist cards are not playable videos
            videos.append(asdict(video))
            if len(videos) >= PAGE_SIZE:
                break
    return {"videos": videos, "has_more": len(videos) == PAGE_SIZE and page + 1 < MAX_PAGE}


def execute(request: dict) -> dict:
    action = request.get("action", "fetch")
    if action.startswith("oauth_") or request.get("account_mode") == "oauth":
        from .youtube_api import execute_account
        return execute_account(request)
    destination = Path(request["session"]) if request.get("session") else None
    with tempfile.TemporaryDirectory(prefix="quiettube-session-") as temp:
        snapshot = Path(temp) / "youtube.txt"
        if action in {"connect", "playback_connect"}:
            if not destination:
                raise ValueError("Missing session destination")
            if request.get("cookie_file"):
                source_path = Path(request["cookie_file"])
                if source_path.stat().st_size > MAX_COOKIE_BYTES:
                    raise ValueError("Cookie file is too large. Export only youtube.com cookies.")
                from yt_dlp.cookies import YoutubeDLCookieJar
                source = YoutubeDLCookieJar(str(source_path))
                source.load(ignore_discard=True, ignore_expires=True)
            else:
                from yt_dlp.cookies import extract_cookies_from_browser
                browser = request.get("browser", "")
                if browser not in BROWSERS:
                    raise ValueError("Choose a supported browser.")
                source = extract_cookies_from_browser(
                    browser, profile=request.get("profile") or suggested_profile(browser) or None,
                    logger=QuietLogger())
            filter_session(source, snapshot)
            if action == "playback_connect":
                # This validates the cookie jar, not YouTube playback. Actual mpv
                # playback is the acceptance check; OAuth feeds stay untouched.
                atomic_private_write(destination, snapshot.read_bytes())
                return {"playback_session_saved": True}
            # Verify an authenticated feed before replacing a previously working session.
            result = fetch({"kind": "subscriptions"}, snapshot)
            atomic_private_write(destination, snapshot.read_bytes())
            return {**result, "connected": True}
        if destination and destination.is_file():
            atomic_private_write(snapshot, destination.read_bytes())
        if action == "history_sync":
            from .watch_history import share_position
            return share_position(request.get("video_id", ""), request.get("position"),
                                  snapshot if snapshot.exists() else None, QuietLogger())
        if action == "like":
            from .ratings import like_video
            return like_video(request.get("video_id", ""), snapshot if snapshot.exists() else None, QuietLogger())
        if action != "fetch":
            raise ValueError("Unknown YouTube action")
        return fetch(request, snapshot if snapshot.exists() else None)


def friendly_error(error: Exception) -> str:
    # Extractor errors can contain session-bearing URLs. Never surface raw output.
    if isinstance(error, FileNotFoundError):
        return ("No cookie database was found for that browser/profile. Open YouTube in the selected browser, "
                "or choose its actual profile directory (Snap and Flatpak profiles are detected automatically).")
    if isinstance(error, PermissionError):
        return "QuietTube cannot access that browser profile. Check its file permissions or import a YouTube cookie file."
    if isinstance(error, ValueError):
        return str(error)
    message = str(error).lower()
    if any(word in message for word in ("cookie", "keyring", "decrypt")):
        return ("Could not read that browser session. Close the browser and retry, check the profile, "
                "or import a Netscape cookie file exported for youtube.com.")
    if any(word in message for word in ("sign in", "login", "private", "authentication")):
        return "YouTube requires a valid session for this content. Reconnect your account and retry."
    if any(word in message for word in ("429", "too many", "rate-limit")):
        return "YouTube is limiting requests. Wait a few minutes before trying again."
    if any(word in message for word in ("network", "resolve", "timed out", "connection", "unreachable")):
        return "Could not reach YouTube. Check your connection and retry."
    return "YouTube could not load this content. Reconnect your account or update the extractor using setup.sh."


def main():
    os.umask(0o077)
    request = {}
    try:
        raw = sys.stdin.buffer.read(16_385)
        if len(raw) > 16_384:
            raise ValueError("Request too large")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Invalid request")
        request = parsed
        result = execute(request)
        print(json.dumps({"ok": True, **result}))
    except Exception as error:
        if request.get("action") == "history_sync":
            from .watch_history import HistoryError
            message = str(error) if isinstance(error, HistoryError) else "Watch history could not be shared. Playback is unaffected."
            print(json.dumps({"ok": False, "error": message}))
        elif request.get("account_mode") == "oauth" or str(request.get("action", "")).startswith("oauth_"):
            from .account import AccountError
            message = str(error) if isinstance(error, AccountError) else "The personal OAuth request failed. Check the setup and retry."
            code = error.code if isinstance(error, AccountError) else "account_error"
            print(json.dumps({"ok": False, "error": message, "code": code}))
        else:
            print(json.dumps({"ok": False, "error": friendly_error(error)}))


if __name__ == "__main__":
    main()
