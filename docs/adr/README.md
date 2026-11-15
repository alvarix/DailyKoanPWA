# Architecture Decision Records — Index

ADRs record *why*, not *how* — the runbooks (001.x, 002) carry the how. Status markers:
Accepted = shipped and live; Proposed = designed (often peer-reviewed) but deliberately not executed.

| ADR | Status | Records |
| --- | --- | --- |
| [deployment.md](deployment.md) | Accepted | Isolated droplet over Forge (failure-domain isolation after the 2026-10-24 postmortem); DuckDNS provider domain over IP-names; stack shape; hard gates |
| [data-model.md](data-model.md) | Accepted / Proposed | SQLite-at-$0 schema; subscriptions retention policy (404/410 only); settings key-value table (002); VAPID pair as irreplaceable state |
| [filesystem.md](filesystem.md) | Accepted / Proposed | Users (`alvar`/`koan`) and ownership; `/opt/dailykoan` layout; generated state vs git; dubious-ownership pulls; log locations; backup rules |
| [frontend.md](frontend.md) | Accepted / Proposed | Zero build step (CDN Tailwind/Alpine/HTMX); server-rendered page + Alpine islands; native `<details>`; SW strategy; PWA/iOS constraints |
| [push-pipeline.md](push-pipeline.md) | Accepted / Proposed | Timer as the only push mechanism (no handler broadcasts); run-time state reads; retention tri-state; VAPID single-pair policy; payload shape |

Related documents outside this directory: deployment runbooks (`docs/001.2`, migration plan `docs/001.11`),
tweaks spec (`docs/002--llm--TWEAKS.md`), the nginx postmortem that started the isolation decision
(`docs/001.1--llm--FORGE_DEPLOYMENT.md`).