"""Synthetic Data API fixtures: no Google account, browser, or real tokens."""
from types import SimpleNamespace

import pytest

from quiettube.account import AccountError
from quiettube.youtube_api import YouTubeAPI, duration_seconds, video_from_api

A = "jNQXAC9IVRw"
B = "aqz-KE-bpKQ"


def video(ident, published):
    return {"id": ident, "snippet": {"title": "Fixture", "channelTitle": "Example", "publishedAt": published},
            "contentDetails": {"duration": "PT8M58S"}}


def api(tmp_path):
    return YouTubeAPI(SimpleNamespace(directory=tmp_path, access_token=lambda **_: "synthetic-token"))


def test_metadata_preserves_short_and_long_videos_with_precise_publication():
    assert duration_seconds("P1DT2H3M4.5S") == 93784.5
    assert duration_seconds("PT45S") == 45
    assert duration_seconds("unknown") == 0
    item = video(A, "2026-11-08T09:00:00Z")
    parsed = video_from_api(item)
    assert parsed.published == "2026-11-08T09:00:00Z"
    assert parsed.duration == 538
    assert parsed.id == A


def test_feed_collects_paginated_subscriptions_deduplicates_and_sorts_before_paging(tmp_path, monkeypatch):
    service = api(tmp_path)
    calls = []
    def request(resource, params, method="GET"):
        calls.append((resource, params))
        if resource == "subscriptions":
            if not params["pageToken"]:
                return {"items": [{"snippet": {"resourceId": {"channelId": "channel1"}}}], "nextPageToken": "second"}
            return {"items": [{"snippet": {"resourceId": {"channelId": "channel2"}}}]}
        if resource == "channels":
            assert params["id"] == "channel1,channel2"
            return {"items": [{"contentDetails": {"relatedPlaylists": {"uploads": "uploads1"}}},
                              {"contentDetails": {"relatedPlaylists": {"uploads": "uploads2"}}}]}
        if resource == "playlistItems":
            return {"items": [{"contentDetails": {"videoId": A, "videoPublishedAt": "2026-11-07T10:00:00Z"}},
                              {"contentDetails": {"videoId": B, "videoPublishedAt": "2026-11-08T10:00:00Z"}}]}
        assert resource == "videos"
        assert params["id"] == B + "," + A
        # API order isn't guaranteed; the published times determine the wall.
        return {"items": [video(A, "2026-11-07T10:00:00Z"), video(B, "2026-11-08T10:00:00Z")]}
    monkeypatch.setattr(service, "request", request)
    result = service.fetch({"kind": "home"})
    assert [item["id"] for item in result["videos"]] == [B, A]
    assert not result["has_more"]
    assert "2 subscriptions" in result["note"]
    assert "Shorts may appear" in result["note"]
    count = len(calls)
    assert service.fetch({"kind": "subscriptions"})["videos"] == result["videos"]
    assert len(calls) == count  # bounded snapshot reused by both navigation items
    service.fetch({"kind": "home", "refresh": True})
    assert len(calls) == count * 2
    assert (tmp_path / "account-feed.json").stat().st_mode & 0o777 == 0o600


def test_search_has_more_even_when_some_videos_are_unavailable(tmp_path, monkeypatch):
    service = api(tmp_path)
    calls = []
    def request(resource, params, method="GET"):
        calls.append((resource, params))
        if resource == "search":
            return {"items": [{"id": {"videoId": A}}, {"id": {"videoId": B}}], "nextPageToken": "next"}
        return {"items": [video(B, "2026-11-08T10:00:00Z")]}
    monkeypatch.setattr(service, "request", request)
    result = service.fetch({"kind": "search", "query": "test"})
    assert [item["id"] for item in result["videos"]] == [B]
    assert result["has_more"]
    assert result["next_page_token"] == "next"
    service.fetch({"kind": "search", "query": "test", "page": 1, "page_token": "next"})
    assert calls[-2][1]["pageToken"] == "next"
    with pytest.raises(ValueError, match="first page"):
        service.fetch({"kind": "search", "query": "test", "page": 1})


def test_like_is_an_explicit_api_write_and_watch_later_is_not_faked(tmp_path, monkeypatch):
    service = api(tmp_path)
    calls = []
    monkeypatch.setattr(service, "request", lambda *args: calls.append(args))
    assert service.like(A)["liked"]
    assert calls == [("videos/rate", {"id": A, "rating": "like"}, "POST")]
    with pytest.raises(AccountError, match="does not expose Watch Later"):
        service.fetch({"kind": "later"})
    assert len(calls) == 1


def test_failed_sync_does_not_overwrite_cached_feed_or_report_empty_success(tmp_path, monkeypatch):
    service = api(tmp_path)
    path = tmp_path / "account-feed.json"
    path.write_text("previous snapshot")
    def request(*args, **kwargs):
        raise AccountError("Quota exhausted", "quota")
    monkeypatch.setattr(service, "request", request)
    with pytest.raises(AccountError, match="Quota exhausted"):
        service.fetch({"kind": "home", "refresh": True})
    assert path.read_text() == "previous snapshot"


def test_feed_coverage_and_page_bounds_are_explicit(tmp_path, monkeypatch):
    service = api(tmp_path)
    monkeypatch.setattr("quiettube.youtube_api.MAX_SUBSCRIPTIONS", 50)
    def request(resource, params, method="GET"):
        assert resource == "subscriptions"
        return {"items": [], "nextPageToken": "more"}
    monkeypatch.setattr(service, "request", request)
    result = service.fetch({"kind": "home"})
    assert "first 50 subscriptions" in result["note"]
    assert not result["has_more"]
    with pytest.raises(ValueError, match="10 pages"):
        service.fetch({"kind": "home", "page": 10})


@pytest.mark.parametrize('status,reason,code', [
    (401, '', 'unauthorized'), (403, 'quotaExceeded', 'quota'),
    (403, 'accessNotConfigured', 'account_error'), (404, '', 'not_found'),
    (429, '', 'quota'), (503, '', 'account_error'), (302, '', 'account_error'),
])
def test_transport_uses_fixed_endpoint_and_sanitizes_failures(monkeypatch, status, reason, code):
    import json
    from quiettube.youtube_api import api_request, API_ROOT
    calls = []
    class Response:
        status_code = status
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def iter_content(self, size):
            yield json.dumps({'error': {'message': 'PRIVATE_SERVER_RESPONSE', 'errors': [{'reason': reason}]}}).encode()
    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Response()
    monkeypatch.setattr('quiettube.youtube_api.requests.request', request)
    with pytest.raises(AccountError) as error:
        api_request('synthetic-only', 'subscriptions', {'mine': 'true'})
    assert error.value.code == code
    assert 'PRIVATE_SERVER_RESPONSE' not in str(error.value)
    assert 'synthetic-only' not in str(error.value)
    assert calls[0][1] == API_ROOT + 'subscriptions'
    assert calls[0][2]['allow_redirects'] is False
    assert calls[0][2]['headers'] == {'Authorization': 'Bearer synthetic-only'}
    with pytest.raises(ValueError):
        api_request('synthetic-only', 'https://attacker.invalid/', {})
    assert len(calls) == 1


def test_transport_caps_response_and_closes_it(monkeypatch):
    from quiettube.youtube_api import api_request, MAX_RESPONSE
    closed = []
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *_): closed.append(True)
        def iter_content(self, size):
            for _ in range(MAX_RESPONSE // size + 2): yield b'x' * size
    monkeypatch.setattr('quiettube.youtube_api.requests.request', lambda *a, **kw: Response())
    with pytest.raises(AccountError, match='too much data'):
        api_request('synthetic-only', 'videos', {})
    assert closed == [True]


@pytest.mark.parametrize('second_failure', [False, True])
def test_unauthorized_refreshes_exactly_once_without_cookie_fallback(tmp_path, monkeypatch, second_failure):
    service = api(tmp_path)
    renewals, calls = [], []
    def token(**kwargs):
        renewals.append(kwargs)
        return 'renewed' if kwargs else 'old'
    service.account.access_token = token
    def request(token, *args):
        calls.append(token)
        if token == 'old' or second_failure:
            raise AccountError('renew', 'unauthorized')
        return {'items': []}
    monkeypatch.setattr('quiettube.youtube_api.api_request', request)
    if second_failure:
        with pytest.raises(AccountError) as error:
            service.request('subscriptions', {})
        assert error.value.code == 'sign_in_required'
    else:
        assert service.request('subscriptions', {}) == {'items': []}
    assert calls == ['old', 'renewed']
    assert renewals == [{}, {'rejected_token': 'old'}]
