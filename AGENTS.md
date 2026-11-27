# Agent Instructions — DailyKoanPWA

## Testing modes (Alvar's rule, 2026-11-17)

Every change is classified into one of two modes **before finishing a task**:

- **Mode 1 — needs remote testing on iPhone**: changes observable only on the device
  (push payloads, PWA install behavior, night mode, notification UX, anything requiring
  the deployed HTTPS app). Unless Alvar states otherwise: document the change
  (CHANGELOG/docs), commit, and push without further prompting. Then prompt Alvar with
  the deploy + on-phone test checklist (runbook 9.2).
- **Mode 2 — testable locally**: backend logic, template rendering, anything covered by
  the unit suite (`venv/bin/python -m unittest discover -s tests`). Run the suite, then
  prompt Alvar to approve the commit. Do not commit or push unprompted.

## Standing repo rules

- Never commit: `*.pem` (VAPID keys), `subscriptions.db`, `venv/`, `.tmp/` — gitignored, verify before staging.
- Conventional commits: brief, no emoji, no attribution.
- Specs/docs under `docs/` follow `NN--llm|usr--*.md` naming; status files updated on completion.
- Whenever you push or ask Alvar to push, explicitly remind him: **Git push does not deploy this droplet.** Give the manual deploy command below and state whether deployment was verified. If the change migrates SQLite settings, remind him to back up the database first. For PWA changes, verify the live worker version before asking him to test on iPhone.
- Deploy is manual and runs on the droplet (`ssh ubuntu-s-1vcpu-512mb-10gb-nyc1` as `alvar`, sudo passworded): `sudo -u koan git -C /opt/dailykoan pull && sudo systemctl restart dailykoan` (runbook 9.2, note: runbook paths pre-dating 2026-11-24 may say `dkStandalone`/`/home/koan` — the verified app root is `/opt/dailykoan/`); migrations run at startup. Read the DB with `sudo -u koan sqlite3 /opt/dailykoan/subscriptions.db`; read the push journal with `sudo journalctl -u dailykoan-push.service --since=-96h --no-pager` (single-line commands only — multi-line pastes shred over ssh).
- When a milestone is verified, remind Alvar to preserve the known-good commit and start the next change on a new branch so rollback has a clear target.
