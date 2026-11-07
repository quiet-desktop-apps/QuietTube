import json

from quiettube.diagnostics import PlaybackLog, codec_name


def test_log_allowlist_excludes_urls_cookies_titles_and_raw_errors(tmp_path):
    log = PlaybackLog(tmp_path / "logs")
    log.write("snapshot", 1, **{
        "time-pos": 123.456789, "pause": True, "avsync": float("nan"),
        "url": "https://media.invalid/?sig=SECRET", "cookie": "SECRET",
        "title": "Private title", "error": "Signed URL SECRET",
        "video-codec": "SECRET", "hwdec-current": "no", "duration": "SECRET",
    })
    log.write("https://SECRET", 1)
    data = log.path.read_text()
    assert "SECRET" not in data
    row = json.loads(data)
    assert row["time-pos"] == 123.457
    assert row["pause"] is True
    assert row["hwdec-current"] == "no"
    assert "avsync" not in row
    assert log.path.stat().st_mode & 0o777 == 0o600
    assert log.path.parent.stat().st_mode & 0o777 == 0o700


def test_logs_rotate_with_bounded_disk_space(tmp_path):
    log = PlaybackLog(tmp_path)
    log.MAX_BYTES = 512
    for _ in range(100):
        log.write("snapshot", 1, position=42)
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 3
    assert all(path.stat().st_size <= 512 for path in files)
    assert all(path.stat().st_mode & 0o777 == 0o600 for path in files)


def test_unwritable_logging_does_not_break_playback(tmp_path):
    not_a_directory = tmp_path / "file"
    not_a_directory.write_text("occupied")
    log = PlaybackLog(not_a_directory)
    log.write("start", 1, position=0)
    assert not log.available


def test_codec_names_are_normalised_not_logged_verbatim():
    assert codec_name("Google VP9") == "vp9"
    assert codec_name("H.264 / AVC") == "h264"
    assert codec_name("Unknown codec SECRET") == "other"
