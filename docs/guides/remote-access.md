# Remote Access

## Overview

By default, Minder is reachable only from the machine it's installed on (or
other devices on the same LAN, once you add a `/etc/hosts` entry — see the
README quickstart). This guide covers accessing it from **outside** your
home network — a phone, a laptop on another network, etc.

> This is unrelated to
> [`docs/development/tailscale-bridge.md`](../development/tailscale-bridge.md),
> which documents a *developer* workflow for reaching a separate dev machine
> from a sandboxed environment. This guide is for reaching your own deployed
> Minder instance remotely as a user.

## Don't port-forward Traefik to the public internet

Nothing about this setup is currently hardened for direct internet exposure:

- **No real DNS + TLS** — Traefik serves a self-signed certificate; browsers
  will warn on every visit, and nothing validates who you're actually
  connecting to over the open internet.
- **Shared default Authelia password** — every clone of this repo ships the
  same admin credential until you rotate it (see
  [authentication.md#rotating-the-admin-password](authentication.md#rotating-the-admin-password)).
  Exposing the login page to the internet before rotating it is a real risk,
  not a theoretical one.
- **IP-whitelist middleware** on the Traefik dashboard, RabbitMQ management
  UI, and Neo4j browser routes assumes a trusted network — a public IP
  breaks that assumption entirely.

Port-forwarding `443`/`8000`/etc. on your router is the wrong tool for
"I want to use this from outside my house." A VPN gets you the same result
without any of the above exposure.

## Recommended: Tailscale

[Tailscale](https://tailscale.com) (or any WireGuard-based VPN) puts your
phone/laptop on the same private network as the machine running Minder, with
no ports opened to the public internet at all. This isn't hypothetical setup
work — if the host running Minder is already a tailnet member (check with
`tailscale status` on that machine), you already have everything you need.

1. **Join the same tailnet** on the device you want to access Minder from
   (install Tailscale, `tailscale up`, sign in with the same account/tailnet
   as the Minder host).
2. **Find the Minder host's tailnet IP**: run `tailscale status` on the
   Minder host itself and note the `100.x.y.z` address next to its hostname.
3. **Add the same `/etc/hosts` entry the README quickstart uses, but with the
   tailnet IP instead of `127.0.0.1`**:
   ```
   100.x.y.z chat.minder.local
   ```
   (On a phone, most Tailscale apps don't let you edit `/etc/hosts` directly —
   use a browser and the tailnet IP directly, e.g. `https://100.x.y.z`, or a
   local DNS/hosts-editing app.)
4. Open `https://chat.minder.local` (or the raw tailnet IP) exactly as you
   would on the LAN — same self-signed-cert warning, same Authelia login.

If your tailnet has **MagicDNS** enabled, `tailscale status` will show
resolvable `<hostname>.<tailnet>.ts.net` names instead of raw IPs — you can
use one of those directly as the `/etc/hosts` target, or skip the hosts-file
step entirely and browse straight to `https://<host>.<tailnet>.ts.net` if you
don't need the exact `chat.minder.local` name (some services key off that
hostname for CORS/routing, so prefer the `/etc/hosts` approach if anything
looks broken).

## What's not supported yet

Public internet exposure with real DNS + a CA-issued certificate isn't set up
in this repo (see the "Future Plans" list in the README) — the tailnet
approach above is the supported path today, not a workaround for a
first-class feature that exists elsewhere.
