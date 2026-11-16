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
- Deploy is manual: `sudo -u koan git pull && sudo systemctl restart dailykoan` on dkStandalone (runbook 9.2); migrations run at startup.