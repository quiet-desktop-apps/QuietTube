"""Opt-in public search through the real GTK interface; no browser cookies."""
import json
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quiettube.ui import QuietTubeApp
from gi.repository import GLib
from PIL import ImageGrab


def main():
    with tempfile.TemporaryDirectory(prefix="quiettube-public-ui-") as directory:
        app = QuietTubeApp(Path(directory))
        started = time.monotonic()
        result = {"passed": False}
        loaded_at = None

        def search():
            app.window.search_entry.set_text("Blender Foundation open movies")
            app.window.search()
            return False

        def finish_when_ready():
            nonlocal loaded_at
            window = app.window
            if window.videos and not window.busy:
                if loaded_at is None:
                    loaded_at = time.monotonic()
                    for video in window.videos[:3]:
                        window.enqueue(video)
                if time.monotonic() - loaded_at > 4:
                    target = Path("test-output/quiettube-live-search.png")
                    target.parent.mkdir(exist_ok=True)
                    ImageGrab.grab().save(target)
                    result.update(passed=True, videos=len(window.videos), queued=len(window.controller.queue.upcoming),
                                  thumbnails=len(window.thumbnails.cache), screenshot=str(target))
                    window.close()
                    return False
            if time.monotonic() - started > 95:
                result["error"] = window.status.get_text()
                window.close()
                return False
            return True

        GLib.timeout_add(300, search)
        GLib.timeout_add(200, finish_when_ready)
        app.run([sys.argv[0]])
        print(json.dumps(result))
        return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
