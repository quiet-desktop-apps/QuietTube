"""Bounded account feeds through the YouTube Data API, without browser cookies."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import re
import time
from urllib.parse import parse_qs, urlparse

import requests

from .account import Account, AccountError, CACHE_FILE
from .models import Video, playlist_url, publication_sort_key, video_id
from .storage import atomic_private_write

API_ROOT = "https://www.googleapis.com/youtube/v3/"
PAGE_SIZE = 30
MAX_PAGES = 10
MAX_SUBSCRIPTIONS = 500
UPLOADS_PER_CHANNEL = 10
MAX_FEED = PAGE_SIZE * MAX_PAGES
CACHE_SECONDS = 600
MAX_RESPONSE = 2 * 1024 * 1024


def api_request(token, resource, params, method="GET"):
    if resource not in {"subscriptions", "channels", "playlistItems", "videos", "videos/rate", "search"}:
        raise ValueError("Unknown YouTube API resource")
    try:
        with requests.request(method, API_ROOT + resource, params=params,
                              headers={"Authorization": "Bearer " + token},
                              timeout=(10, 20), stream=True, allow_redirects=False) as response:
            raw = bytearray()
            for chunk in response.iter_content(65_536):
                raw.extend(chunk)
                if len(raw) > MAX_RESPONSE:
                    raise AccountError("YouTube returned too much data. Try a smaller request.")
            if response.status_code == 401:
                raise AccountError("Google access needs renewal.", "unauthorized")
            if response.status_code == 429:
                raise AccountError("YouTube is limiting requests. Please retry later.", "quota")
            if response.status_code >= 500:
                raise AccountError("YouTube is temporarily unavailable. Please retry later.")
            if not 200 <= response.status_code < 300:
                try:
                    reasons = {item.get("reason") for item in json.loads(raw).get("error", {}).get("errors", [])}
                except (ValueError, AttributeError, TypeError):
                    reasons = set()
                if reasons & {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"}:
                    raise AccountError("Your Google project's YouTube API quota is exhausted. Check its Quotas page and retry later.", "quota")
                if reasons & {"accessNotConfigured", "serviceDisabled"}:
                    raise AccountError("Enable YouTube Data API v3 in the Google project that owns your Desktop client.")
                if response.status_code == 404:
                    raise AccountError("This video or playlist is unavailable.", "not_found")
                raise AccountError("YouTube denied this request. Check that YouTube access was approved and the content is available.")
            return json.loads(raw) if raw else {}
    except requests.RequestException:
        raise AccountError("Could not reach YouTube. Check your connection and retry.") from None
    except ValueError:
        raise AccountError("Could not read YouTube's response. Please retry.") from None


def duration_seconds(value):
    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?)?", value or "")
    return sum(float(part or 0) * unit for part, unit in zip(match.groups(), (86400, 3600, 60, 1))) if match else 0


def video_from_api(item):
    snippet = item.get("snippet", {})
    return Video(video_id(item["id"]), str(snippet.get("title", "Untitled video"))[:500],
                 str(snippet.get("channelTitle", ""))[:200],
                 duration_seconds(item.get("contentDetails", {}).get("duration", "")),
                 str(snippet.get("publishedAt", ""))[:30])


class YouTubeAPI:
    def __init__(self, account):
        self.account = account

    def request(self, resource, params, method="GET"):
        token = self.account.access_token()
        try:
            return api_request(token, resource, params, method)
        except AccountError as error:
            if error.code != "unauthorized":
                raise
        # Refresh once, not a retry loop. Concurrent workers reuse a rotated token.
        token = self.account.access_token(rejected_token=token)
        try:
            return api_request(token, resource, params, method)
        except AccountError as error:
            if error.code == "unauthorized":
                raise AccountError("Google denied renewed access. Sign in with Google again.", "sign_in_required") from None
            raise

    def details(self, ids):
        videos = {}
        for start in range(0, len(ids), 50):
            data = self.request("videos", {"part": "snippet,contentDetails", "id": ",".join(ids[start:start + 50])})
            for item in data.get("items", [])[:50]:
                try:
                    video = video_from_api(item)
                    videos[video.id] = video
                except (ValueError, KeyError, TypeError):
                    continue
        return [videos[ident] for ident in ids if ident in videos]

    def subscriptions_feed(self, page, refresh=False):
        # Validate/renew authorization even when displaying a cached snapshot.
        self.account.access_token()
        path = self.account.directory / CACHE_FILE
        snapshot = None
        try:
            if path.stat().st_size <= MAX_RESPONSE:
                cached = json.loads(path.read_text())
                if (not refresh and 0 <= time.time() - cached["created"] < CACHE_SECONDS
                        and len(cached["videos"]) <= MAX_FEED):
                    snapshot = cached
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if snapshot is None:
            channels, continuation = [], ""
            for _ in range(MAX_SUBSCRIPTIONS // 50):
                result = self.request("subscriptions", {"part": "snippet", "mine": "true", "maxResults": 50,
                                                        "order": "alphabetical", "pageToken": continuation})
                for item in result.get("items", [])[:50]:
                    ident = item.get("snippet", {}).get("resourceId", {}).get("channelId")
                    if ident and ident not in channels:
                        channels.append(ident)
                continuation = result.get("nextPageToken", "")
                if not continuation:
                    break
            playlists = []
            for start in range(0, len(channels), 50):
                result = self.request("channels", {"part": "contentDetails", "id": ",".join(channels[start:start + 50])})
                for item in result.get("items", [])[:50]:
                    uploads = item.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
                    if uploads:
                        playlists.append(uploads)

            def recent(playlist):
                try:
                    result = self.request("playlistItems", {"part": "contentDetails", "playlistId": playlist,
                                                            "maxResults": UPLOADS_PER_CHANNEL})
                    return result.get("items", [])[:UPLOADS_PER_CHANNEL], False
                except AccountError as error:
                    if error.code == "not_found":
                        return [], True
                    raise  # quota/network/auth errors must not masquerade as an empty feed

            uploads, skipped = {}, 0
            with ThreadPoolExecutor(max_workers=4) as pool:
                for items, unavailable in pool.map(recent, playlists):
                    skipped += unavailable
                    for item in items:
                        detail = item.get("contentDetails", {})
                        try:
                            ident = video_id(detail.get("videoId", ""))
                        except (ValueError, AttributeError):
                            continue
                        uploads[ident] = detail.get("videoPublishedAt", "")
            ids = sorted(uploads, key=lambda ident: uploads[ident], reverse=True)[:MAX_FEED]
            videos = sorted(self.details(ids), key=publication_sort_key, reverse=True)
            note = (f"Newest uploads from {len(playlists)} subscriptions · up to {UPLOADS_PER_CHANNEL} recent uploads per channel, "
                    f"{MAX_FEED} videos total. Shorts may appear; the API does not reliably identify them.")
            if continuation:
                note += f" Coverage limited to the first {MAX_SUBSCRIPTIONS} subscriptions alphabetically."
            if skipped:
                note += f" {skipped} upload lists unavailable."
            snapshot = {"created": time.time(), "videos": [asdict(v) for v in videos], "note": note}
            atomic_private_write(path, json.dumps(snapshot).encode())
        start = page * PAGE_SIZE
        return {"videos": snapshot["videos"][start:start + PAGE_SIZE],
                "has_more": start + PAGE_SIZE < len(snapshot["videos"]), "note": snapshot["note"]}

    def fetch(self, request):
        kind, page = request["kind"], int(request.get("page", 0))
        if not 0 <= page < MAX_PAGES:
            raise ValueError("Browse up to 10 pages at a time. Refine your search for more results.")
        if kind in {"home", "subscriptions"}:
            result = self.subscriptions_feed(page, bool(request.get("refresh")))
        elif kind == "later":
            raise AccountError("Google does not expose Watch Later through this API. Use QuietTube's local queue to save videos.",
                               "unsupported")
        elif kind == "video":
            result = {"videos": [asdict(v) for v in self.details([video_id(request.get("query", ""))])], "has_more": False}
        else:
            query = str(request.get("query", "")).strip()[:500]
            if kind == "liked":
                channels = self.request("channels", {"part": "contentDetails", "mine": "true"})
                items = channels.get("items", [])
                playlist = (items[0].get("contentDetails", {}).get("relatedPlaylists", {}).get("likes") if items else None)
                if not playlist:
                    return {"videos": [], "has_more": False, "account_connected": True}
            elif kind == "playlist":
                playlist = parse_qs(urlparse(playlist_url(query)).query)["list"][0]
            elif kind != "search" or not query:
                raise ValueError("Enter a search term or supported YouTube link.")
            # Page tokens stay in the request/response, never in the saved account.
            token = str(request.get("page_token", ""))[:2048]
            if page and not token:
                raise ValueError("Reload the first page before continuing.")
            if kind == "search":
                data = self.request("search", {"part": "id", "q": query, "type": "video",
                                               "maxResults": PAGE_SIZE, "pageToken": token})
                ids = [item.get("id", {}).get("videoId", "") for item in data.get("items", [])[:PAGE_SIZE]]
            else:
                data = self.request("playlistItems", {"part": "contentDetails", "playlistId": playlist,
                                                      "maxResults": PAGE_SIZE, "pageToken": token})
                ids = [item.get("contentDetails", {}).get("videoId", "") for item in data.get("items", [])[:PAGE_SIZE]]
            ids = [ident for ident in ids if re.fullmatch(r"[A-Za-z0-9_-]{11}", ident)]
            next_token = data.get("nextPageToken", "")
            result = {"videos": [asdict(v) for v in self.details(ids)],
                      "has_more": bool(next_token) and page + 1 < MAX_PAGES, "next_page_token": next_token}
        return {**result, "account_connected": True}

    def like(self, ident):
        ident = video_id(ident)
        self.request("videos/rate", {"id": ident, "rating": "like"}, "POST")
        return {"video_id": ident, "liked": True, "account_connected": True}


def execute_account(request):
    account = Account(request["account_dir"])
    action = request.get("action", "fetch")
    if action == "oauth_configure":
        return account.configure(request)
    if action == "oauth_forget":
        return account.forget()
    if action == "oauth_connect":
        return account.connect()
    api = YouTubeAPI(account)
    if action == "like":
        return api.like(request.get("video_id", ""))
    if action != "fetch":
        raise ValueError("Unknown YouTube action")
    return api.fetch(request)
