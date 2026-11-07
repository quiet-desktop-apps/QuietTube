import pytest
from yt_dlp import YoutubeDL

from quiettube.player import PlaybackDiagnostics, playback_format


def stream(ident, height=None, *, hls=False, combined=False):
    return {
        "format_id": ident, "url": f"https://example.invalid/{ident}",
        "ext": "mp4" if height else "m4a",
        "protocol": "m3u8_native" if hls else "https", "height": height,
        "vcodec": "avc1" if height else "none",
        "acodec": "aac" if height is None or combined else "none",
    }


def select(formats, height=720):
    with YoutubeDL({"quiet": True, "cachedir": False, "format": playback_format(height)}) as ydl:
        info = ydl.process_ie_result({
            "id": "fixture", "title": "Synthetic stream selection", "formats": formats,
            "extractor": "fixture", "webpage_url": "https://example.invalid/watch",
        }, download=False)
    return [f["format_id"] for f in info.get("requested_formats", [info])]


@pytest.mark.parametrize("height", [480, 720, 1080, 1440, 2160])
def test_prefers_hls_video_and_audio_with_resolution_limit(height):
    formats = [stream("direct-audio"), stream("hls-audio", hls=True)]
    for resolution in (480, 720, 1080, 1440, 2160):
        formats += [stream(f"direct-{resolution}", resolution), stream(f"hls-{resolution}", resolution, hls=True)]
    assert select(formats, height) == [f"hls-{height}", "hls-audio"]


def test_falls_back_to_direct_when_hls_not_offered():
    assert select([stream("audio"), stream("720", 720), stream("1080", 1080)]) == ["720", "audio"]


def test_prefers_combined_hls_without_separate_audio():
    assert select([stream("audio"), stream("direct", 720),
                   stream("combined", 720, hls=True, combined=True)]) == ["combined"]


def test_incomplete_hls_pair_falls_back_to_playable_direct_pair():
    assert select([stream("audio"), stream("direct", 720),
                   stream("silent-hls", 720, hls=True)]) == ["direct", "audio"]


def test_combined_direct_fallback():
    assert select([stream("combined", 360, combined=True)]) == ["combined"]


@pytest.mark.parametrize("message,category", [
    ("[ffmpeg] HTTP error 403 Forbidden", "forbidden"),
    ("Server returned 403 Forbidden", "forbidden"),
    ("HTTP error 429 Too Many Requests", "limited"),
    ("Sign in to confirm your age", "account"),
    ("Connection timed out", "network"),
    ("Requested format is not available", "format"),
    ("Unrecognized error at https://example.invalid/?sig=secret403", "unknown"),
])
def test_error_classification_never_exposes_raw_diagnostics(message, category):
    diagnostics = PlaybackDiagnostics()
    diagnostics.observe(message + " https://media.invalid/?token=PRIVATE Cookie: SECRET")
    assert diagnostics.category == category
    assert "PRIVATE" not in diagnostics.error()
    assert "SECRET" not in diagnostics.error()
    assert "https://" not in diagnostics.error()
    assert "preserved" in diagnostics.error()


def test_repeated_logs_retain_only_category_and_do_not_hide_specific_error():
    diagnostics = PlaybackDiagnostics()
    diagnostics.observe("HTTP error 403 Forbidden")
    for _ in range(10_000):
        diagnostics.observe("Failed to open https://example.invalid/?secret=123")
    assert vars(diagnostics) == {"category": "forbidden"}
