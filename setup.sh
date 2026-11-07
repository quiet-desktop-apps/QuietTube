#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"
missing=0
for executable in python3 mpv node; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    echo "Missing dependency: $executable" >&2
    missing=1
  fi
done
if ! python3 -c 'import gi; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk' 2>/dev/null; then
  echo 'Missing Python GTK4 bindings.' >&2
  missing=1
fi
if [[ "$missing" == 1 ]]; then
  echo 'Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip python3-gi gir1.2-gtk-4.0 mpv nodejs' >&2
  echo 'Use Node.js 20 or newer for current YouTube extraction.' >&2
  exit 1
fi
if (( $(node -p 'Number(process.versions.node.split(".")[0])') < 20 )); then
  echo 'Node.js 20 or newer is required.' >&2
  exit 1
fi
if [[ ! -x .venv/bin/python ]]; then
  if ! python3 -m venv --system-site-packages .venv; then
    # Ubuntu may have pip available separately but not ensurepip/python3-venv.
    python3 -m venv --without-pip --system-site-packages .venv
  fi
fi
if .venv/bin/python -m pip --version >/dev/null 2>&1; then
  .venv/bin/python -m pip install -r requirements.txt
else
  python3 -m pip --python .venv/bin/python install -r requirements.txt
fi
.venv/bin/python -c 'import gi, yt_dlp.version; gi.require_version("Gtk", "4.0"); from gi.repository import Gtk; print("GTK4 ready; yt-dlp", yt_dlp.version.__version__)'
echo 'QuietTube is ready. Start it with ./run.sh'
