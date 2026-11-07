"""Authenticated YouTube Like actions, isolated from browsing and playback.

Uses the same web-client command exposed by the watch page. Endpoint mapping is
documented in YouTube.js's LikeEndpoint implementation; yt-dlp supplies the pinned
web-client context and cookie authentication. Never log responses or headers.
"""
from pathlib import Path

from .models import video_id


def dictionaries(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from dictionaries(child)
    elif isinstance(value, list):
        for child in value:
            yield from dictionaries(child)


def like_control(response: dict, ident: str) -> tuple[str, dict]:
    """Read this video's control, ignoring recommendation/comment ratings."""
    primary = next((node["videoPrimaryInfoRenderer"] for node in dictionaries(response)
                    if isinstance(node.get("videoPrimaryInfoRenderer"), dict)), None)
    if primary is None:
        raise ValueError("YouTube did not provide this video's Like control. Try again later.")
    for node in dictionaries(primary):
        entity = node.get("likeStatusEntity")
        if isinstance(entity, dict) and entity.get("likeStatus") in {"LIKE", "DISLIKE", "INDIFFERENT"}:
            endpoint = next((item["likeEndpoint"] for item in dictionaries(node)
                             if isinstance(item.get("likeEndpoint"), dict)
                             and item["likeEndpoint"].get("status") == "LIKE"
                             and item["likeEndpoint"].get("target", {}).get("videoId") == ident), None)
            if endpoint:
                status = entity["likeStatus"]
                # Framework updates may override the initial view-model state.
                for item in dictionaries(response.get("frameworkUpdates", {})):
                    updated = item.get("likeStatusEntity", {})
                    if (isinstance(updated, dict) and entity.get("key")
                            and updated.get("key") == entity.get("key")
                            and updated.get("likeStatus") in {"LIKE", "DISLIKE", "INDIFFERENT"}):
                        status = updated["likeStatus"]
                return status, endpoint
        toggle = node.get("toggleButtonRenderer")
        if isinstance(toggle, dict):
            endpoint = toggle.get("defaultServiceEndpoint", {}).get("likeEndpoint", {})
            if endpoint.get("status") == "LIKE" and endpoint.get("target", {}).get("videoId") == ident:
                if isinstance(toggle.get("isToggled"), bool):
                    return "LIKE" if toggle["isToggled"] else "INDIFFERENT", endpoint
    raise ValueError("YouTube's Like control is unavailable for this video. No rating was changed.")


class RatingClient:
    def __init__(self, extractor, config):
        self.extractor, self.config = extractor, config
        self.headers = extractor.generate_api_headers(ytcfg=config)

    def read(self, ident):
        response = self.extractor._extract_response(
            ident, {"videoId": ident}, ep="next", ytcfg=self.config, headers=self.headers)
        logged_out = response.get("responseContext", {}).get("mainAppWebResponseContext", {}).get("loggedOut")
        if logged_out is True or (logged_out is not False and self.config.get("LOGGED_IN") is not True):
            raise ValueError("Your YouTube session has expired. Reconnect your account before liking a video.")
        return like_control(response, ident)

    def send_like(self, ident, endpoint):
        query = {"target": {"videoId": ident}}
        if isinstance(endpoint.get("likeParams"), str):
            query["params"] = endpoint["likeParams"]
        response = self.extractor._call_api(
            ep="like/like", query=query, video_id=ident, headers=self.headers,
            context=self.extractor._extract_context(self.config, "web"))
        if not response or response.get("error"):
            raise ValueError("YouTube did not confirm the Like request. Check Liked videos before retrying.")


def ensure_liked(client, ident: str) -> dict:
    ident = video_id(ident)
    state, endpoint = client.read(ident)
    if state != "LIKE":
        client.send_like(ident, endpoint)
        state, _ = client.read(ident)
        if state != "LIKE":
            raise ValueError("YouTube has not confirmed this Like. Check Liked videos before retrying.")
    return {"video_id": ident, "liked": True}


def like_video(ident: str, session: Path | None, logger) -> dict:
    if not session or not session.is_file():
        raise ValueError("Connect your YouTube account before liking a video.")
    ident = video_id(ident)
    from yt_dlp import YoutubeDL
    from yt_dlp.extractor.youtube import YoutubeTabIE
    with YoutubeDL({"cookiefile": str(session), "logger": logger, "quiet": True,
                    "cachedir": False, "socket_timeout": 15, "extractor_retries": 0,
                    "retries": 0}) as downloader:
        extractor = YoutubeTabIE(downloader)
        extractor.initialize()
        config = extractor._download_ytcfg("web", ident)
        return ensure_liked(RatingClient(extractor, config), ident)
