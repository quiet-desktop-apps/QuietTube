# QuietTube verification

Verified on 7 November 2026 on this Linux workstation. The historical playback checks below predate the independent public repository.
No binary packages for other distributions were produced by these checks.


## Playback verification challenge — 9 November 2026

The existing redacted logs showed successful playback earlier, then repeated
`account` warnings followed by error/closure after the application was left open
and after a restart. A separate read-only live diagnostic reproduced YouTube's
“not a bot” challenge for a public sample and the current queued video, without
cookies or OAuth tokens. It printed only result categories, read queue metadata
through a read-only SQLite connection, and did not alter queue/history or ratings.
The installed yt-dlp 2026.10.26 matched the latest stable upstream release checked.

The confirmed defect was the instruction to reconnect the account: the generic
classifier grouped verification challenges with account-session requirements,
even in OAuth mode where a new Data API login cannot authorize mpv. Classification
now distinguishes `verification`, carries the category in the typed player event,
and records the final category in the private log. Raw URLs/messages remain
excluded. Playback help exposes manual recovery options and explicitly opening
the video in a browser at the saved time. No browser session is silently imported
or used, no automatic retry is added, and Google sign-in is reachable at the top
of the account dialog.

These changes correct diagnosis and recovery guidance. They **do not establish
that cookie-free playback has recovered**: the live YouTube verification challenge
remains unresolved. Deterministic tests use a synthetic failing extractor with
real mpv, plus GTK/controller checks, and never use a real account session.

`./test.sh` passed all **200 tests** with **88% coverage**. A GTK screenshot
check also verified the playback-help dialog; its height was increased to keep
the recovery buttons visible without scrolling on the tested desktop.

## OAuth PR review corrections — 8 November 2026

Review found three reproducible defects: subscription sync queued the entire
account before observing quota/auth failures, malformed fresh cache records could
be repeatedly returned, and unsupported Watch Later kept the previous feed's
cards under its new heading while downgrading the connected status.

Nine new regression cases failed before the fixes and passed afterward. Upload-list
requests now run in batches of at most four and stop scheduling on error; the old
snapshot is retained. Cache records are validated before reuse and rebuilt when
invalid. Unsupported feeds show an empty explanatory state while preserving account
status and the playback queue. The complete local `./test.sh` run passed **194
tests**, no skips/failures, with **88% statement coverage**. The existing GTK/Python
deprecation warnings remain. No real account requests or ratings were performed.

## Personal Desktop OAuth experiment — 8 November 2026

`./test.sh`: **185 passed**, no failed or skipped tests, **88% overall statement
coverage**. After a timezone-only correction to synthetic token fixtures, the
28 account tests also passed separately. The existing GTK/Python deprecation
warnings remain; no warning suppression was added.

- Desktop JSON and manual inputs validate before replacing configuration. Invalid,
  oversized and non-Desktop inputs preserve previous authorization. Imported
  endpoints cannot redirect the token exchange.
- Real Google OAuthlib loopback callbacks exercise state validation and PKCE with
  synthetic authorization codes and intercepted HTTP token exchange. Incorrect
  state is rejected before exchange; no Google account or live endpoint is used.
- A real worker stores a synthetic client through Secret Service in an isolated
  D-Bus session and temporary password-protected GNOME keyring. Read/update/delete
  and per-library isolation pass; neither the client secret nor refresh token is
  present in plaintext files. This never opens the user's login keyring.
- Locked/unavailable keyrings fail without a file fallback. Tests cover refresh
  rotation, revoked authorization, transient renewal failure, malformed requests,
  sanitized errors and exclusion of client JSON from package data.
- Synthetic API tests cover feed ordering/deduplication/cache bounds, pagination,
  explicit Likes, unsupported Watch Later, quota errors, bounded responses and a
  single 401 renewal attempt. Failures do not overwrite an existing feed cache.
- GTK tests verify setup fields, clearing pasted values, explicit mode selection,
  cancellation/stale completion, preserved queues and no browser-cookie fallback.
  The controller passes no cookies to mpv in OAuth mode. Existing native playback,
  queue and 200-refresh memory regressions still pass.
- The setup panel was rendered and visually inspected under Xvfb, including its
  instructions and import/manual fields. Screenshots contain only offline demo
  data and are ignored under `test-output/oauth-setup-*.png`.

**Not verified:** real Google consent, account feeds/Like writes, renewal over days,
restricted playback, long-term memory in OAuth mode, or a realistic daily quota
budget. No real credentials were imported and no user ratings changed. Synthetic
success does not establish that OAuth improves reliability or resolves Google's
service-policy questions. Clean-runner CI is tracked on the implementation PR.

## Open-source publication preparation — 8 November 2026

Prepared for the independent `quiet-desktop-apps` repository: MIT licensing,
architecture and Agentic Engineering docs, scoped memory evidence, synthetic-data
screenshots, contributor/security guidance and PR-only CI configuration.
Local verification: all 134 tests passed with 89% overall statement coverage
after the compatibility regression below. The initial source snapshot had 133 tests.
The GTK/Python deprecation warnings remain recorded below. The screenshot was
captured from a fresh offline preview with no personal account. CI on a clean
GitHub runner is tracked on the publication PR, separately from these local results.

Clean-runner mpv compatibility fix (0.1.1): Ubuntu 24.04's mpv 0.37 rejected the
newer positional loadfile argument shape. Named `url`, `flags` and `options`
arguments work across both versions and preserve the resume position. Request
acknowledgements now report rejection explicitly instead of silently waiting.
A real mpv regression verifies rejection emits a safe error without leaking paths
or falsely completing a video. The existing real-player tests check resume,
seeking, rendered frames, consecutive queue playback and failure recovery.
The [mpv 0.37 IPC documentation](https://github.com/mpv-player/mpv/blob/v0.37.0/DOCS/man/ipc.rst)
and command definition were checked before changing the call.

Earlier dated records below describe development at that time; install paths and
version references in them are historical, not current release instructions.


## Automated tests

Command: `./test.sh` from `QuietTube/`.

- **133 passed**, no failed or skipped tests in the original development run.
- **89% overall statement coverage**; video/queue models 96%, storage 94%, playback
  controller 99%, thumbnail cache 95%, native UI 90%, Like adapter 99%.
- Queue insertion in the middle, moving to a position, removal, duplicate video
  identity, 3,000 random operations, the 1,000-item bound, saved positions, database
  reopen and corrupt-state recovery.
- EOF advances the queue; errors, stale events and closing the player do not.
  Real mpv integration loads a generated local clip, reports progress/completion,
  pauses/resumes/seeks, reports missing-file errors, and terminates cleanly.
- Synthetic session cookies test domain filtering, expiry, permissions, account
  verification failure preserving a previous session, and safe error messages.
- Real worker processes test cancellation, timeout, process reaping and removal
  of temporary session directories before cancellation returns.
- GTK tests exercise native queue controls, search routing, account-dialog errors,
  disconnect, stale-result handling, quality/volume persistence and card menus.
- Thumbnail cache tests exercise its size bound, oversized images and stale
  downloads. Snap/Flatpak profile-location tests use temporary directories.
- Tests never import the user's real browser cookies. Native UI tests use Xvfb.
- Preview layout checks verify the allocated 16:9 shape at two window widths and
  queue insertion through the vertical overlay controls. The updated layout was
  also visually inspected with 30 real public thumbnails. The 200-refresh memory
  regression remained stable at about 199 MiB after warm-up.
- Responsive-grid regression resizes the same 30-item feed through 1380, 1920,
  2560, 3440 and 5120-pixel window widths and back to 1380. Cards remain 400
  logical pixels wide (382-pixel previews inside the border and padding); the
  grid displays 2, 3, 4, 6 and 10 columns respectively. Returning to the initial
  window restores two columns. The 5120-pixel layout was also rendered and
  visually inspected in a matching virtual display. Desktop scaling affects how
  many logical pixels a physical monitor provides.

The distribution's PyGObject emits deprecation warnings about Python 3.14 asyncio
policy APIs and a GLib signal wrapper. Xvfb also reports that accelerated DRI3 is
unavailable. These are recorded environment warnings, not silently filtered test
failures; UI rendering and playback tests pass.

## Pause/resume diagnostics and preserved reopening position

The reported audio-only resume could not be reconstructed: the previous build
kept only transient warning categories, redirected mpv stderr, and had no saved
playback logs. A read-only inspection after the user's restart showed software
VP9 decoding, gpu-next rendering, a roughly 20-second cache, negligible A/V skew
and no dropped frames. That describes the recovered session, not the failure.

A separate confirmed code defect reset the position when Play now selected the
already-current video. It now restarts that item at its saved position without
inserting a duplicate. Pause immediately persists position. The new Reload video
control explicitly refreshes streams at the current position and retains queue
identity/order. No speculative stream or decoder changes were introduced.

Private JSONL diagnostics now record lifecycle events and bounded ten-second
snapshots using mpv's structured properties. Warning text is reduced to a fixed
category and never persisted. Only allowlisted scalar fields and codec/renderer
names reach disk; raw URLs, titles, IDs and credentials are excluded. Rotation
retains at most three 1 MiB files. This uses the documented
[mpv properties](https://mpv.io/manual/master/#properties) and existing IPC channel.

Tests verify log redaction/permissions/rotation, unavailable log destinations,
real mpv snapshot and pause/resume capture, nonzero-position reopening, the UI
reload action, and unchanged queue identity through current-video reopening.

A separate live diagnostic loaded the affected video in a muted, minimized
player on the desktop renderer, paused it for 180.8 seconds, then resumed for
10.7 seconds. Captured frames changed both immediately after resume and later;
they were visually inspected. Logged A/V sync was near zero, dropped-frame
counts were zero and the cache returned to roughly 20 seconds. Two warnings had
unknown categories; no fatal playback error occurred. This single check did not
reproduce the intermittent freeze and is not proof that the underlying cause is
fixed. It did not interrupt the user's player or alter saved queue/history.

## Watched wall and publication ordering

Home and Subscriptions now default to newest-first ordering within each loaded
page and hiding locally completed videos. Both controls persist. Raw page data
stays available so changing a control is immediate and adds no network requests.
All-hidden pages keep their pagination, and watched videos carry a badge when
shown. Other feeds preserve source ordering and remain replayable.

The existing bounded 500-video history supplies completion state. History upserts
now retain completion across replay checkpoints rather than overwriting it with
false. Existing completed records work without a database migration. Only valid
current-generation EOF events trigger immediate wall filtering; errors, closing
or partial viewing do not imply completion. No watch-history writes are sent to
YouTube.

Tests cover date/timezone ordering, unknown dates, completed flags surviving
database reopen and replay, refresh returning the same videos, control persistence,
all-hidden-page navigation, preserved playlist/search/history order, and valid
versus stale EOF/error handling. The native controls were rendered and visually
inspected. The full suite includes the existing repeated-feed memory regression.

## Corrupted playback frames

The user subsequently reported severe block corruption during playback. The old
default selected VP9 HLS and Vulkan hardware decoding on this workstation.
Software-decoded VP9 and H.264 samples rendered cleanly. A short repeat with
Vulkan also rendered cleanly, so the intermittent corruption was not reproduced
deterministically and a specific driver defect is not established.

As a compatibility fix, the default now explicitly sets `--hwdec=no`; HLS
selection, resolution ceilings and demuxer buffer limits stay unchanged. This
avoids automatic hardware decoding while still allowing GPU rendering. CPU use
can increase, especially above the default 720p. See mpv's
[hardware decoding documentation](https://mpv.io/manual/master/#options-hwdec).

A new deterministic integration test generates a VP9 HLS stream, serves it over
local HTTP, renders it through mpv and compares captured pixels with reference
colour bars at startup and after an exact seek. It also checks that hardware
decoding is disabled. This supplements the existing event/queue tests rather
than treating time-pos or file-loaded events as proof of visual correctness.

Separate live desktop checks of the affected video used the corrected default
decoder with a muted, minimized player. Captured frames at startup and after
forward/backward seeks were visually inspected. These checks preserve the user's
saved queue, history and position, and use temporary session copies. They cover
short playback samples, not a multi-hour stability benchmark.

## Playback failure after advancing the queue

The reported video reproduced HTTP 403 failures in real mpv with the original
direct-stream selector, both with a temporary copy of the saved session and
without authentication. Metadata extraction succeeded in both cases. A separate
public playback check still worked, isolating this from a general mpv or queue
failure. The installed yt-dlp version matched the latest stable release checked.

Selecting HLS video and audio made the previously failing video play. The player
now prefers a complete HLS video/audio pair, then combined HLS, and retains direct
stream fallbacks for videos without HLS. Every selection keeps the chosen height
ceiling. No buffer limits were increased and no new download cache was introduced.

Regression tests use yt-dlp's real format selector on synthetic format lists at
all five supported resolutions. They cover combined streams, absent HLS and an
incomplete HLS pair. Real mpv/controller tests play two local clips consecutively,
then exercise EOF followed by a failed video and recovery through Play now while
preserving queued items. A local HTTP server verifies that a 403 is reported as
an error, not completion, without exposing a secret URL query.

The player retains only a fixed diagnostic category from warning/error messages;
raw logs and signed URLs are not stored or displayed. Classification is best
effort because [mpv log wording is not a stable API](https://mpv.io/manual/master/#json-ipc).
Structured end-file events alone continue to control queue advancement. Repeated
log-message tests verify bounded diagnostic state and safe output.

Live checks are separate from the automated suite, use disposable session copies,
and do not alter the user's queue, saved positions, history or ratings.
With the corrected player, the current video and all three upcoming videos each
reached three seconds of playback with both audio and video streams present and
no playback errors. Output was muted/headless for these checks; no private titles,
IDs, cookies or signed URLs were written to the verification record.

## Publication ages

Cards show compact publication ages (minutes, hours, days, weeks, months, years),
with timestamp precision retained when supplied. Date-only saved records remain
compatible; missing/invalid dates are omitted and future dates say Upcoming.
Feed extraction enables yt-dlp's approximate-date parsing on the existing flat
results, without resolving each video or adding per-video network requests.

Tests cover age boundaries, timezone offsets, unknown/invalid/future dates,
date-only precision and timestamp fallback. A live public search returned dates
for all 30 results, including labels such as 2d ago, 14y ago and 1mo ago. The native
UI was rendered with those public results and visually inspected; age/duration
remain separate from the ellipsized channel name.

## Clipboard, playback choices and Likes

- Native clipboard tests copy a video's canonical URL and paste it back through
  the new Paste link action; invalid clipboard text is rejected.
- Empty-player/empty-queue requests start immediately. Existing playback or queue
  content opens Play now / Add to queue / Cancel. Tests verify that queueing keeps
  the current video and playback position, Play now preserves the interrupted
  item, and merely refreshing a feed does not start playback.
- Synthetic Like tests cover current and legacy YouTube controls, precise video
  targeting, expired authentication, already-liked videos without duplicate
  writes, authenticated request parameters, read-back verification and ambiguous
  failures. The worker receives a disposable private cookie copy. Browsing uses a
  separate worker and cannot cancel an in-flight Like request.
- The five-button preview column (Play, Queue, Copy, Like, More) was visually
  inspected, and layout tests verify it fits inside the thumbnail. Confirmed
  rating state is bounded to visible videos rather than an unbounded cache.
- The 200-refresh memory test remained stable at approximately 200.5 MiB.

A read-only live check inspected YouTube's current Like-control structure for a
public video. It confirmed the expected endpoint fields and rating entity shape;
the saved session reported `loggedOut: true`, so a fresh user connection is needed
before account writes. No real ratings were changed. Successful account mutation
has been tested with synthetic responses, not by liking an arbitrary real video.
Actual Likes are sent only when the user clicks a video's thumb-up button, and the
UI marks success only after a subsequent YouTube response reports that video liked.

## Desktop icon and launcher

The custom SVG icon was rendered and inspected at desktop/dock sizes. The native
window uses the icon name, and its application ID matches the installed desktop
entry. All 65 tests pass after this integration. `desktop-file-validate` accepts
the launcher, and Gio resolves the installed Applications entry and SVG file.

This workstation's pre-existing hicolor theme cache could not be rebuilt, so the
launcher references its installed SVG directly. The themed copy and bundled
window icon remain available. No existing dock favourites were changed.

## Public YouTube checks

These opt-in network checks are separate from the deterministic suite:

```bash
.venv/bin/python scripts/public_smoke.py
GDK_BACKEND=x11 GSK_RENDERER=cairo xvfb-run -a -s '-screen 0 1440x1000x24' \
  .venv/bin/python scripts/ui_smoke.py
xvfb-run -a -s '-screen 0 1280x800x24' \
  .venv/bin/python scripts/public_smoke.py --render
```

- Live public search returned 30 videos.
- The actual GTK search interface displayed 30 videos, fetched 30 thumbnails and
  added three results to the queue.
- Public Big Buck Bunny YouTube playback at a maximum of 720p reached five
  seconds of playback, with no saved account/session. Headless mpv RSS sampled at
  that point was **252.8 MiB**; this excludes the GTK app, transient extractor and
  GPU/display buffers, and is not a total memory guarantee.
- A separate X11 check rendered actual video frames, reached 5.1 seconds of
  playback, and captured the visible movie. mpv RSS in that check was 265.1 MiB;
  audio was muted. The screenshot was visually inspected.
- Generated screenshots are in `test-output/` (ignored by Git):
  `quiettube-preview.png`, `quiettube-live-search.png`, and
  `quiettube-live-playback.png` from the successful rendered playback check.
- `setup.sh` completed successfully, and `run.sh` launched the normal app on the
  user's desktop. No account was imported as part of launch verification.

## Memory regression

`scripts/memory_check.py` replaces a 30-card feed 200 times using real decoded
320×180 synthetic thumbnails in the native GTK interface. It runs in an isolated
process with the Cairo renderer and is included in the default test suite.

The first run caught an actual reference cycle: card-menu callbacks retained their
own popovers. UI RSS grew from 240 MiB after warm-up to about 475 MiB. Replacing
that reference with a GObject weak reference fixed the growth. Subsequent runs
stabilised around **199 MiB**, with effectively zero growth after warm-up across
200 replacements. The regression fails if post-warm-up growth exceeds 35 MiB.

This is a repeated-allocation stress test, not a multi-hour viewing benchmark.
No controlled Chromium comparison has been performed. Codec, resolution, GPU and
rendering backend can change actual memory use; mpv's 64/8 MiB demuxer limits do
not cap the whole process.

## Account connection fix and live verification

The initial account attempt failed because an empty native Chromium configuration
directory hid the actual Snap cookie database. Detection now checks for cookie
database files rather than directory existence, and the extraction worker performs
the same fallback when no explicit profile is supplied. A missing database and a
file-permission failure also receive distinct messages. Regression tests cover
empty native directories, valid native precedence, Snap/Flatpak database layouts,
worker fallback, and preservation of an explicitly selected profile.

After the user reported the login failure, a separate live diagnostic successfully
connected through the corrected Chromium Snap profile and retrieved **30 videos
from the user's subscription feed**. Only success and a count were printed; the
temporary session was removed. This check did not save or expose cookie values,
video titles, or other private account data in the repository. Automated tests
continue to use synthetic fixtures only.

The open app starts a fresh worker for every connection attempt, so retrying
**Connect browser session** loads the fix without restarting the app. Other
personal feeds and account-backed playback still need user verification.

To complete the remaining checks:

1. Start `./run.sh`, click **Connect YouTube**, and sign in on YouTube in Chromium
   (or choose the actual browser you use).
2. Confirm the profile path, then click **Connect browser session**.
3. Check Home, Subscriptions, Watch Later and Liked videos against that account.
4. Add several videos, insert one into the middle, close the browser, and play.
5. Close and reopen QuietTube; confirm the saved queue and resume position.

If YouTube rejects or expires the session, reconnect or use the documented cookie
file fallback. Unofficial home-feed/playlist extraction may change upstream. This
release does not promise an exact copy of YouTube's browser recommendations,
Google OAuth account management, a built-in browser, or synchronisation of local
queue/history edits back to YouTube.
