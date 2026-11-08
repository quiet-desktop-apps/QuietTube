# ADR 0003: explicit playback session alongside personal OAuth

Date: 9 November 2026. Human owner: Paulo Aboim Pinto.

Status: accepted for a local trial at the maintainer's request.

OAuth account feeds continued working while anonymous yt-dlp/mpv extraction failed
with YouTube's bot-verification challenge. Repeating Data API sign-in cannot
authorize that extraction. ADR 0002 remains the account-feed direction.

Offer an explicit **Connect playback** action. Save only YouTube cookies in a
separate private file outside the checkout and enable it only after an explicit
successful import. In OAuth mode, mpv receives a disposable copy of this file;
OAuth still supplies account feeds and Likes. In browser-account mode, preserve
the original account session route. Never automatically import an old browser
session or switch account modes. Removal preserves OAuth and the queue.

Saving validates the local jar, not the remote stream. Report it as saved until
actual playback is tested. Do not retry automatically or add a browser engine.
This reintroduces cookie expiry/import dependence for playback; it does not deliver
browser-independent authorization or guaranteed YouTube compatibility.

A bounded live trial loaded the queued video and rendered changing frames; see
[verification](../verification.md). Keep synthetic regression tests separate from
live account checks. Long-term idle/resume and expiry behavior remain unverified.
