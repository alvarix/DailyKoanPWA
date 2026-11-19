# Daily Koan PWA — File Map (Doc 000)

Version: 000 — llm
Status: CURRENT as of 0.1.6 (2026-11-17)
Related: docs/adr/ (the *why*), docs/002--llm--TWEAKS.md (the 0.1.6 change set), docs/003--llm--KOAN_PROGRESSION.md (what comes next)

Purpose: one glance at the load-bearing files. Everything else is support and stays plain text at the bottom — the diagrams stay simple. Mermaid renders natively on GitHub; locally use a VS Code Mermaid extension or paste into mermaid.live.

## 1. Runtime — who talks to whom

```mermaid
flowchart TD
    subgraph phone["Phone / browser"]
        direction TB
        Page["templates/index.html<br/>drawer · theme · buttons"]
        SW["static/sw.js<br/>push handler · offline cache"]
    end

    subgraph box["dkStandalone (gunicorn, user koan)"]
        direction TB
        APP["app.py<br/>Flask routes"]
        SEL["koan_selector.py<br/>selection + settings — ONE definition,<br/>both processes import it"]
        DB[("subscriptions.db<br/>settings + subscriptions")]
        DATA["koans.json<br/>14 koans · group / order / id"]
    end

    TIMER["dailykoan-push.timer<br/>hourly tick"]
    SEND["push_sender.py"]
    RELAY["Web Push endpoints<br/>Apple · Google"]

    Page -->|"GET / · /koan/N"| APP
    Page -->|"POST /api/next · mode · settings<br/>subscribe · unsubscribe"| APP
    APP --> SEL
    SEL --> DATA
    SEL <--> DB
    TIMER --> SEND
    SEND --> SEL
    SEND -->|"send loop"| RELAY
    RELAY -->|"push reaches phone"| SW
    SW -.->|"cache fallback"| Page
```

Read it top to bottom — request path first, push path second. The page asks `app.py` for koans and posts setting changes; `app.py` never touches state directly — `koan_selector.py` is the only reader/writer of `koans.json` and the DB. Then, every hour, the timer fires `push_sender.py`, which reuses the *same* selector — so the web app and the push can never disagree on which koan is current.

## 2. One decision, made fresh every run

The point of `koan_selector.py`: mode and delivery schedule are data, so no decision is ever remembered between runs. The hourly run asks three questions in order:

```mermaid
flowchart TD
    RUN(("push_sender run<br/>every hour")) --> READ["read settings<br/>via koan_selector"]
    READ --> GATE{"local time >= push_time?<br/>(push_timezone, DST-correct)"}
    GATE -->|"no — before the<br/>delivery moment"| QUIET["exit — journaled:<br/>before the moment"]
    GATE -->|"yes"| DEDUPE{"last_push_date ==<br/>local today?"}
    DEDUPE -->|"yes — already<br/>delivered today"| QUIET
    DEDUPE -->|"no"| MODE{"mode"}
    MODE -->|"daily"| DATE["daily_index()<br/>sha256(UTC date) % N"]
    MODE -->|"held"| PTR["current_index()<br/>global pointer — RE-ANNOUNCED<br/>every day until Next"]
    DATE --> LOOP["send loop<br/>only 404/410 deletes,<br/>other errors kept"]
    PTR --> LOOP
    LOOP --> MARK["mark_pushed()<br/>local date"]
```

`GET /` answers with the same two branches (daily shows today's hash koan; held shows the pointer). `POST /api/next` calls `advance()` — `BEGIN IMMEDIATE`, atomic `+1` with wrap — and 409s in daily mode, where the pointer is meaningless.

## 3. Support files (deliberately off the diagrams)

| File | What it is |
| --- | --- |
| `init_db.py` | creates the schema + seeds settings (idempotent; app startup does the same, so this is belt-and-suspenders) |
| `init_vapid.py` | generates `vapid_*.pem` — gitignored, irreplaceable (data-model ADR: rotation = re-subscribe event) |
| `init_icons.py` | placeholder PWA icon generator |
| `mockup.html` | static design reference — lags 0.1.6; the template is the source of truth |
| `tests/` | 56 unit tests — delivery gate, selection state, routes, payload truncate |
| `requirements.txt` · `pyproject.toml` | deps; ruff targets `py39` (the venv runs 3.9.6) |
| `static/manifest.json` | PWA manifest |
| `docs/` + `AGENTS.md` | specs, deploy runbook (001.2), ADRs, this map; agent workflow rules |

Reading order for a fresh session: `koan_selector.py` → `app.py` → `templates/index.html` → `push_sender.py`. That is the whole machine; the table above is everything that only helps build it.