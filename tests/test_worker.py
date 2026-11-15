from http.cookiejar import Cookie
import time

import pytest

from quiettube import worker


def cookie(domain=".youtube.com", name="SAPISID", expires=None):
    return Cookie(0, name, "FAKE_TEST_VALUE", None, False, domain, True,
                  domain.startswith("."), "/", True, True, expires, True, None, None, {})


def test_session_filter_never_keeps_unrelated_browser_credentials(tmp_path):
    from yt_dlp.cookies import YoutubeDLCookieJar
    path = tmp_path / "session"
    source = [cookie(), cookie(".google.com", "SID"), cookie("bank.example", "SESSION"),
              cookie("youtube.com.evil.test"), cookie(name="expired", expires=int(time.time()) - 5)]
    assert worker.filter_session(source, path) == 1
    loaded = YoutubeDLCookieJar(str(path))
    loaded.load(ignore_discard=True, ignore_expires=True)
    assert [(item.domain, item.name) for item in loaded] == [(".youtube.com", "SAPISID")]
    assert path.stat().st_mode & 0o777 == 0o600


def test_logged_out_browser_cannot_look_connected(tmp_path):
    with pytest.raises(ValueError, match="No signed-in"):
        worker.filter_session([cookie(name="CONSENT")], tmp_path / "session")


def test_expired_login_cookie_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="No signed-in"):
        worker.filter_session([cookie(expires=int(time.time()) - 1)], tmp_path / "session")


def test_failed_account_check_preserves_existing_session(tmp_path, monkeypatch):
    source, destination = tmp_path / "import.txt", tmp_path / "saved.txt"
    worker.filter_session([cookie()], source)
    destination.write_text("old session")
    def fail(*_):
        raise RuntimeError("Sign in required token=SECRET")
    monkeypatch.setattr(worker, "fetch", fail)
    with pytest.raises(RuntimeError):
        worker.execute({"action": "connect", "cookie_file": str(source), "session": str(destination)})
    assert destination.read_text() == "old session"


def test_successful_connect_saves_only_validated_youtube_session(tmp_path, monkeypatch):
    source, destination = tmp_path / "import.txt", tmp_path / "saved.txt"
    worker.filter_session([cookie()], source)
    calls = []
    def fetch(request, session):
        calls.append((request, session.exists()))
        return {"videos": [], "has_more": False}
    monkeypatch.setattr(worker, "fetch", fetch)
    result = worker.execute({"action": "connect", "cookie_file": str(source), "session": str(destination)})
    assert result["connected"]
    assert calls == [({"kind": "subscriptions"}, True)]
    assert destination.stat().st_mode & 0o777 == 0o600


def test_error_messages_do_not_expose_raw_session_urls():
    for text in ["https://secret?token=PRIVATE", "Cookie decrypt PRIVATE", "login PRIVATE", "connection PRIVATE", "429 PRIVATE"]:
        assert "PRIVATE" not in worker.friendly_error(RuntimeError(text))


def test_missing_profile_is_distinguished_from_decryption_failure():
    message = worker.friendly_error(FileNotFoundError("cookie database at PRIVATE"))
    assert "No cookie database" in message
    assert "PRIVATE" not in message
    assert "file permissions" in worker.friendly_error(PermissionError("PRIVATE"))


def test_browser_connection_resolves_snap_profile_in_worker(tmp_path, monkeypatch):
    import yt_dlp.cookies
    calls = []
    monkeypatch.setattr(worker, "suggested_profile", lambda browser: "/synthetic/snap/chromium")
    def extract(browser, profile, logger):
        calls.append((browser, profile))
        return [cookie()]
    monkeypatch.setattr(yt_dlp.cookies, "extract_cookies_from_browser", extract)
    monkeypatch.setattr(worker, "fetch", lambda *_: {"videos": [], "has_more": False})
    result = worker.execute({"action": "connect", "browser": "chromium", "session": str(tmp_path / "session")})
    assert result["connected"]
    assert calls == [("chromium", "/synthetic/snap/chromium")]
    worker.execute({"action": "connect", "browser": "chromium", "profile": "/explicit/profile", "session": str(tmp_path / "session")})
    assert calls[-1] == ("chromium", "/explicit/profile")


def test_authenticated_feeds_require_session():
    with pytest.raises(ValueError, match="Connect your YouTube account"):
        worker.fetch({"kind": "home"}, None)


def test_pagination_is_bounded():
    with pytest.raises(ValueError, match="10 pages"):
        worker.fetch({"kind": "search", "query": "test", "page": 10}, None)


def test_search_is_flat_paginated_and_does_not_download(monkeypatch):
    import yt_dlp
    captured = {}
    class YDL:
        def __init__(self, options): captured.update(options)
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def extract_info(self, url, download):
            captured["url"], captured["download"] = url, download
            return {"entries": [{"id": "jNQXAC9IVRw", "title": "Test", "channel": "A"},
                                {"id": "UC_channel", "title": "Not a video"}]}
    monkeypatch.setattr(yt_dlp, "YoutubeDL", YDL)
    result = worker.fetch({"kind": "search", "query": "rust tutorials", "page": 1}, None)
    assert captured["playlist_items"] == "31:60"
    assert captured["url"] == "ytsearch60:rust tutorials"
    assert captured["extract_flat"] is True
    assert captured["extractor_args"]["youtubetab"]["approximate_date"] == ["true"]
    assert captured["download"] is False
    assert len(result["videos"]) == 1


def test_like_worker_uses_disposable_session_copy(tmp_path, monkeypatch):
    from quiettube import ratings
    source = tmp_path / "saved-session"
    source.write_text("synthetic session")
    snapshots = []
    def like(ident, session, logger):
        assert ident == "jNQXAC9IVRw"
        assert session != source
        assert session.read_text() == "synthetic session"
        snapshots.append(session)
        session.write_text("updated only in worker")
        return {"video_id": ident, "liked": True}
    monkeypatch.setattr(ratings, "like_video", like)
    result = worker.execute({"action": "like", "video_id": "jNQXAC9IVRw", "session": str(source)})
    assert result["liked"]
    assert source.read_text() == "synthetic session"
    assert not snapshots[0].exists()


def test_playback_import_is_private_and_does_not_fetch_or_change_feeds(tmp_path, monkeypatch):
    from yt_dlp.cookies import YoutubeDLCookieJar
    source, destination = tmp_path / 'import.txt', tmp_path / 'playback.txt'
    jar = YoutubeDLCookieJar(str(source))
    for item in [cookie(), cookie('bank.example', 'SECRET')]:
        jar.set_cookie(item)
    jar.save(ignore_discard=True, ignore_expires=True)
    def unexpected(*_):
        pytest.fail('Playback import must not fetch account feeds')
    monkeypatch.setattr(worker, 'fetch', unexpected)
    result = worker.execute({'action': 'playback_connect', 'cookie_file': str(source), 'session': str(destination)})
    assert result == {'playback_session_saved': True}
    saved = YoutubeDLCookieJar(str(destination))
    saved.load(ignore_discard=True, ignore_expires=True)
    assert [(c.domain, c.name) for c in saved] == [('.youtube.com', 'SAPISID')]
    assert destination.stat().st_mode & 0o777 == 0o600
    assert 'FAKE_TEST_VALUE' not in str(result)
    # An invalid replacement leaves the previous working session intact.
    previous = destination.read_bytes()
    source.write_text('# Netscape HTTP Cookie File\n')
    with pytest.raises(ValueError, match='No signed-in'):
        worker.execute({'action': 'playback_connect', 'cookie_file': str(source), 'session': str(destination)})
    assert destination.read_bytes() == previous
