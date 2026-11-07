"""Offline GTK memory soak: repeated feed replacement with decoded thumbnails."""
import gc
from io import BytesIO
import json
import os
from pathlib import Path
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quiettube.models import Video
from quiettube.ui import QuietTubeApp
from gi.repository import GLib
from PIL import Image


def rss():
    return int(next(line.split()[1] for line in Path("/proc/self/status").read_text().splitlines()
                    if line.startswith("VmRSS:"))) / 1024


def drain():
    while GLib.MainContext.default().pending():
        GLib.MainContext.default().iteration(False)


def main():
    with tempfile.TemporaryDirectory(prefix="quiettube-memory-") as directory:
        app = QuietTubeApp(Path(directory), demo=True)
        app.register(None)
        app.activate()
        window = app.window
        window.demo = False
        videos = [Video(f"{n:011d}", f"Memory test video {n}", "Synthetic fixture", 120) for n in range(30)]
        for n, video in enumerate(videos):
            image = Image.new("RGB", (320, 180), (35 + n * 3, 80 + n * 2, 110))
            stream = BytesIO()
            image.save(stream, format="JPEG")
            window.thumbnails.cache[video.id] = stream.getvalue()
        samples = []
        try:
            for iteration in range(200):
                window.show_videos(videos if iteration % 2 else list(reversed(videos)))
                drain()
                if iteration % 10 == 0:
                    gc.collect()
                    drain()
                    samples.append({"refreshes": iteration + 1, "rss_mib": round(rss(), 1)})
                time.sleep(0.005)
            gc.collect()
            final = rss()
            baseline = samples[3]["rss_mib"]  # after GTK/allocator warm-up
            report = {"refreshes": 200, "cards_per_page": 30, "warm_rss_mib": baseline,
                      "final_rss_mib": round(final, 1), "growth_after_warmup_mib": round(final - baseline, 1),
                      "thumbnail_cache_entries": len(window.thumbnails.cache), "samples": samples}
            target = Path("test-output/memory-check.json")
            target.parent.mkdir(exist_ok=True)
            target.write_text(json.dumps(report, indent=2) + "\n")
            print(json.dumps(report), flush=True)
            return 0 if final - baseline < 35 else 1
        finally:
            window.close()
            drain()
            app.quit()


if __name__ == "__main__":
    raise SystemExit(main())
