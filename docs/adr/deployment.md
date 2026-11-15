# ADR: Deployment

Status: Accepted
Date: 2026-11-15 (deployment complete, alert verified on device)
Related: docs/001.1--llm--FORGE_DEPLOYMENT.md (postmortem), docs/001.2--llm--STANDALONE_DROPLET_DEPLOYMENT.md, docs/001.11--llm--MIGRATE_TO_FORGE.md

## Context

Two hosting worlds were available: the Forge-managed droplet `alfaForge` (already paid for, hosts a
mission-critical client site `wana....org` and wmw) or a fresh droplet. On 2026-10-24 a single bad nginx
fragment on alfaForge took nginx down for 3 days and the client site with it — nginx validates all
included files atomically, so one syntax error anywhere refuses the whole master process. That postmortem
(001.1) is the founding constraint of this ADR. No custom domain is owned; DNS provider options were
DuckDNS, nip.io/sslip.io, or placeholder.

## Decision

**Isolated droplet, not Forge.** Daily Koan deploys to its own DigitalOcean droplet ("dkStandalone",
Ubuntu 24.04, 1 vCPU / 512MB). Rationale: the only real failure-domain isolation is a separate machine —
on a dedicated droplet a bad nginx file costs a koan, not a client. Cost: $6/mo. A later, gated migration
path onto Forge exists (001.11) but is deliberately deferred until the app has been boring for weeks.

**Provider domain, not raw IP.** Public name is `dailykoan.duckdns.org` (free DuckDNS subdomain, short
fixed TTL). Chosen over nip.io/sslip.io because the name survives a future droplet/IP change — origin
stability protects every Web Push subscription and iOS PWA install (both bind to origin). Raw IP names
embed the IP and would force a re-subscribe event on any move. Adopting a real owned domain later remains
possible but is itself an origin change (documented, not chosen).

**Stack shape (no Forge on this box):**

- gunicorn, `--workers 1`, bound to `127.0.0.1:8001`, systemd `dailykoan.service`, run as system user `koan`
- nginx in front: **full `server { }` block** in `sites-available/koan` (the body-only-fragment rule applies
  only to Forge-managed sites; this droplet has no Forge)
- static assets, `manifest.json`, `sw.js` aliased and served by nginx directly; everything else proxied
- HTTPS via certbot (`--nginx`), Let's Encrypt, auto-renewal dry-run gated
- daily push via `dailykoan-push.timer` `OnCalendar=*-*-* 08:00:00` (UTC) — see push-pipeline ADR

**Operating rules (hard gates, from the postmortem):** `nginx -t` before every reload; reload, never
restart; baseline curls after every nginx change. On this droplet a gate failure only ever affects the
koan — but the rules stay because they cost nothing.

**Security posture:** SSH key-only (password auth disabled after key+sudo gates passed), UFW
(OpenSSH/80/443 allowed before enable), unattended-upgrades, `koan` as a no-login system user owning the
app tree, deploy user `alvar` with sudo.

## Consequences

- +$6/mo over the "free" Forge option; that money buys the client site never sharing a blast radius with us.
- Droplet IP is redacted from the repo (public repo) — placeholders in docs, real IP in local notes only.
- DuckDNS TTL is short and fixed — the 001.11 cutover needs no TTL games, but we cannot lengthen it either.
- 512MB is enough for 1 worker + nginx + SQLite; watch journalctl for memory pressure, swapfile is the cheap fix.