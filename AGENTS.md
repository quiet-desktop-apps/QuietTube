# QuietTube

Native Linux GTK4/Python app with mpv playback. This is an independent repository
in the Quiet organization. Run Git operations from this directory.

- Keep the app free of embedded browser engines. Browser-assisted login is a
  transient user action; normal playback must work with the browser closed.
- Never read the user's real cookies in tests. Use synthetic fixtures and
  temporary private directories. Never log session content or signed media URLs.
- Preserve explicit worker/player completion messages and ignore stale results.
  EOF alone advances the queue; errors and closing the player preserve it.
- Keep feed, thumbnail, buffer, queue and history bounds explicit and tested.
- Run `./test.sh` after behavioural changes. Tests include real mpv/GTK integration
  and need display/socket access (`xvfb-run` is suitable).
- Keep yt-dlp pins in requirements.txt and pyproject.toml aligned.
- Record live YouTube/account verification separately from deterministic tests.
- Do not start sub-agents unless Paulo explicitly asks.

- Read `docs/agentic-engineering.md` for human/agent ownership.
- Default branch: `master`. All changes need a PR and required CI; never push
  directly to master or bypass protections. Merge only for a human-authorized
  publication/merge task after required checks pass.
