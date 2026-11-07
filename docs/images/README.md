# Publication screenshots

Captured on 8 November 2026 from the actual app, using its offline demo in an
isolated Xvfb/D-Bus session. No account, real messages, cookies, personal feed or
pairing QR code is visible. Demo content is labelled in the image and main README.
These are captures of the application, not product mockups.

From the repository root, after installing dependencies/building as documented:

```bash
GDK_BACKEND=x11 GSK_RENDERER=cairo xvfb-run -a -s '-screen 0 1500x1100x24' \
  dbus-run-session -- .venv/bin/python scripts/capture-demo.py
```
