#!/usr/bin/env bash
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$project_dir"
if ! .venv/bin/python -m pytest --version >/dev/null 2>&1; then
  echo 'Install test tools: python3 -m pip --python .venv/bin/python install -r requirements-dev.txt' >&2
  exit 1
fi
export GDK_BACKEND=x11
export GSK_RENDERER=cairo
export QUIETTUBE_SCREENSHOT=test-output/quiettube-preview.png
if command -v xvfb-run >/dev/null 2>&1; then
  exec xvfb-run -a -s '-screen 0 5120x1440x24' .venv/bin/python -m pytest tests -q \
    --cov=quiettube --cov-report=term-missing --cov-report=json:test-output/coverage.json "$@"
fi
echo 'xvfb-run is missing; GTK tests require a display. Ubuntu/Debian: sudo apt install xvfb' >&2
exec .venv/bin/python -m pytest tests -q "$@"
