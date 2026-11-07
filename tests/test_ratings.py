import pytest

from quiettube.ratings import RatingClient, ensure_liked, like_control, like_video

IDENT = "jNQXAC9IVRw"


def response(status="INDIFFERENT", ident=IDENT, logged_out=False):
    return {
        "responseContext": {"mainAppWebResponseContext": {"loggedOut": logged_out}},
        "contents": {"videoPrimaryInfoRenderer": {"menu": {"likeButtonViewModel": {
            "likeStatusEntity": {"key": "rating-key", "likeStatus": status},
            "toggleButtonViewModel": {"defaultButtonViewModel": {"onTap": {"commands": [{
                "innertubeCommand": {"likeEndpoint": {
                    "status": "LIKE", "target": {"videoId": ident}, "likeParams": "fixture-params"}}
            }]}}}
        }}}}
    }


class Extractor:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.writes = []

    def generate_api_headers(self, **_):
        return {"Authorization": "synthetic-test-auth"}

    def _extract_response(self, *_, **__):
        return next(self.responses)

    def _extract_context(self, config, client):
        return {"client": {"clientName": "WEB"}}

    def _call_api(self, **kwargs):
        self.writes.append(kwargs)
        return {"responseContext": {}}


def test_like_reads_actual_state_sends_target_and_verifies():
    extractor = Extractor([response(), response("LIKE")])
    result = ensure_liked(RatingClient(extractor, {"LOGGED_IN": True}), IDENT)
    assert result == {"video_id": IDENT, "liked": True}
    assert len(extractor.writes) == 1
    assert extractor.writes[0]["ep"] == "like/like"
    assert extractor.writes[0]["query"] == {"target": {"videoId": IDENT}, "params": "fixture-params"}


def test_already_liked_is_idempotent_without_another_write():
    extractor = Extractor([response("LIKE")])
    assert ensure_liked(RatingClient(extractor, {}), IDENT)["liked"]
    assert not extractor.writes


def test_expired_session_never_sends_like():
    extractor = Extractor([response(logged_out=True)])
    with pytest.raises(ValueError, match="Reconnect"):
        ensure_liked(RatingClient(extractor, {"LOGGED_IN": True}), IDENT)
    assert not extractor.writes


def test_missing_authentication_evidence_never_sends_like():
    data = response()
    data.pop("responseContext")
    extractor = Extractor([data])
    with pytest.raises(ValueError, match="Reconnect"):
        ensure_liked(RatingClient(extractor, {}), IDENT)
    assert not extractor.writes


def test_unconfirmed_rating_is_not_reported_as_success():
    extractor = Extractor([response(), response()])
    with pytest.raises(ValueError, match="not confirmed"):
        ensure_liked(RatingClient(extractor, {}), IDENT)
    assert len(extractor.writes) == 1


def test_recommendation_or_comment_like_cannot_target_another_video():
    with pytest.raises(ValueError, match="unavailable"):
        like_control(response(ident="aqz-KE-bpKQ"), IDENT)
    with pytest.raises(ValueError, match="did not provide"):
        like_control({"comments": {"likeEndpoint": {"target": {"videoId": IDENT}}}}, IDENT)


def test_framework_update_overrides_stale_initial_rating():
    data = response()
    data["frameworkUpdates"] = {"mutations": [{"payload": {"likeStatusEntity": {
        "key": "rating-key", "likeStatus": "LIKE"}}}]}
    assert like_control(data, IDENT)[0] == "LIKE"


def test_legacy_toggle_control_is_supported():
    data = {"videoPrimaryInfoRenderer": {"toggleButtonRenderer": {
        "isToggled": True, "defaultServiceEndpoint": {"likeEndpoint": {
            "status": "LIKE", "target": {"videoId": IDENT}}}}}}
    assert like_control(data, IDENT)[0] == "LIKE"


def test_like_requires_session_file(tmp_path):
    with pytest.raises(ValueError, match="Connect your YouTube account"):
        like_video(IDENT, tmp_path / "missing", None)


def test_rating_adapter_initializes_authenticated_client_without_download(tmp_path, monkeypatch):
    import yt_dlp
    import yt_dlp.extractor.youtube
    session = tmp_path / "session"
    session.write_text("synthetic session")
    options = {}
    extractor = Extractor([response(), response("LIKE")])
    initialized = []
    extractor.initialize = lambda: initialized.append(True)
    extractor._download_ytcfg = lambda client, ident: {"LOGGED_IN": True}
    class Downloader:
        def __init__(self, params): options.update(params)
        def __enter__(self): return self
        def __exit__(self, *_): pass
    monkeypatch.setattr(yt_dlp, "YoutubeDL", Downloader)
    monkeypatch.setattr(yt_dlp.extractor.youtube, "YoutubeTabIE", lambda _: extractor)
    assert like_video(IDENT, session, None)["liked"]
    assert initialized == [True]
    assert options["cookiefile"] == str(session)
    assert options["extractor_retries"] == 0
    assert len(extractor.writes) == 1
