# QuietTube memory evidence

Figures use **MiB**, not decimal MB. RSS is resident process memory; totals can
count shared pages twice. PSS apportions shared pages. There is no controlled
Chromium-versus-QuietTube comparison yet, and no percentage saving is claimed.

## Recorded development checks — 7 November 2026

| Workload | Result | Included / excluded |
|---|---:|---|
| 200 replacements of a 30-card feed with decoded synthetic thumbnails | ~199–203 MiB stable UI RSS after warm-up | GTK UI; no active player/extractor |
| Retained numeric regression artifact | 203.1 → 203.2 MiB; +0.1 MiB | Same 200-refresh workload |
| Public 720p video, headless, sampled around 5 seconds | 252.8 MiB mpv RSS | Player only; excludes GTK/extractor/GPU/display buffers |
| Separate rendered public playback sample | 265.1 MiB mpv RSS | Player only; different run |

Do not add the separate UI and player figures and present the sum as a measured
application total. Codec, resolution, display backend, decoder, buffer state and
worker lifetime affect memory. The current software-decoding preference can also
increase CPU use. Component buffer limits are not a total RSS ceiling.

An early feed replacement test found a real reference cycle: callback closures
retained their popovers, and UI RSS grew from about 240 to 475 MiB. Weak references
removed that growth; the regression now fails above 35 MiB growth after warm-up.
That short stress test does not prove multi-hour stability.

## Reproduce

```bash
./setup.sh
.venv/bin/python -m pip install -r requirements-dev.txt
GDK_BACKEND=x11 GSK_RENDERER=cairo xvfb-run -a \
  .venv/bin/python scripts/memory_check.py
```

The test writes sanitized numerical output to `test-output/memory-check.json` and
is part of `./test.sh`. The initial retained report is included under
[`benchmarks/feed-memory-2026-11-07.json`](benchmarks/feed-memory-2026-11-07.json).
Public playback checks in the [verification record](verification.md) are opt-in and
separate from deterministic tests. They do not read a browser's real session.

For a fair browser comparison, sample the entire QuietTube tree (UI, extraction
worker and mpv) against all browser processes for the same video, codec, resolution,
playback position and elapsed time. Include GPU caveats and distinguish startup
peaks from steady state. The organization provides a
[process-tree sampler](https://github.com/quiet-desktop-apps/.github/blob/master/scripts/measure-memory.py)
that outputs no command lines, titles, cookies or URLs.
