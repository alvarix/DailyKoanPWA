# 005 — Bugs & next steps: push silence, iOS re-add, and the global-sync reversal

Status: FINDINGS RECORDED — reversal spec written: docs/005.1--llm--held-state-fix.md (awaiting Alvar's call on Open Decision 1 + approval; no code yet)
Date: 2026-11-24
Note: requested as `004--llm--bugs-and-next-steps.md`; `004` is taken by android-notifications, so this doc takes `005` per the sequential convention.
Related: docs/002--llm--TWEAKS.md (held-mode design), 002.1 (cadence), 002.2 (title fix), 003 (progression), docs/adr/push-pipeline.md, docs/adr/data-model.md

## 1. Plain English

Three days of quiet mornings had nothing to do with the server. The server sent a koan to Apple every single day and Apple accepted each one — but the phone never displayed them. What broke was the phone's half: the Home Screen app's push registration had silently died, so iOS had nothing to show. Removing and re-adding the app (with a fresh Allow) is what fixed it. We cannot prove from here which iOS event killed the registration; what we can prove is the server was clean the whole time.

The second finding is a real bug, ours: the koan changed every day without anyone (meaning the operator) pressing Next. The reason: "Next Koan" moves ONE global pointer, with no authentication — any visitor to the public URL changes everyone's koan. That global-synced state was never a requested feature. It cascaded from one early decision ("all users see the same koan") into the global held-mode pointer, the push's source koan, and an unauthenticated write endpoint on the open internet. The reversal below removes the global state itself instead of patching around it.

## 2. Findings — notification silence (Nov 21–24)

### Server side — VERIFIED (journal + DB)

| Check | Result |
| --- | --- |
| Hourly timer | Ticked every hour, every day — no gaps |
| Delivery gate | Opened exactly 05:00 America/New_York daily (journal prints local now + push_time) |
| Send | Every day: `Sending to 1 subscription(s)` → `Sent: 1` — Apple accepted |
| Settings rows | Persisted across days (push_time=05:00, timezone, mode=held) — DB was NOT recreated |
| Conclusion | Pipeline performed per spec (0.1.8). Nothing server-side to fix |

### Phone side — OBSERVED

- No visible notification for days, despite `Sent: 1` on the server.
- Settings → Notifications listed **no "Daily Koan" entry** — the OS had nothing registered to display.
- Bell badge showed ON — but the badge reflects the subscription *record*, not OS display permission. (Trap: the badge can lie.)
- Bell off/on toggle did **not** restore the Settings entry.
- **Fix that worked:** remove the Home Screen icon → Safari → Share → Add to Home Screen → open → bell → Allow.
- Pending verification: the next 05:00 send lands on screen.

### Root cause — honest boundary

`Sent: 1` means Apple's web-push endpoint accepted the send. It is **not** proof of display, and the server cannot observe the phone's display state. The specific iOS event that killed the registration is **UNCONFIRMED** — candidates: the PWA was removed/re-added at some point (this resets push permission), an iOS Safari website-data cleanup, or an iOS update. Alvar's note for the record: "the idea that the iPhone's routine would stop notifications seems far-fetched" — agreed; no phone-side mechanism was confirmed, and this doc records the boundary rather than a tidy story: **server clean (proven), phone broken until re-add (observed), which iOS event caused it (unknown).**

### Lesson (candidates for RUN.md / the 006 spec)

- The only end-to-end check of a push is the phone itself.
- Journal `Sent: 1` + no display = phone-side. First check: Settings → Notifications for the app entry.
- A system that can fail silently for days should get a detection path: an in-app "send me a test notification" affordance, and journaling the APNs HTTP status per send (201/202 vs 404/410/429/5xx) so the next death is observable within a day, not discovered by accident.

## 3. Findings — the pointer that moved by itself (a real bug, ours)

Evidence — daily "Koan to push" lines (the pushed index = the global pointer):

| Day | Index | Step |
| --- | --- | --- |
| Nov 20 | 11 (Chao-chou in the Snow) | — |
| Nov 21 | 13 (The Leaking Roof) | +2 |
| Nov 22 | 0 (Two Monks, Two Blinds) | +1 |
| Nov 23 | 0 (Two Monks, Two Blinds) | +0 — no press that day |
| Nov 24 | 1 (Hui-neng's Flag) | +1 |

- The +1 steps are the signature of `POST /api/next` taps. A date-hash reseed would show 7, 8, 7, 1 — not observed. A recreated DB would reset `push_time` — not observed.
- `/api/next` has **no authentication** (a same-origin check blocks other *websites*, not people). Any visitor to `dailykoan.duckdns.org` — a public URL — advances the pointer for every user and changes what the push announces.
- Forensics (optional, still open): `sudo grep "POST /api/next" /var/log/nginx/access.log` identifies the tapper(s) — likely the operator's own debugging, but unconfirmed.

## 4. Design verdict + reversal (Alvar, 2026-11-24; revised after peer review)

### Verdict, recorded

All-users-synced koan state was **never a requested feature**. Its value: some in daily mode (everyone shares "today's koan"); **zero in hold mode**. Its cost: this bug class — a public, unauthenticated write into shared state, plus the held-mode re-announce machinery built on top of it.

### The flaw is the global state, not the missing auth

Patch-first options are rejected:

- **Shared secret on `/api/next`** — rejected: patches the symptom, keeps the unrequested global feature, adds auth machinery to a no-auth personal app.
- **Server-side per-visitor state keyed to the subscription** — rejected (peer review): the subscription↔visitor link is fragile across reinstall/new-phone (the exact failure mode this incident surfaced), and per-visitor state reintroduces write endpoints, which need capability tokens — over-engineering for N=1.

### Reversal direction (for the 006 spec)

Remove ALL server-side progression state:

1. **Hold mode goes client-local.** Next advances only the viewing *device* (localStorage). No server write endpoint exists, so there is nothing for a stranger to move. The failure class disappears instead of being guarded.
2. **Daily mode stays the stateless date-hash.** Read-only; same date yields the same koan everywhere. (Everyone seeing today's same koan in daily mode is inherent to a date hash — it costs nothing and has no write path, so it survives the verdict as-is.)
3. **Push becomes stateless/generic.** With no server-side "current koan," the push body comes from the daily date-hash (or a generic "your koan awaits" + deep link); the app resolves the device's held position on open. **Open decision:** which body.
4. **Migration, not amputation.** One-time, idempotent: on first open, the operator's device seeds its local pointer from the old global `current_index` (11 → wherever the taps dragged it is a separate question). Then the global row, `/api/next`, and global `/api/mode` semantics are removed.

### Does the cross-user sync propagate up into the held bug? Remove it altogether?

Propagation trace — yes, and the trace is the indictment:

| Layer | What synced | Write path? |
| --- | --- | --- |
| daily mode (0.1.0) | date-hash: same date → same koan for everyone | **none** — read-only, stateless |
| held mode (0.1.6) | "same koan for everyone" imported the sync into a POINTER | `POST /api/next` — global, public, unauthenticated |
| push source (0.1.6→0.1.8) | the push must read the same shared pointer (and later re-announce it daily) | inherits the write path's blast radius |

The sync was harmless where it was born: a deterministic date hash has no server state to attack. Held mode could only be synced by making the sync **mutable** — a shared row plus a public endpoint to move it. That is the propagation: read-only sharing cascaded into mutable shared state, and mutable shared state is the bug. The pointer moved 11→13→0→0→1 precisely because sync demands mutability.

Remove it altogether? Split verdict:

- **Daily mode: keep.** The sharing there is inherent to the hash — costs no server state, exposes no write path. Removing it would mean per-visitor daily randomness: value destroyed, no bug class removed.
- **Hold mode: remove.** Zero value (one operator), and its only possible implementation is the mutable global row + public endpoint that caused this incident. The 005.1 spec removes it — the sync stops at the layer where it is free.

### Open decisions (answered in the 005.1 spec — docs/005.1--llm--held-state-fix.md, Alvar's call still needed on #1)

1. Push body in hold mode: date-hash koan text vs generic text + deep link.
2. Mode toggle (`/api/mode`, drawer Hold/Daily): per-device or removed with the server state.
3. What the push dedupe keys become with no `current_index` (per-day date dedupe survives as-is).
4. Health/detection scope: test-notification button + APNs status journaling — queued as a separate small pass after 005.1 (not speced yet).

The 005.1 spec answers 1–3: push = today's date-hash koan (stateless), mode toggle = per-device localStorage, dedupe = per-local-day `last_push_date` unchanged.

## 5. Next steps (user-requested, 2026-11-24)

Separate work items, queued behind (or alongside) the reversal — recorded here per request, speced alongside 005.1:

1. **Where am I in the progression?** If Next is a progression, show the position. `koans.json` already carries `group`/`order`/`id` — render a position indicator (e.g., "Mumonkan · case 26" style) so Next reads as moving through a corpus, not shuffling.
2. **About page in the settings drawer.** Explains the progression methodology (ordered: text → case; daily: date-hash) plus an index of all current koans, each linking to its deep link (`/koan/<idx>` exists). Note for the spec: mark it `noindex` so crawlers don't index the corpus.

### Pending ops (carried)

| Item | How to close |
| --- | --- |
| Verify the re-add fix | Tomorrow's 05:00 send lands on the phone (Mode 1 — on-device check, runbook 9.2) |
| Confirm 0.2.0 deployed | On droplet: `sudo -u koan git -C /opt/dailykoan log --oneline -1` → `0cf56e8`; then on-phone title line shows the koan title, not "Daily Koan"/"From Koan" |
| Next-tapper forensics (optional) | nginx access log grep, above |
| Ubuntu apt upgrade + reboot | Carried from 002.1 item 2 |

## 6. For dummies

The server was mailing a koan to your phone every morning, and your phone's doorman had lost the mailbox. Re-adding the app built a new mailbox. Separately: the website's "Next" button used to move ONE shared bookmark for the whole world — anyone on the internet could move your bookmark. The plan is to make "Next" move only your own copy and delete the shared one entirely.

## 7. Effort (estimate)

- This doc: ~1h (including two-model peer review of the reversal direction).
- 006 spec + reversal implementation + tests + migration: ~one session.
- Position indicator + About page: ~half a session, speced together with 006.

## Peer review

| Item | Status |
| Reviewer models | `google/gemini-2.5-pro` + `openai/gpt-5` (2 of 2 responded, 2026-11-24) |
| Flagged - high (adopted) | "Push follows the operator's per-visitor **server** state" is fragile across reinstall and reintroduces write endpoints needing auth → reversal revised to fully client-local progression + stateless push; silent-failure detection (test notification, APNs status journaling) added to the direction |
| Flagged - medium (adopted) | `Sent: 1` is an attempted-send receipt, not proof of delivery — the doc now words it that way and the detection item follows |
| Flagged - rejected | Locking the two drawer features (position indicator, About page) out of this doc as "scope creep" — they are the user's explicitly requested next steps, kept but marked as separate work items; rate limits/CORS hardening on a to-be-deleted endpoint — moot once the global write path is removed |