# ADR 0002: investigate user-owned account connections

Date: 8 November 2026. Human owner: Paulo Aboim Pinto.

Status: accepted as a direction for investigation and documentation; implementation,
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

Investigate a model where the person supplies a Desktop OAuth configuration from
their own Google Cloud project, keeps authorization locally and consumes that
project's allowance. Ship no shared maintainer registration. Keep credentials out
of the source tree and public artifacts. Preserve MIT licensing and local
queue/history ownership; distinguish these software freedoms from access to Google.

Describe this as planned until usable and verified. Keep current browser-session
instructions accurate in the meantime. Do not bundle the unfinished shared-client
experiment with this documentation change.

## Consequences and unresolved work

Personal setup is harder than a shared Sign in button. Project quotas, token
expiration, account-feature gaps and mpv media access still require explicit
handling. Separate projects do not establish that Google permits this distribution
model; the one-project-per-client and quota-sharding rules remain an open question.
No credential rotation across projects to evade limits is part of the design.

The [account direction document](../account-direction.md) records the alternatives,
billing distinctions, current sources and release criteria. A working OAuth callback
alone is not acceptance evidence for this architecture.
