# QuietTube

A native Linux app for browsing your YouTube feeds and watching an editable queue
in mpv. The interface uses Python and GTK4. No browser engine runs inside the app.

## Start

From the repository root:

```bash
./setup.sh    # first run, or reinstall the pinned extractor
./run.sh
```

After setup, `./run.sh` starts the app. `./run.sh --demo` opens an offline preview with clearly labelled sample
data and temporary storage; account access and playback are disabled in preview.

### Applications menu and dock icon

After installing the launcher below, open
**QuietTube** from the Applications menu, then right-click its dock icon and choose
**Pin to Dash** / **Add to Favorites**. Reopen an already running app once if it
still displays the generic gear icon. Your session and queue remain saved.

To install again after moving this checkout, or for a different user:

```bash
.venv/bin/python scripts/install_desktop.py
```

The installer writes only to the user's XDG data directory: a desktop entry under
`applications/` and a scalable SVG under `icons/hicolor/scalable/apps/`, with a
direct copy under `icons/` so the launcher also works with a stale theme cache. It does
not change your pinned apps. The desktop entry points to this checkout's `run.sh`;
the launcher filename, icon name, Wayland application ID and X11 window class use
`ch.aboimpinto.QuietTube` so the dock groups its windows correctly.

System dependencies: Python 3.11+, GTK 4.8+/PyGObject, mpv, and Node.js 20+.
On Ubuntu/Debian:

```bash
sudo apt install python3 python3-venv python3-pip python3-gi gir1.2-gtk-4.0 mpv nodejs
```

No system packages are installed automatically. Python dependencies are isolated
in `.venv`, with system-site-packages enabled for the distribution's GTK bindings.

## Connect your YouTube account

These first steps describe browser-session mode, which needs no Google Cloud
setup. Evaluate it at your own pace; there is no timed evaluation or forced
migration. Optional personal OAuth is available experimentally under **Connect
YouTube → Personal OAuth · experimental**. Its panel has the Google links, exact
fields and JSON import; see the [setup guide](personal-oauth-setup.md) and
[account trade-offs](account-direction.md). Live OAuth reliability is not yet verified.

1. Click **Connect YouTube**, then **Open YouTube sign-in**.
2. Sign in on the real YouTube website in your normal browser. Choose the desired
   YouTube channel/account there if you have more than one.
3. In QuietTube choose that browser. For multiple browser profiles, specify its
   profile name or full profile path; leaving this blank uses yt-dlp's default
   selection, which may not be the profile you intended.
   Common Snap/Flatpak profile roots are suggested when the normal profile
   directory has no cookie database, including when an empty folder remains from
   another installation. Linux keyring support is included in the Python dependencies.
4. Click **Connect browser session**. QuietTube checks the subscription feed before
   saving the session. Once connected, close the browser and watch in QuietTube.

This is browser-assisted login, not an embedded Google password form or Google
Data API OAuth. The official Data API does not expose the personalised homepage
or Watch Later, and yt-dlp no longer supports YouTube OAuth login. The account's
website session supplies Home, Subscriptions, Watch Later and Liked videos.

If cookie decryption fails, close the browser and retry, check the profile, or use
**Import a YouTube cookies.txt file instead**. This accepts the Netscape cookie
format. Export only youtube.com cookies; follow the upstream
[YouTube cookie instructions](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies).
Keep cookie files private: they grant access to your session. Do not send them in
chat or put them in the repository.

Only YouTube cookies are retained. The selected browser's cookie store is read
locally during connection; cookies from other websites are discarded. The retained
session is stored as a plaintext file with mode `0600` inside a `0700` directory
owned by your Linux user, outside the repository. It is sent only as needed to
YouTube/Google's media infrastructure, never to an app backend. Temporary copies
are removed after requests and playback end. **Remove saved browser session** stops playback and
removes the saved session and feed thumbnails; the local queue/history remain.

YouTube may expire the session or restrict unofficial clients. Reconnect through
the same dialog. Upstream warns that using accounts with yt-dlp can lead to account
restrictions; keep requests modest. QuietTube fetches one bounded page at a time
and does not poll feeds in the background. Account feeds depend on YouTube and
may occasionally need an extractor update. No personal account is bundled.

### Personal OAuth mode

Import the Desktop JSON or paste its Client ID and Client secret, save to the
keyring, then **Sign in with Google**. Saving configuration alone does not switch
modes. Successful sign-in selects OAuth and the header identifies it. Home and
Subscriptions both show a bounded newest-first snapshot of subscription uploads;
Watch Later is unavailable, and Shorts may appear. Liked videos and explicit Likes
use the API. Search also consumes your project's API quota in this mode.

Account data uses refreshable authorization independent of copied browser cookies.
The player still uses public yt-dlp/mpv access, without OAuth tokens or browser
cookies. Restricted videos may fail. A failed request preserves the queue; expired
authorization asks for Google sign-in rather than silently using browser cookies.
Use **Connect browser session** to switch back deliberately. Switching stops the
player but preserves its queue and position for manual resume.

**Remove personal OAuth from keyring** deletes the local client and tokens; it does
not revoke Google's grant. Use the dialog's Google permissions link to do that.
Removing browser cookies and removing OAuth are separate actions. Neither deletes
the local queue/history. See the setup guide for keyring and expiry troubleshooting.

## Watch your way

The feed descriptions below refer to browser-session mode unless stated otherwise.

- **Home:** your signed-in YouTube home recommendations, subject to extraction
  support; not guaranteed to be identical to the browser's current page.
- **Subscriptions:** latest videos surfaced by your account's subscriptions feed.
- **Newest first:** Home and Subscriptions sort each loaded page by publication
  date by default; unknown dates appear last. Select **YouTube order** to restore
  the returned order. This does not search all pages for the newest upload.
- **Hide watched here:** enabled by default on Home and Subscriptions. Videos
  that reached the end in QuietTube disappear from the wall and remain hidden
  after refresh. Turn it off to show them with a **Watched** badge. Both choices
  are remembered. Completion uses the existing local history (latest 500 videos),
  including previously recorded completions; partial playback and errors do not
  count as completed. Replaying a completed video keeps its watched flag.
- **Watch Later / Liked videos:** browse your existing account lists.
- **Search:** search YouTube, open an individual link, or paste a playlist URL.
- **Paste link:** read a YouTube video URL from your clipboard. Entering a video
  URL in the search box and pressing Enter has the same behaviour. If the player
  and queue are empty, it starts immediately; otherwise choose **Play now** or
  **Add to queue**. Cancel leaves playback and the queue untouched. Playlist links
  still open a browsable list rather than starting an entire playlist.
- **▶ on the preview:** play immediately when the queue is empty, otherwise show
  the same Play/Queue choice. Play now keeps an interrupted video and its position
  at the front of the upcoming queue.
- **+ on the preview (Add to queue):** append to the end without loading video data.
- **Copy icon on the preview:** copy that video's YouTube URL to the clipboard.
- **Thumbs up on the preview:** Like the video on your connected YouTube account.
  It changes colour only after YouTube confirms the rating; an already-liked
  video stays liked. This version adds Likes and does not toggle them off.
- **⋮ → Play next:** insert immediately after the current video.
- **⋮ → Insert before selected:** select an item in the queue first, then insert
  another video at that position.
- Select a queue row and use **↑ / ↓**, **Move to**, or **Remove** to edit it.
- **Play queue:** starts the first item or resumes the current one.
- **Next:** skips the current video. Playback errors preserve the current item;
  they never silently skip the queue.
- **Find similar videos:** searches by the video's title. These are topic search
  results, not the personalised YouTube “Up next” sidebar.

YouTube history sharing is optional and separate from watched filtering, which
remains local to this computer. Local history, searches, direct links and playlists
remain available for replay and keep their original ordering. A fully watched
page keeps **Next page** available when YouTube supplies more results.

Cards stay 400 logical pixels wide, close to their size in the initial window.
Wider windows add columns instead of enlarging previews, including on ultrawide
monitors. Previews keep a 16:9 shape. Play, Add to queue, Copy link, Like and More
actions form a translucent vertical stack at the top right of each preview, with
tooltips and accessible labels. Titles and channel information remain below.
The metadata row shows the duration and publication age, such as **1h ago**,
**6d ago** or **1y ago**. Long channel names truncate before the age does. Feed
dates can be approximate because YouTube supplies relative ages; no extra
per-video requests are made. Missing dates remain blank, and date-only uploads
from today say **Today** rather than inventing an upload hour. Ages update when
the cards are rendered again, for example after a feed refresh.

Video opens in a separate lightweight mpv window. Use Space to pause, F for
fullscreen, J to cycle available subtitles, and the usual mpv seek controls.
QuietTube also provides pause/resume, ±10-second seeking, volume, stop and next.
Playback prefers HLS video and audio, with direct streams used when HLS is not
available. This avoids a reproduced YouTube HTTP 403 failure on advertised direct
streams. Both paths respect the selected resolution limit and player buffer bounds.
Video decoding uses software to avoid the automatic GPU decoding path implicated
in corrupted frames. This can use more CPU, particularly at high resolutions;
720p remains the default. The video renderer can still use the GPU.
On failure, the status bar identifies recognised stream, connection or account
errors without exposing media URLs. Press **Play** to retry the preserved video
and position; errors do not consume the remaining queue.
If audio continues but the picture freezes, use **Reload video** (the circular
arrow beside the quality selector). It opens fresh streams at the current saved
position without moving or duplicating queue entries. Choosing **Play now** for
the current video also retains its position. Pause saves the position immediately.
The resolution selector is a maximum and applies to the next playback start;
720p is the default. Some restricted, DRM, paid, regional or bot-challenged content
may not play. The queue is local and does not modify YouTube playlists. Optional
history sharing reports the video and actual playback position separately.

Likes are an explicit account action, separate from the local queue. A dedicated
worker handles one Like at a time, so browsing or searching does not cancel it.
In browser-session mode, the worker reads the rating, sends the Like command only
if needed, then reads the rating again to verify it. In OAuth mode, success means
the Data API accepted the rating request; there is no additional read-back call.
Expired authorization prompts you to sign in again; an unconfirmed or timed-out
request is not presented as success.
Check Liked videos before retrying an ambiguous network failure. No account
ratings are changed by the automated tests or by opening a feed.

## Connected OAuth but mpv closes immediately

The **Personal OAuth · connected** badge describes access to account feeds, not
permission to stream video through mpv. If YouTube asks the extractor to confirm
that it is not a bot, the player cannot start even when refreshing the dashboard
works. Repeating Google OAuth sign-in does not satisfy that separate check.

A playback error now exposes **Playback help** beside the status message. It
explains the connection boundary and offers an explicit retry at the saved
position, Copy video link, or **Open this video on YouTube** in your usual browser.
Opening the help itself makes no network requests and does not launch a browser.
The browser link includes the saved playback time. Watching there does not advance
QuietTube's queue or synchronize its resume position; the queue remains intact.

There is no automatic browser-cookie fallback or retry loop. Waiting before a
manual retry may help a temporary restriction, but QuietTube cannot guarantee it.
You can explicitly add the separate playback connection below without changing
your account feed mode. Google sign-in for account feeds is available near the top
of the account dialog when OAuth is selected.

### Connect playback while keeping personal OAuth

1. Click **Connect playback** in the header, or **Connect / reconnect playback**
   inside Playback help.
2. Use **Open YouTube sign-in** if necessary, then select the browser/profile
   where you are signed in. You may instead import a Netscape YouTube cookies file.
3. Click **Save browser session for playback**. Only YouTube cookies are retained,
   in `youtube-playback-session.txt` under the private application data directory
   (normally `~/.local/share/quiettube/`). The file is `0600`, its directory `0700`.
4. Close the browser and dialog, then press **Play**. The current video retries at
   its saved position. The dashboard and Likes continue using OAuth.

**Playback session · saved** confirms a local session was imported, not that
YouTube will accept it. The actual playback attempt establishes that. The first
live authenticated check on 9 November restored playback of the queued video;
long-term reliability is not established. Reconnect here if the session expires.
**Remove playback session** deletes only this separate session and stops its
active player copy; it retains OAuth, the account-feed session, queue and history.

This is opt-in. An older saved browser-account session is not silently reused.
In browser-session account mode, playback still uses the original account session;
the separate playback session is used only when personal OAuth is selected.
Importing does not load feeds or claim a video is playable. Browser cookies are
read on import, not continuously; no embedded browser or background browser is added.

The upstream [yt-dlp account documentation](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#logging-in-with-oauth)
states that OAuth login is not supported for YouTube extraction. A Data API login
therefore cannot be treated as a replacement for website playback authorization.

## Share watch history and resume on another device

Open **Connect playback** (or **Playback session · saved**) and enable
**Share watch history and playback position with YouTube**. Sharing is off by
default for new installations. The switch persists locally and can be turned off
without removing the playback session, OAuth, queue or local history. Turning it
off stops future requests; it does not delete history already sent to YouTube.

Sharing uses the YouTube account/channel in the selected **website session**.
OAuth does not write watch history. Keep YouTube watch history enabled and use
that same account/channel on the other device. Enabling sharing with a current
saved video immediately requests its saved position; it does not upload the
whole local viewing history.

During playback, a separate bounded worker reports the current position at most
once every 30 seconds, plus a final changed position on pause, stop, reload, skip
or EOF. It waits for observed playback before automatic reporting. It does not
mark queued/opened videos fully watched or invent watch time for skipped ranges.
Paused or idle playback creates no periodic history traffic. The request uses
`st=et=cmt=current position`, following YouTube.js's position-reporting approach.
Current live streams are unsupported; ordinary recorded videos can be reported.

The Now playing area distinguishes **Sharing watch history**, **History update
sent**, and failure. Sent means the requests succeeded, not a server read-back
for every update. On failure, playback and local resume continue. No infinite
retry loop or replay of stale positions after reopening is used. Up to five
pending video updates are retained in memory, coalesced to the latest position
per video. Requests have a 30-second worker timeout, an 8-second socket timeout,
and a 4 MiB page-response bound. Shutdown gives the in-flight update up to three
seconds before cancelling; a final update can be lost on immediate exit or crash.

For a handoff, **pause and wait for History update sent**, then open the same
video from YouTube History on your other device. YouTube may take time to refresh
its progress. A live trial retained both a progress bar and the reported resume
point, but every device/client is not verified. Almost-completed videos may
restart; YouTube describes resume as usual behavior, not a guarantee. See
[YouTube progress-bar help](https://support.google.com/youtube/answer/7174115?hl=en).

This is **one-way sharing from QuietTube to YouTube**. Watching farther on another
device does not update QuietTube's local queue position. Avoid simultaneously
playing the same video in both, because later reports may replace the resume point.
No browser engine, OAuth token in mpv, extra API scope or API quota is involved.
Unofficial website requests remain subject to cookie expiry and YouTube changes.

## Playback diagnostics

Playback writes private structured logs to
`~/.local/share/quiettube/logs/playback.jsonl` (under `$XDG_DATA_HOME/quiettube/logs`
when that variable is set). The current file and two rotated copies are capped
at 1 MiB each. Directory permissions are `0700`, files `0600`.

Logs record playback starts and requested positions, pause/resume duration,
seeks, completion and closure, plus ten-second snapshots of playback/audio time,
A/V sync, cache state, dropped frames, codec, decoder and renderer. Recognised
warnings become fixed categories. Raw messages, video titles/IDs, cookies and
media URLs are never written. Logging failures do not interrupt playback.

These diagnostics help distinguish a stalled stream, decoder or renderer; they
cannot reconstruct incidents from before logging was installed or guarantee a
diagnosis from every freeze. After an incident, retain all three log files before
they rotate away. Restart QuietTube after updating to enable the new logger.

## Memory and storage

- One mpv process at a time; stopped when playback ends, fails, or the app closes.
- Forward demuxer buffer capped at 64 MiB and backward buffer at 8 MiB. Decoder,
  GPU, UI and extractor memory are additional; these are not a total RSS cap.
- Feed pages contain at most 30 videos; up to 10 pages per query, replacing the
  displayed page rather than growing an infinite scroll.
- Thumbnail cache: at most 64 compressed images, each at most 192 KiB, with two
  concurrent requests. Only displayed cards hold decoded textures.
- Extraction runs in a separate process that exits after a request; cancellation
  terminates that worker and its children. Requests time out after 90 seconds.
- Queue: up to 1,000 upcoming items, storing metadata only. History: 500 videos.
- Queue edits save immediately to SQLite. Playback position checkpoints every
  five seconds and on normal close. Resume is manual after restart.
- Default data: `${XDG_DATA_HOME:-~/.local/share}/quiettube/`. Override with
  `./run.sh --data-dir /some/private/directory` for isolated testing.
- One app instance per data directory prevents competing queue writers.

See [verification](verification.md) for measured results and remaining live
account checks. Lower memory use than a browser is a design objective; the exact
saving depends on video format, resolution, GPU and the browser baseline.

## Tests

```bash
python3 -m pip --python .venv/bin/python install -r requirements-dev.txt
sudo apt install xvfb ffmpeg python3-pil  # if not already present
./test.sh
```

Tests use temporary databases and synthetic cookies; they never read your browser
profile. They cover queue ordering/persistence, recovery, session filtering,
cancelled/timed-out workers, stale player events, actual mpv playback through IPC,
and native GTK controls in a virtual display. Public YouTube smoke tests are
separate from deterministic tests. Live account verification requires you to sign
in; it is not represented as an automated test pass.

## Development

`ratings.py` handles authenticated Like commands and confirmation, using the
web-client command structure described in
[YouTube.js LikeEndpoint](https://github.com/LuanRT/YouTube.js/blob/main/src/parser/classes/endpoints/LikeEndpoint.ts).
This unofficial endpoint can change upstream, just like feed extraction.

`models.py` and `storage.py` own queue data; `controller.py` owns playback state
transitions. `player.py` emits typed `PlayerEvent` messages, and `tasks.py` emits
typed `TaskResult` replies. GTK delivers those on its main loop. `worker.py`
handles extraction and session import in a disposable process. `thumbnails.py`
owns the bounded thumbnail cache; `ui.py` is the native interface.

To update yt-dlp, change the exact pin in `requirements.txt` and `pyproject.toml`,
run `./setup.sh`, then repeat tests and public playback checks. No silent
self-updater or custom remote JavaScript downloads are enabled.
