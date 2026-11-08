# Account connection: history, direction and trade-offs

Status as of 8 November 2026: the published app uses browser-session import.
Personal OAuth is a proposed direction. An unfinished development experiment is
not a working sign-in feature, a release or proof of Google's approval. No real
OAuth client configuration has been bundled or published by this project.

## What the first implementation achieved

The original goal was to browse videos and play an editable queue without keeping
YouTube tabs open in a Chromium-based browser. QuietTube uses a GTK interface,
short-lived yt-dlp workers, a local SQLite library and one mpv player.

The user signs in on YouTube in a normal browser, then explicitly imports that
browser's session into QuietTube. Only YouTube cookies are retained. The browser
can close after import: it does not render the native video wall or the mpv window.
There is no embedded browser engine or Quiet-hosted backend. No Google developer
project is required by this implementation.

This gave us access to account feeds without first running an OAuth application.
See the [current connection instructions](usage.md#connect-your-youtube-account)
and [privacy boundaries](architecture.md#account-privacy-and-network-boundaries).

## Why it is not the final connection model

A copied session remains a dependency on YouTube's website login:

- Cookies can expire, rotate or be invalidated. A saved cookie file is not proof
  of an authenticated connection, and a snapshot does not automatically track
  browser changes.
- Cookie import depends on browser/profile locations, OS permissions and keyring
  decryption. Selecting the wrong profile can mean importing no usable login.
- An expired session can fail explicitly, or a public feed can still return
  signed-out results. A manual investigation found the latter: a saved session
  was unauthenticated, and the returned recommendations did not match the user's
  signed-in dashboard. This was not evidence that ordinary videos had been
  deliberately classified as Shorts or members-only content.
- Website extraction can break when YouTube changes its pages or restrictions.
  Reconnecting and updating the extractor are maintenance tasks, not guarantees.
- Returning to the browser to repair account access conflicts with the intended
  day-to-day experience, even though the browser stays closed during playback.

Other observed limitations have different causes. Watching through mpv does not
update YouTube watch history; QuietTube's completed-video filtering is local.
Sorting a loaded page cannot find newer videos on pages not fetched. Home
recommendations are not a complete chronological subscription feed. Decoder,
network or stream failures are playback issues, not necessarily login failures.
OAuth must not be presented as a fix for all of them.

## Options considered

| Model | What it offers | Difficulty or limitation |
|---|---|---|
| Existing browser-session import | No developer setup; access to website account feeds | Cookie expiry/rotation, import failures and repeated browser reconnection; unofficial extraction |
| One shared Desktop OAuth registration | Simple sign-in for users; refreshable account access | Every installation consumes the maintainer project's allowance; desktop configuration is extractable; shared operational dependency |
| QuietTube-operated backend | Server-side confidential credentials, caching and request controls | Hosting, security and privacy responsibilities; still the same project quota; not the intended standalone utility |
| Personal project and Desktop OAuth client | Locally owned configuration and project allowance; no QuietTube server | Each person must configure Google Cloud; token lifecycle, API feature gaps and distribution-policy questions remain |
| Local subscriptions without Google account integration | No shared OAuth registration; local library and public-channel feed | No synchronized account Likes/private lists; public extraction still depends on YouTube and can break |

The human-selected direction to investigate is **personal credentials**, not a
commercial hosted account service. That describes product intent, not a change to
the MIT license: its permissions still include redistribution and commercial use.
The code's license does not override Google's service terms.

## Intended personal setup

This is the proposed workflow, not a walkthrough of buttons available today:

1. The person creates a Google Cloud project under their own eligible Google
   account and enables YouTube Data API v3. Managed accounts may require their
   administrator's permission.
2. They configure Google's consent settings and create a **Desktop app** OAuth
   client. A client ID under somebody else's project does not provide a new quota.
3. QuietTube imports the configuration into private local application storage,
   outside the checkout. No maintainer credentials, client JSON files, cookies or
   user tokens belong in GitHub, issue reports or screenshots.
4. A temporary browser visit lets Google authenticate the person and obtain
   consent. QuietTube does not collect their Google password.
5. The app uses its own OAuth authorization for account data, renewing access
   when possible. Disconnect must remove local authorization and support revoking
   access. Secure token storage and cancellation behavior need implementation and
   verification before release.

Google documents the Desktop client setup in its
[YouTube Python quickstart](https://developers.google.com/youtube/data/quickstart/python).
Client configuration identifies the application; access/refresh tokens represent
the user's authorization. Neither belongs in the public repository. Google's
[OAuth policy](https://developers.google.com/identity/protocols/oauth2/policies)
also requires secure credential handling and encrypted token storage at rest.

## Quota ownership and costs

The [README](../README.md#direction-personal-credentials-and-freedom-to-run-locally)
lists the default daily allocations checked on 8 November 2026. Google's project
console is the source of truth for the allocation actually granted.

| Configuration | Quota relationship |
|---|---|
| Many users authorize one QuietTube registration | Shared project allocation |
| Several OAuth client IDs inside one project | Still the same project allocation |
| One person's laptop and desktop use that project | Both consume that allocation |
| Independently configured personal projects | Separate project allocations, subject to Google's rules |

Quota measures API operations, not watching time or RAM. A list call can return
multiple videos; refreshing many channels may require many calls. Pagination and
failed requests can consume quota too. Caching, bounded refreshes and batching
matter even for personal use. A new login does not replenish quota.
[API usage accounting](https://developers.google.com/youtube/data/getting-started#quota-usage)

YouTube Data API does not require a paid Cloud subscription for its allocated
usage. A Google identity, a Cloud project and a billing account are different
things. Someone already paying for other Google Cloud services can use a separate
project and check that billing is disabled for it. This does not alter their
existing paid projects. Other enabled paid APIs or hosted infrastructure are not
covered by the YouTube API's no-billing setup.
[YouTube API billing explanation](https://dev.to/googleworkspace/getting-started-using-google-apis-api-keys-part-2-38i6),
[Google project billing](https://support.google.com/googleapi/answer/6158867?hl=en)

Requests over the relevant allowance fail. More quota is a request for Google to
review, not an automatic purchase. QuietTube must show a useful quota error and
preserve the user's queue. No rotating credential pool or automatic project
creation is proposed.
[Quota extension process](https://developers.google.com/youtube/data/guides/quota_and_compliance_audits)

## What remains difficult

- **Refresh tokens are not permanent.** Google can revoke access. External apps
  left in OAuth **Testing** receive seven-day refresh tokens for YouTube scopes.
  Leaving Testing is not a promise of permanent access or automatic exemption
  from verification. Expired authorization must produce an explicit sign-in
  request, not an apparently connected but anonymous wall.
  [Google token expiration rules](https://developers.google.com/identity/protocols/oauth2#expiration)
- **Account data and playback are separate.** Data API authorization does not
  supply a supported mpv media stream. The intended newest-first subscription
  feed would differ from YouTube's personalized Home. Website features such as
  Watch Later and watch history cannot simply be assumed available via OAuth;
  account feature coverage and media access need separate validation.
- **Independent quota is not unlimited or approved access.** YouTube requires
  one API project per API client and forbids quota sharding. How those rules apply
  to distributing the same application with mandatory personal projects remains
  unresolved. Personal or noncommercial intent does not by itself establish an
  exception. We do not present this design as a way to bypass limits or bans.
  [YouTube credentials policy](https://developers.google.com/youtube/terms/developer-policies#d.-accessing-youtube-api-services),
  [quota-sharding guidance](https://developers.google.com/youtube/terms/developer-policies-guide)
- **Playback policy also needs resolution.** YouTube's API policies restrict
  non-API retrieval of its content. Combining official account endpoints with
  yt-dlp/mpv cannot be described as an approved integration without resolving that
  compatibility question.
  [YouTube prohibited actions](https://developers.google.com/youtube/terms/developer-policies#i.-additional-prohibitions)

The release criteria are therefore broader than successful sign-in: usable setup,
private credentials, refresh/revocation handling, accurate account state, bounded
quota consumption, clear feature differences, tested playback boundaries and an
established distribution-policy position. This documentation records the direction
and its limits; it does not claim that those criteria have been met.
