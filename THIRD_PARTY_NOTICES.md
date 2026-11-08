# Third-party software and assets

The MIT license covers QuietTube's original code and original bundled SVG assets.
Dependencies keep their own licenses; service names do not imply endorsement by
YouTube or Google, or grant rights to their trademarks.

| Component | Role / upstream license |
|---|---|
| yt-dlp Python package | Extraction; Unlicense, with separate notices for optional/bundled components |
| yt-dlp-ejs and JavaScript dependencies | Extractor support; retain their Unlicense/MIT/ISC notices as applicable |
| google-auth, google-auth-oauthlib | Google OAuth client libraries; Apache-2.0 |
| requests, requests-oauthlib, oauthlib | HTTP and OAuth transport; Apache-2.0 / ISC / BSD respectively |
| SecretStorage | Linux keyring integration; BSD license |
| Python, PyGObject, GTK, GLib | Native runtime; system package licenses including PSF/LGPL |
| mpv | External player; GPL/LGPL depending on build/components |
| Node.js | JavaScript runtime; Node distribution license and bundled notices |
| ffmpeg | Test/media tooling; LGPL/GPL depending on build configuration |

See `requirements.txt`, `requirements-dev.txt`, `pyproject.toml` and installed
package metadata for dependency versions and individual notices. Runtime binaries,
GTK libraries and fonts are installed separately and are not bundled here.
An MIT application license does not relicense those components. Audit the actual
artifacts and any source/notice obligations before shipping a binary bundle.

The Like adapter was informed by the public YouTube.js endpoint structure, linked
in the user guide. Demo titles and placeholders illustrate the interface; screenshots
contain no personal feed or session. Test videos are generated locally with ffmpeg.
No YouTube video, browser cookie export or third-party thumbnail collection is
included in the public source snapshot. System fonts retain their own licenses.
