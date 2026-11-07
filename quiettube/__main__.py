import argparse
import fcntl
from pathlib import Path
import sys
import tempfile

from .storage import data_directory, private_directory


def main():
    parser = argparse.ArgumentParser(description="QuietTube — native YouTube feeds and a persistent playback queue")
    parser.add_argument("--demo", action="store_true", help="Offline preview with temporary data; no account access")
    parser.add_argument("--data-dir", type=Path, help="Override the local data directory")
    parser.add_argument("--quit-after", type=int, default=0, help=argparse.SUPPRESS)
    args = parser.parse_args()
    temporary = tempfile.TemporaryDirectory(prefix="quiettube-demo-") if args.demo and not args.data_dir else None
    directory = private_directory(args.data_dir or (Path(temporary.name) if temporary else data_directory()))
    lock = open(directory / "instance.lock", "a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print("QuietTube is already running for this data directory.", file=sys.stderr)
        return 1
    try:
        from .ui import QuietTubeApp
        from gi.repository import GLib
        GLib.set_prgname("ch.aboimpinto.QuietTube")
        return QuietTubeApp(directory, args.demo, args.quit_after).run([sys.argv[0]])
    except (ImportError, ValueError) as error:
        print(f"QuietTube could not start: {error}\nRun ./setup.sh to check dependencies.", file=sys.stderr)
        return 1
    finally:
        lock.close()
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
