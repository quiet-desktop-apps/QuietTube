# ADR 0004: optional website-session history and position sharing

Date: 9 November 2026. Human owner: Paulo Aboim Pinto.

Status: requested by the maintainer; implemented with live server read-back.

The maintainer requested sharing QuietTube viewing and the current position so
YouTube can use history for recommendations and offer resume on another device.
This extends ADR 0003's explicitly connected website session; OAuth remains for
account feeds and Likes. New installations default off. No historical bulk upload.

Do not enable yt-dlp's global mark-watched option: that executes during extraction
and reports near-full duration. Instead report the actual position using the
YouTube.js MediaInfo.updateWatchTime approach (st/et/cmt at current position),
after observing playback, and on explicit user opt-in for a saved current video.
Do not invent intervals across seeks or mark an opened/failed video complete.

Typed PlaybackObservation messages decouple queue ownership from the history
sender. One short-lived worker processes a report at a time, with 30-second
periodic updates and pause/stop/transition flushes. Coalesce at most five pending
video positions. Ignore stale completions; account changes and opt-out cancel
pending work. Playback never waits for network success. On shutdown wait at most
three seconds, then cancel; do not replay stale positions after restarting.

Requests require a signed-in watch page matching the exact video and YouTube-only
statistics endpoints. Cookies stay in a disposable private copy. Raw endpoints,
page contents, cookie values and errors never enter UI or logs. HTTP acceptance is
labelled sent, not verified. The live verification record separately confirms a
YouTube history entry with a matching resume point; cross-device behavior is not
assumed for every client. This is one-way reporting, not reverse synchronization.

References:
- https://github.com/LuanRT/YouTube.js/blob/main/src/core/mixins/MediaInfo.ts
- https://github.com/yt-dlp/yt-dlp/blob/2026.10.26/yt_dlp/extractor/youtube/_video.py
- https://support.google.com/youtube/answer/7174115?hl=en
