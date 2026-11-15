# ADR: Filesystem

Status: Accepted (dkStandalone layout) / Proposed (Forge-path layout notes)
Date: 2026-11-16
Related: docs/adr/deployment.md, docs/001.2--llm--STANDALONE_DROPLET_DEPLOYMENT.md, docs/001.11--llm--MIGRATE_TO_FORGE.md

## Context

One droplet (dkStandalone), two humans' worth of users (`alvar` deploys, `koan` runs the app), one git
worktree, and a set of generated artifacts that must never enter the public repo. A keys-in-git incident
(2026-11-15: 1651 tracked files, of which ~1600 were a committed venv, plus a burned VAPID pair in public
history) forced explicit rules about what lives where.

## Decision

**Users and ownership:**

- `alvar` — the deploy human. SSH key-only, sudo with password. Runs `git`, `systemctl`, `nginx`.
- `koan` — faceless system user (`/bin/false`, no password, no login). Owns the app tree and runs
  gunicorn + the push sender. Deploy operations in the tree go through `sudo -u koan ...`.
- Nothing in the app tree is root-owned; root SSH is emergency-only (001.2 2.2).

**Droplet layout (accepted):**

```
/opt/dailykoan/              # git worktree, owned by koan:koan
├── app.py                   # Flask app
├── push_sender.py           # timer-run sender
├── koans.json               # source data (load-bearing order — indices into it are stored)
├── templates/index.html     # Jinja template
├── static/                  # manifest.json, sw.js, generated icon-*.png / badge-72.png
├── venv/                    # virtualenv (gitignored)
├── subscriptions.db         # SQLite (gitignored)
├── vapid_private.pem        # 0600 (gitignored, irreplaceable — see data-model ADR)
└── vapid_public.pem         # (gitignored)
/etc/systemd/system/dailykoan.service          # gunicorn unit
/etc/systemd/system/dailykoan-push.service     # oneshot sender unit
/etc/systemd/system/dailykoan-push.timer      # 08:00 UTC schedule
/etc/nginx/sites-available/koan → sites-enabled/koan   # full server block, no Forge on this box
```

**The load-bearing rule — generated state must survive deploys:** the venv, the key pair, the DB, and
generated icons are *not in git* (`.gitignore`: `venv/`, `*.pem`, `subscriptions.db`, `.hypa/`, `.tmp/`).
On dkStandalone they live inside the worktree, which is acceptable only because deploys are manual
`sudo -u koan git pull` — nothing ever resets the tree. The Forge path (001.11) cannot assume that:
Forge deployments reset `current/`, so the standard there is venv *outside* the deploy tree
(`~/<site>/venv`), with keys and DB migrating in explicitly. That asymmetry is deliberate, not drift.

**Git operations:** the worktree is owned by `koan`, so `alvar` pulling directly hits git's
multi-user protection ("detected dubious ownership") — pulls go through `sudo -u koan git pull`, which
is also what 001.2 9.2 ships. This is the documented recovery for that exact live failure.

**Logs:** app and sender output go to the systemd journal (`journalctl -u dailykoan` / `-u
dailykoan-push.service`; alvar needs `sudo` because the units run as koan). nginx access/error logs in
`/var/log/nginx/` — the access log is the ground truth for subscribe POSTs (gunicorn's journal shows
errors only, a live debugging lesson).

**Backups:** DB snapshots via `sqlite3 .backup` (never a raw `cp` of a live DB — corruption risk);
the VAPID pair must exist off-droplet (001.2 9.3; flagged housekeeping, droplet loss without it equals
total re-subscribe event).

## Consequences

- Two-file mental model: everything replaceable is in git; everything not is in four paths + one file.
- `git clean` / hard resets are forbidden on the droplet until the state files move out of the tree.
- The public repo never carries secrets; burned pairs get regenerated locally (rotation policy in
  data-model ADR), history stays dirty-but-harmless.
