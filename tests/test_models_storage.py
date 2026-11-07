import random
import sqlite3

import pytest

from quiettube.models import PlaybackQueue, QueueItem, Video, duration_label, playlist_url, video_id
from quiettube.storage import Store, atomic_private_write


def video(index=0):
    return Video(f"{index:011d}", f"Video {index}", "Test channel", 120)


def test_publication_sort_handles_dates_offsets_and_missing_values():
    from quiettube.models import publication_sort_key
    dates = ["", "20260101", "2026-01-03T01:00:00+02:00", "bad", "2026-01-03T00:00:00Z", "2026-01-02"]
    videos = [Video(f"{i:011d}", "Test", published=date) for i, date in enumerate(dates)]
    assert [v.published for v in sorted(videos, key=publication_sort_key, reverse=True)] == [
        dates[4], dates[2], dates[5], dates[1], dates[0], dates[3]]


def test_completion_survives_replay_checkpoints_and_database_reopen(tmp_path):
    store = Store(tmp_path)
    store.record(video(1), 120, completed=True)
    store.record(video(1), 5)
    store.record(video(2), 90)
    store.close()
    reopened = Store(tmp_path)
    assert reopened.completed_ids() == {video(1).id}
    assert reopened.db.execute("SELECT position FROM history WHERE video_id=?", (video(1).id,)).fetchone() == (5,)
    reopened.close()


@pytest.mark.parametrize("seconds,expected", [
    (20, "Just now"), (60, "1m ago"), (3599, "59m ago"), (3600, "1h ago"),
    (6 * 86400, "6d ago"), (14 * 86400, "2w ago"),
    (90 * 86400, "3mo ago"), (365 * 86400, "1y ago"),
])
def test_compact_publication_age(seconds, expected):
    from datetime import datetime, timedelta, timezone
    from quiettube.models import published_label
    now = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
    assert published_label((now - timedelta(seconds=seconds)).isoformat(), now) == expected


def test_missing_invalid_future_and_date_only_publication_times():
    from datetime import datetime, timezone
    from quiettube.models import published_label
    now = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
    assert published_label("", now) == ""
    assert published_label("invalid", now) == ""
    assert published_label("20260230", now) == ""
    assert published_label("20261106", now) == "Today"
    assert published_label("2026-11-05", now) == "1d ago"
    assert published_label("2026-11-07T12:00:00Z", now) == "Upcoming"
    assert published_label("2026-11-06T13:00:00+02:00", now) == "1h ago"


def test_extraction_preserves_hour_precision_and_falls_back_to_upload_date():
    from datetime import datetime, timezone
    from quiettube.models import published_label
    now = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)
    info = {"id": "jNQXAC9IVRw", "title": "Fixture", "timestamp": now.timestamp() - 3600,
            "upload_date": "20261106"}
    item = Video.from_info(info)
    assert published_label(item.published, now) == "1h ago"
    info["timestamp"] = float("nan")
    assert Video.from_info(info).published == "20261106"


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/watch?v=jNQXAC9IVRw&t=4", "https://youtu.be/jNQXAC9IVRw?si=abc",
    "https://m.youtube.com/shorts/jNQXAC9IVRw", "https://youtube.com/live/jNQXAC9IVRw",
    "jNQXAC9IVRw",
])
def test_normalizes_video_urls(url):
    assert video_id(url) == "jNQXAC9IVRw"


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "https://youtube.com.attacker.test/watch?v=jNQXAC9IVRw",
    "https://youtube.com@attacker.test/watch?v=jNQXAC9IVRw", "--script=/tmp/test",
    "https://example.com/jNQXAC9IVRw", "https://youtube.com/watch?v=x",
    "javascript:alert(1)", "https://user:password@youtube.com/watch?v=jNQXAC9IVRw",
])
def test_rejects_non_youtube_input(url):
    with pytest.raises(ValueError):
        video_id(url)


def test_playlist_url_strips_extraneous_parameters():
    assert playlist_url("https://www.youtube.com/watch?v=jNQXAC9IVRw&list=PL_test-123&token=secret") == "https://www.youtube.com/playlist?list=PL_test-123"
    with pytest.raises(ValueError):
        playlist_url("https://example.com/?list=WL")


def test_middle_insertion_reorder_and_duplicates():
    queue = PlaybackQueue()
    a, b, c, d = [video(n) for n in range(4)]
    for item in (a, b, c, d):
        queue.add(item)
    queue.advance()
    inserted = queue.add(video(9), 1)
    assert [item.video.id for item in queue.upcoming] == [b.id, video(9).id, c.id, d.id]
    queue.move(inserted.key, 3)
    assert queue.upcoming[-1].key == inserted.key
    duplicate = queue.add(b, 0)
    queue.remove(duplicate.key)
    assert queue.upcoming[0].video == b
    assert queue.current.video == a


def test_randomized_queue_operations_keep_identity_and_order():
    rng = random.Random(2351)
    queue, expected = PlaybackQueue(), []
    for _ in range(3000):
        action = rng.choice(["add", "move", "remove", "advance"])
        if action == "add":
            index = rng.randint(0, len(expected))
            item = queue.add(video(rng.randrange(10)), index)
            expected.insert(index, item.key)
        elif expected and action == "move":
            old, new = rng.randrange(len(expected)), rng.randrange(len(expected))
            key = expected.pop(old)
            expected.insert(new, key)
            queue.move(key, new)
        elif expected and action == "remove":
            key = expected.pop(rng.randrange(len(expected)))
            queue.remove(key)
        elif action == "advance":
            key = expected.pop(0) if expected else None
            current = queue.advance()
            assert (current.key if current else None) == key
        assert [item.key for item in queue.upcoming] == expected


def test_play_now_retains_interrupted_position():
    queue = PlaybackQueue()
    queue.play_now(video(1))
    queue.current.position = 51.25
    queue.play_now(video(2))
    assert queue.current.video == video(2)
    assert queue.upcoming[0].position == 51.25


def test_queue_limit_prevents_unbounded_growth():
    queue = PlaybackQueue()
    for n in range(queue.MAX_ITEMS):
        queue.add(video(n))
    with pytest.raises(ValueError):
        queue.add(video(1))
    queue.current = QueueItem(video(9))
    with pytest.raises(ValueError):
        queue.play_now(video(8))
    assert queue.current.video == video(9)


def test_save_reopen_preserves_queue_position_and_settings(tmp_path):
    store = Store(tmp_path / "data")
    queue = PlaybackQueue()
    queue.add(video(1))
    queue.add(video(2))
    queue.advance()
    queue.current.position = 42.125
    store.save_queue(queue)
    store.set("quality", 1080)
    store.record(video(1), 42.125)
    store.close()
    reopened = Store(tmp_path / "data")
    assert reopened.load_queue().to_dict() == queue.to_dict()
    assert reopened.get("quality") == 1080
    assert reopened.history() == [video(1)]
    assert (tmp_path / "data").stat().st_mode & 0o777 == 0o700
    assert (tmp_path / "data/library.sqlite3").stat().st_mode & 0o777 == 0o600
    reopened.close()


def test_corrupt_queue_is_recovered_without_deleting_evidence(tmp_path):
    store = Store(tmp_path)
    broken = {"upcoming": [{"video": {"id": "invalid"}}]}
    store.set("queue", broken)
    assert store.load_queue().upcoming == []
    assert store.load_warning
    assert store.get("queue-recovery") == broken
    store.close()


def test_history_is_bounded_and_updates_existing_video(tmp_path):
    store = Store(tmp_path)
    for n in range(520):
        store.record(video(n), n)
    assert len(store.history(1000)) == 500
    store.record(video(519), 5)
    assert len(store.history(1000)) == 500
    assert store.history(1) == [video(519)]
    store.close()


def test_atomic_private_write_replaces_content_and_permissions(tmp_path):
    path = tmp_path / "private/session"
    atomic_private_write(path, b"first")
    atomic_private_write(path, b"second")
    assert path.read_bytes() == b"second"
    assert path.stat().st_mode & 0o777 == 0o600
    assert list(path.parent.glob(".pending-*")) == []


def test_nonfinite_positions_cannot_poison_saved_state():
    item = QueueItem(video()).to_dict()
    item["position"] = float("inf")
    assert QueueItem.from_dict(item).position == 0
    assert duration_label(float("nan")) == ""
    assert duration_label(3661) == "1:01:01"
