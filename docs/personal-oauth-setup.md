# Personal Desktop OAuth setup (experimental)

Open **Connect YouTube → Personal OAuth · experimental**. Follow the same steps
below, then import your downloaded JSON or paste the two fields inside QuietTube.
Do not send credentials to the maintainer, a chat, an issue or GitHub.

This implementation has synthetic authorization/API tests and an isolated real
keyring test. **Live Google sign-in, renewal over days and practical quota usage
have not been verified.** Browser-session import remains available without Cloud
setup. OAuth is an optional experiment, not a promised cure for missing videos.

## Google setup and what to enter

Checked against Google's documentation on 8 November 2026. Console labels may
change. All pages must have the same personal project selected.

### 1. Create your personal project

[1. Create your personal project](https://console.cloud.google.com/projectcreate)

Project name: QuietTube Personal (or a name you recognize). Select that same project on every page below. YouTube Data API does not require paid billing; check that this project is not linked to your existing billing account. Your organization's administrator may restrict project creation.

### 2. Enable YouTube Data API v3

[2. Enable YouTube Data API v3](https://console.cloud.google.com/apis/library/youtube.googleapis.com)

Check your project in the top selector, then choose Enable. You do not need an API key for this OAuth connection.

### 3. Configure the consent screen

[3. Configure the consent screen](https://console.cloud.google.com/auth/branding)

Google Auth Platform → Branding → Get started (if shown). App name: QuietTube Personal. User support email and contact email: your own email. For a personal Gmail account choose External as the audience. Review Google's terms, then create the configuration. Use accurate information; do not enter QuietTube maintainer contact details.

### 4. Add yourself as a test user

[4. Add yourself as a test user](https://console.cloud.google.com/auth/audience)

Audience → Testing → Test users → Add users: enter the Google email you will sign in with. Testing access for YouTube scopes expires after seven days; you may need to sign in again. Publishing and verification have additional requirements and are not a promise of permanent access.

### 5. Add the YouTube scope

[5. Add the YouTube scope](https://console.cloud.google.com/auth/scopes)

Data Access → Add or remove scopes → manually add the scope shown below, then Update/Save. It supports reading account feeds and the Like action. Google's permission description is broader than those features; review it before approving access. QuietTube does not upload or delete videos.

```text
https://www.googleapis.com/auth/youtube.force-ssl
```

### 6. Create a Desktop client

[6. Create a Desktop client](https://console.cloud.google.com/auth/clients)

Clients → Create client. Application type: Desktop app. Name: QuietTube on my computer. Choose Create, then Download JSON. Keep the file outside the repository, for example in Downloads. A Desktop client does not need a website URL or a manually configured redirect URI; QuietTube uses a temporary local callback.

### 7. Import here, then sign in

Use Import Desktop JSON below. Alternatively copy Client ID and Client secret from that same Desktop client into the two matching fields, then Save to keyring. Paste neither an API key, project ID, Google password nor access token. Then choose Sign in with Google. Check that the consent screen identifies your own project. You may close the browser afterward; account requests use OAuth, not copied browser cookies.

The JSON must contain an `installed` Desktop client, not a `web` client or service
account. Import reads at most 16 KiB, validates the client and fixes the Google
endpoints. Manual entry expects a Client ID ending in `.apps.googleusercontent.com`
and its matching Client secret. The secret field is masked. Both entry fields
clear after submission; no values are inserted into source code or environment files.

**Save to keyring** stores configuration without changing the current connection.
**Sign in with Google** opens your regular browser for consent, then receives a
callback on a temporary `127.0.0.1` port. You have four minutes to finish consent.
Successful authorization switches the active method. Closing the connection dialog
cancels the worker and callback; a late result cannot switch the UI's account mode.
The queue/history are preserved. If switching stops an active video, resume manually.

Google's [Desktop OAuth flow](https://developers.google.com/identity/protocols/oauth2/native-app),
[consent setup](https://developers.google.com/workspace/guides/configure-oauth-consent)
and [YouTube Python quickstart](https://developers.google.com/youtube/data/quickstart/python)
are the reference instructions. A Desktop client identifies your application;
access and refresh tokens authorize your account. QuietTube does not collect your
Google password and ships no maintainer registration.

## Storage and removal

Saved client configuration and tokens stay in your desktop Secret Service keyring, not in the checkout, SQLite database or an exported JSON file. Use a password-protected login keyring. If it is unavailable, saving fails without a plaintext fallback. The downloaded Google JSON remains wherever you saved it; QuietTube does not remove that original file. Keep it private and outside GitHub.

On GNOME, the login keyring is usually unlocked when you log into Linux. Other
desktops need a compatible Secret Service implementation; installing the Python
package alone does not create one. On Debian/Ubuntu, GNOME Keyring is provided by
`gnome-keyring`; use your desktop's keyring manager to create/unlock a protected
login keyring. Do not choose an empty password merely to bypass an error.

One item named **QuietTube personal OAuth** holds the client and tokens for each
local QuietTube library. The keyring service owns its storage location. The normal
app data directory (`$XDG_DATA_HOME/quiettube`, or `~/.local/share/quiettube`) contains
only OAuth status hints in SQLite, an empty private lock file and a private bounded
feed-metadata cache. The config and tokens are not copied there. Workers receive
configuration through stdin; fixed error messages omit credentials and raw OAuth
responses. Common Google client JSON filenames are ignored by Git as a second
safeguard. Arbitrarily named files or forced Git additions can still expose data.

**Remove personal OAuth from keyring** deletes the local configuration, tokens and
API feed cache. It preserves your queue/history and does not silently select a
saved browser session. Revoking Google's grant is separate: follow the dialog's
[Google permissions link](https://myaccount.google.com/connections) and remove the
project's access there. Previously imported browser cookies stay saved until you
choose **Remove saved browser session**; they are unused while OAuth is selected.

## Features, quota and costs

Experimental: live account reliability and daily quota usage are not yet verified. Home becomes recent subscription uploads; Watch Later is unavailable through this API. Shorts may appear. OAuth does not authenticate mpv or fix playback errors. Your project has its own limited quota, not unlimited access. Google's distribution and playback policy questions remain unresolved. Browser-session import remains available as a separate choice.

| Action in OAuth mode | Behavior / bound |
|---|---|
| Home / Subscriptions | Same newest-first snapshot: up to 500 subscriptions alphabetically, ten recent uploads per channel, 300 videos total, 30 per page |
| Navigation | Reuses the snapshot for ten minutes; manual Refresh rebuilds it |
| Search / playlists / Liked videos | Data API requests; up to ten pages, with pagination tokens |
| Like | Explicit API request after clicking the thumb-up control; no background ratings |
| Watch Later | Not available through OAuth; use the local queue |
| YouTube watch history / resume | Optional website-session sharing under Connect playback; separate from OAuth |
| Playback | yt-dlp/mpv; an explicitly connected separate playback session may be used. OAuth tokens and old browser-account cookies are not passed to mpv |

Quota belongs to the **project**, not each user, client ID or device. Separate
client IDs under your project still share its limits. See the [quota explanation
and billing distinctions](../README.md#direction-personal-credentials-and-freedom-to-run-locally).
YouTube API allocation does not require attaching your paid Cloud billing account.
Check the project's actual quotas and billing association in Google Cloud; do not
create more projects or rotate credentials to evade a limit.

A full subscription refresh costs roughly one upload-list call per channel, plus
subscription/channel pagination and batched metadata calls. For 100 channels that
is approximately 110 API calls (2 subscription pages + 2 channel batches + 100
upload lists + up to 6 metadata batches), excluding initial sign-in/renewal. This
is a request-count estimate, not a measured daily quota budget. Search and other
methods may use different quota buckets/costs. Repeated Refresh can exhaust even
a personal allocation; QuietTube does not poll in the background. A quota error
stops new subscription batches (up to four requests may already be in flight),
preserves the queue and does not switch connection methods.

## Troubleshooting

- **Keyring unavailable/locked:** unlock your protected desktop keyring and retry.
  Nothing falls back to a plaintext credentials file.
- **Invalid client:** use Desktop app JSON or the matching Client ID and secret;
  an API key, project ID, web client or service-account key will not work.
- **Access denied:** check the same project has YouTube Data API v3 enabled, your
  exact Google email is a test user, and you approved the requested scope.
- **Expired/revoked access:** sign in again using the stored client. External apps
  in Testing normally get seven-day refresh tokens for YouTube scopes. Publishing
  is a separate Google process, not a guarantee against expiry. See [Google's
  expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration).
- **Quota exhausted:** check the project's quota page and wait for the relevant
  reset or request an extension through Google's process. Another sign-in does
  not reset quota, and excess requests are not an automatic paid upgrade.
- **Different feed or restricted playback:** these are feature/media-access gaps,
  not necessarily expired authorization. Read [account direction](account-direction.md)
  for the unresolved distribution and playback policy questions.

Never attach client JSON, tokens, cookies or unredacted screenshots to a bug report.
