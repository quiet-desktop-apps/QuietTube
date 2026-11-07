"""Opt-in real YouTube search + playback smoke test. Never loads account cookies."""
import json
import argparse
from pathlib import Path
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from quiettube.player import MpvPlayer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--render", action="store_true", help="Render video in X11 and capture it; audio remains muted")
    args = parser.parse_args()
    result = subprocess.run([sys.executable, "-m", "quiettube.worker"],
        input=json.dumps({"kind": "search", "query": "Blender Foundation Big Buck Bunny"}),
        capture_output=True, text=True, timeout=100)
    data = json.loads(result.stdout)
    if not data.get("ok") or not data.get("videos"):
        print(json.dumps({"search": "failed", "error": data.get("error")}))
        return 1
    print(json.dumps({"search": "passed", "videos": len(data["videos"])}), flush=True)
    events = []
    player = MpvPlayer(events.append)
    began = time.monotonic()
    try:
        player.start("https://www.youtube.com/watch?v=aqz-KE-bpKQ", height=720,
                     extra_args=["--vo=x11" if args.render else "--vo=null", "--ao=null",
                                 "--force-window=yes" if args.render else "--force-window=no"])
        while time.monotonic() - began < 90:
            errors = [event for event in events if event.kind == "error"]
            if errors:
                print(json.dumps({"playback": "failed", "error": errors[-1].value}))
                return 1
            positions = [float(event.value) for event in events if event.kind == "time-pos"]
            if positions and max(positions) >= 5:
                if args.render:
                    from PIL import ImageGrab
                    target = Path("test-output/quiettube-live-playback.png")
                    target.parent.mkdir(exist_ok=True)
                    ImageGrab.grab().save(target)
                rss = next(line.split()[1] for line in Path(f"/proc/{player.process.pid}/status").read_text().splitlines()
                           if line.startswith("VmRSS:"))
                print(json.dumps({"playback": "passed", "seconds_played": round(max(positions), 1),
                                  "mpv_rss_mib": round(int(rss) / 1024, 1), "video_output": "x11" if args.render else "null",
                                  "elapsed_seconds": round(time.monotonic() - began, 1)}))
                return 0
            time.sleep(0.1)
        print(json.dumps({"playback": "timeout"}))
        return 1
    finally:
        player.stop()


if __name__ == "__main__":
    raise SystemExit(main())
