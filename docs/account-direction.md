# Account connection: history, direction and trade-offs

Status as of 9 November 2026: browser-session import remains the entry path.
QuietTube implements optional personal OAuth configuration, keyring storage,
authorization and bounded API feeds. Synthetic tests are not live account
verification, a release or proof of Google's approval. No real OAuth client
configuration is bundled. See the [setup guide](personal-oauth-setup.md).

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

## Why offer an alternative connection model

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

Other observed limitations have different causes. Optional website-session
reporting now shares playback positions with YouTube; it is separate from OAuth
and from QuietTube's local completed-video filtering.
Sorting a loaded page cannot find newer videos on pages not fetched. Home
recommendations are not a complete chronological subscription feed. Decoder,
network or stream failures are playback issues, not necessarily login failures.
OAuth must not be presented as a fix for all of them.

## Try first, choose the connection that fits

The product direction keeps browser-session import as the entry path.
Someone can install QuietTube, connect their existing session and try the native
interface, queue and mpv playback without first learning Google Cloud setup. The
browser can then close, subject to the session limitations described above.

Evaluation is informal and user-controlled: there is no countdown, paywall or
forced migration. People can judge the app's usefulness and observe whether
reconnection or account-feed problems affect their own usage. They can continue
with browser-session import while it meets their needs and remains usable.

Personal OAuth is an experimental **optional second connection method** for people willing to configure and maintain their own Google
project. They need not wait for a failure to choose it. The setup should explain
which account features change and which problems it addresses before they switch.
It must not promise identical Home recommendations, unlimited quota, permanent
sign-in or a fix for mpv failures.

The expected improvement is a hypothesis: refreshable OAuth authorization may
reduce the problems caused by copied website sessions, but live use has not yet
validated that expectation. We may encounter a new wall in the form of API quota,
even with a single person owning the entire project allowance. This is an optional
experiment, not a proven upgrade or a reason to remove the existing method.

Validation must measure requests and quota consumption for realistic subscription
counts, refresh frequency, pagination, searches and Likes. It must also exercise
token renewal, revoked access and quota exhaustion over ordinary daily use. Compare
the resulting feed coverage and reconnection burden with browser-session import;
passing isolated sign-in or synthetic tests is not enough to claim improvement.

Switching preserves the local queue and history, identifies the active connection
method and avoids silently falling back to browser cookies when OAuth expires.
These transitions are covered by synthetic GTK tests; live account checks remain. Offering two methods also adds maintenance and testing work: both
account states, failures and transitions need coverage.

## Options considered

| Model | What it offers | Difficulty or limitation |
|---|---|---|
| Existing browser-session import | No developer setup; access to website account feeds | Cookie expiry/rotation, import failures and repeated browser reconnection; unofficial extraction |
| One shared Desktop OAuth registration | Simple sign-in for users; refreshable account access | Every installation consumes the maintainer project's allowance; desktop configuration is extractable; shared operational dependency |
| QuietTube-operated backend | Server-side confidential credentials, caching and request controls | Hosting, security and privacy responsibilities; still the same project quota; not the intended standalone utility |
| Personal project and Desktop OAuth client | Locally owned configuration and project allowance; no QuietTube server | Each person must configure Google Cloud; token lifecycle, API feature gaps and distribution-policy questions remain |
| Local subscriptions without Google account integration | No shared OAuth registration; local library and public-channel feed | No synchronized account Likes/private lists; public extraction still depends on YouTube and can break |

The human-selected direction is **browser-session import first, with optional
personal credentials to investigate**, not a commercial hosted account service.
That describes product intent, not a change to
the MIT license: its permissions still include redistribution and commercial use.
The code's license does not override Google's service terms.

## Optional personal setup

The [step-by-step setup guide](personal-oauth-setup.md) matches the native panel.
This is not a prerequisite for trying browser-session mode:

1. The person creates a Google Cloud project under their own eligible Google
   account and enables YouTube Data API v3. Managed accounts may require their
   administrator's permission.
2. They configure Google's consent settings and create a **Desktop app** OAuth
   client. A client ID under somebody else's project does not provide a new quota.
3. QuietTube imports the configuration into the Linux Secret Service keyring,
   with no plaintext fallback. No maintainer credentials, client JSON files, cookies or
   user tokens belong in GitHub, issue reports or screenshots.
4. A temporary browser visit lets Google authenticate the person and obtain
   consent. QuietTube does not collect their Google password.
5. The app uses its own OAuth authorization for account data, renewing access
   when possible. Remove personal OAuth deletes local keyring data; a separate
   link opens Google permissions to revoke server-side access. Cancellation and
   storage tests use synthetic data, including an isolated real keyring.

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
  to distributing the same application with optional personal projects remains
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
quota consumption measured against realistic daily use, clear feature differences,
tested playback boundaries and an
established distribution-policy position. This documentation records the direction
and its limits; it does not claim that those criteria have been met.

## Playback session trial

Personal OAuth does not authorize yt-dlp/mpv extraction. An explicit separate
**Connect playback** flow now allows a YouTube website session for mpv while
keeping OAuth for feeds and Likes. A live trial restored video playback, but
requires browser-derived cookies and does not remove their expiry limitations.
See [ADR 0003](decisions/0003-separate-playback-session.md) and the
[verification record](verification.md) for the decision and evidence.
