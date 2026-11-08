# ADR 0002: browser-session entry path and optional personal OAuth

Date: 8 November 2026. Human owner: Paulo Aboim Pinto.

Status: accepted for an experimental implementation at the human owner’s request.
Configuration, keyring storage and API routing are implemented;
live verification and service-policy suitability remain incomplete. ADR 0001's
native UI and resource bounds remain in force.

## Context

The initial browser-session import proved that browsing and mpv playback can run
with the browser closed. It did not remove dependence on browser-derived cookies.
Expiration, rotation and import failures require reconnection; an existing cookie
file can coexist with signed-out feed results.

A single shared OAuth registration would renew authorization but introduce shared
project quota and maintainer ownership for every installation. A hosted backend
would add operating costs and responsibility for account data without eliminating
that quota. QuietTube is intended as an independently operated personal desktop
tool rather than a commercial hosted account service.

## Direction

Keep browser-session import as the entry path so people can try QuietTube without
Google developer setup. Let them evaluate its usefulness and session limitations
at their own pace, without a timed trial, payment or forced migration.

Investigate personal OAuth as an optional second method: the person supplies a
Desktop OAuth configuration from their own Google Cloud project, keeps
authorization locally and consumes that project's allowance. They can choose it
when its benefits justify the setup, without needing to encounter a failure first.
Ship no shared maintainer registration. Keep credentials out of the source tree
and public artifacts. Preserve MIT licensing and local queue/history ownership;
distinguish these software freedoms from access to Google.

Label the implementation experimental until live use is verified. Keep browser-
session instructions accurate. Store the personal client and tokens in the Linux
Secret Service keyring with no plaintext fallback; accept JSON import or manual
Client ID/secret fields. Include precise Google setup links in the native panel.
Switching preserves queue/history, identifies the active method and never silently
restores browser-cookie dependence when OAuth fails. State/PKCE, token renewal,
keyring round-trips and mode transitions are tested with synthetic data.

## Consequences and unresolved work

Improved account reliability is an untested hypothesis, not an accepted outcome.
Personal OAuth may replace browser-session problems with a quota bottleneck.
Measure realistic daily API consumption, feed coverage and reconnection behavior
before recommending it as an improvement over the existing connection.

Maintaining two connection methods adds testing and support work. Personal setup
is harder than a shared Sign in button. Project quotas, token
expiration, account-feature gaps and mpv media access still require explicit
handling. Separate projects do not establish that Google permits this distribution
model; the one-project-per-client and quota-sharding rules remain an open question.
No credential rotation across projects to evade limits is part of the design.

The [account direction document](../account-direction.md) records the alternatives,
billing distinctions, current sources and release criteria. A working OAuth callback
alone is not acceptance evidence for this architecture.
