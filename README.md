<div align="center">
<img src="quiettube/icons/ch.aboimpinto.QuietTube.svg" width="88" alt="QuietTube icon">

# QuietTube

**Your videos. A little more breathing room.**

A native Linux YouTube companion with a persistent playback queue and mpv.
Part of [Quiet](https://github.com/quiet-desktop-apps) · [MIT](LICENSE)
</div>

![QuietTube native desktop showing the offline sample feed and queue](docs/images/quiettube-desktop.png)

*Real application screenshot with an offline sample feed. Playback/account access
are disabled in demo mode; the screenshot does not expose a personal feed.*

## Why QuietTube?

Watching a queue of videos should not require keeping a browser session open.
QuietTube uses Python and GTK4 for browsing, short-lived yt-dlp workers for
extraction, SQLite for your queue/history, and one mpv player for video.
There is **no Chromium, Electron or embedded webview**.

Memory stays explicit: one page of at most 30 videos, a bounded thumbnail cache,
disposable extraction workers, and player buffers capped at 64 MiB forward / 8 MiB
backward. These are component limits, not a total memory cap.

A repeated-feed regression stabilized around **199–203 MiB UI RSS** after warm-up
across 200 replacements. A separate public 720p playback check measured
**253–265 MiB mpv RSS**, excluding the UI and extractor. These were different
workloads and must not be added into a claimed measured total. **We do not yet have
a controlled Chromium comparison for QuietTube.** See [memory evidence](docs/memory.md).

## What it does

- Browse Home, Subscriptions, Watch Later and Liked videos with your connected
  session; search public videos, open links and browse playlists.
- Keep an editable queue: play now, add next, insert, reorder and remove.
- Save playback position locally; resume, seek, reload a stalled stream and
  select a resolution ceiling (720p by default).
- Show publication ages and hide locally completed videos; newest-first ordering
  applies within each loaded page.
- Like a video through an explicit account action, confirmed before showing success.
- Use native GTK controls and a separate mpv video window. Playback works with the
  browser closed after browser-assisted account connection.

## Install from source on Linux

Requires Python **3.11+**, GTK4 **4.8+**/PyGObject, mpv and Node.js **20+** for current
YouTube extraction. On Ubuntu/Debian:

```bash
sudo apt install git python3 python3-venv python3-pip python3-gi gir1.2-gtk-4.0 mpv nodejs
# Check node --version is 20 or newer.
git clone https://github.com/quiet-desktop-apps/QuietTube.git
cd QuietTube
./setup.sh
./run.sh --demo                 # Offline sample interface
./run.sh
.venv/bin/python scripts/install_desktop.py
```

The installer adds a user-local Applications entry linked to this checkout. Keep
the checkout in place. No signed binary packages or automatic updates are provided
yet. Update a clean checkout with `git pull --ff-only`, run `./setup.sh`, then
restart. See the [full user guide](docs/usage.md) for controls and troubleshooting.

## Account connection and limits

**Connect YouTube** opens the real sign-in page in your regular browser. QuietTube
then imports your selected browser session locally after you request it, keeping
only YouTube cookies. You can close the browser afterwards. This is browser-assisted
login, not Google OAuth or an embedded login form.

Session cookies are powerful credentials. They are saved unencrypted with private
file permissions outside the repository. Never upload them to an issue. Disconnect
removes the saved session; your local queue/history remain. There is no Quiet-hosted
service. See [architecture and privacy](docs/architecture.md).

QuietTube is **unofficial**, not affiliated with or endorsed by YouTube or Google.
Website/extractor changes and account restrictions can interrupt it. Some restricted,
paid, DRM-protected or bot-challenged videos may not play. Local queue and watch
history are not synchronized back to YouTube. Software decoding is currently the
compatibility default and may use more CPU at high resolutions.

## Architecture and Agentic Engineering

[Architecture](docs/architecture.md) · [Engineering process](docs/agentic-engineering.md)
· [Decisions](docs/decisions/0001-native-clients.md) · [Verification](docs/verification.md)

Humans own product intent, high-level requirements and important technical
decisions. Coding agents implement, test and document within that direction.
The human maintainer owns acceptance and merge authority; required PR checks
protect `master`.

```bash
# Test dependencies; setup.sh must have completed first.
sudo apt install xvfb xauth ffmpeg python3-pil
.venv/bin/python -m pip install -r requirements-dev.txt
./test.sh
```

Tests use synthetic cookies, temporary stores, local generated videos and a virtual
display. Public/live-account checks are separately labelled; opening a feed does
not authorize tests to mutate ratings. [Contributing](CONTRIBUTING.md) · [Security](SECURITY.md)

Original QuietTube code and bundled original assets are [MIT licensed](LICENSE).
Dependencies retain their own licenses: [third-party notices](THIRD_PARTY_NOTICES.md).
Maintained by [Paulo Aboim Pinto](https://github.com/aboimpinto).
