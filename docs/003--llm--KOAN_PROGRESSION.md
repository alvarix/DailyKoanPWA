# Daily Koan PWA — Koan Progression Analysis (Doc 003)

Version: 003 — llm
Status: ANALYSIS + PROPOSALS — the mechanics shipped (0.1.6); the corpus fill-out and gate/level model are Phase 2, awaiting Alvar's pick.
Answers the questions raised in docs/002--usr--TWEAKS.md ("create analysis doc 003", "analyze: is the same-koan complexity componentizable?").
Related: docs/002--llm--TWEAKS.md (executed), docs/adr/data-model.md, docs/adr/push-pipeline.md.

---

## 1. The problem

Phase 1 pulled a *random* koan from a flat list. But koans are not a flat list: they live inside canonical texts, each text has an internal case order, and the texts themselves have a traditional reading order. "Next Koan" should mean *the next case in the tradition*, not "roll dice" — with random as an explicit mode, not the default. (002 shipped exactly that inversion: ordered is the default, random is a choice.)

## 2. Research: the three seminal texts

| Text | Cases | Author | Character | Role in progression |
| --- | --- | --- | --- | --- |
| **Mumonkan** (Gateless Gate / Wumen Guan) | 48 | Wumen Huikai (1228) | Short cases, Wumen's own commentary + verse per case | The traditional entry point — short, self-contained, minimal apparatus |
| **Blue Cliff Record** (Piyan Lu) | 100 | Xuedou Chongxian (cases + verses), Yuanwu Keqin (commentary, ~1125) | Longer, layered: case + interlinear notes + Yuanwu's commentary + Xuedou's verse | Second stage — commentary layers add context Mumonkan withholds |
| **Book of Serenity** (Congrong Lu) | 100 | Hongzhi Zhengjue (cases + verses), Wansong Xingxiu (commentary, ~1224) | The most expansive apparatus | Later stage — same shape as BCR, denser |

The common curricular pattern — and the one 002-usr quotes — is: **start with the Mumonkan, then move to the Blue Cliff Record or Book of Serenity**, which add layers of commentary and verse. That gives Phase 1 its spine:

```text
ordered progression = Mumonkan (1..48) → Blue Cliff Record → Book of Serenity → other sources
```

The gate metaphor is native to the material: Mumonkan literally means "the gateless gate" — each case is a gate; passing one is "through the gate" (and Wumen's own verse says the gateless gate is hard to pass). A "Next Koan goes through gates" mechanic is not a gimmick bolted on; it is the text's own self-description.

## 3. What shipped in 0.1.6 (the mechanics)

- `koans.json` carries per-koan metadata: `group` (text), `order` (case number within the text), `id` (stable slug, e.g. `mumonkan-29`).
- `koan_selector.load_koans()` sorts by `(text rank, case order, title)` — the **file order is no longer load-bearing**. Reformatting or re-lining the JSON cannot change what anyone is served.
- `settings.progression` (`ordered` | `random`): ordered advances `+1 % total` (wraps); random jumps to a *different* koan (never a stall). The Random Koan button in the UI is a per-visitor view jump that always ends with "Next" returning to the global order.
- The settings drawer exposes mode (Hold/Daily), order (In order/Random), push time, and night mode.

## 4. Proposals (Phase 2 — awaiting Alvar's pick)

### 4.1 Inter-text progression (`progression: 'inter-text'`)

Ordered-within-text first, then the next text. This is what shipped. The *inter-text* upgrade is: order by a **curriculum position that crosses texts**, e.g. Mumonkan 1-48 as stage 1, then a curated BCR selection as stage 2, BoS as stage 3. Data model:

```jsonc
// per-koan, additive:
{ "group": "Blue Cliff Record", "order": 22, "id": "bcr-22", "stage": 2 }
// settings, additive:
{ "progression": "inter-text" }  // walks (stage, order) instead of (group, order)
```

`stage` is just a coarse integer — the gate/level question (next section) decides whether it stays metadata or becomes load-bearing.

### 4.2 Gates / levels

The honest version of "levels" for this app is **not** a game-like XP system — it is *curriculum position*. Two shapes, in ascending cost:

1. **Linear gates (recommended)**: `stage` per koan (1-3); `current_index` walks `(stage, order)`. "Level" = which text you are in. No unlock logic needed: the order *is* the gate sequence. A settings row could pin progression to a stage (`progression_stage: 1`) for people who want only-Mumonkan days. Cheap: one field, one settings row, sort-key change.
2. **Unlocked branching (not recommended for N=1)**: koans unlock per-visitor; requires per-visitor state (accounts or localStorage), breaks the same-koan-for-everyone property, and the push pipeline has no per-recipient targeting. This is a different product. Reject unless the app grows users who want their own track.

Either way the data model needs **nothing new beyond `stage`** for shape 1 — which is why 4.1 and 4.2 are the same field.

### 4.3 Corpus fill-out (the big one)

Current state: 14 koans — 7 Mumonkan, 4 Blue Cliff Record, 3 other sources. The tradition's full spine:

- **Mumonkan: 48 cases** — fill all 48 (we hold 7). Each case: text, Wumen's commentary, Wumen's verse, in `group: Mumonkan`, `order: case#`.
- **Blue Cliff Record: 100 cases** — fill a curated selection first (BCR is long; 20-40 cases is a realistic stage-2 shelf), full 100 later.
- **Book of Serenity: 100 cases** — same approach; a selection is realistic.

Content risk is the real cost, not the mechanics: koan translations must be checked against standard renderings (Reps, Shibayama, Aitken/Cohen for the Mumonkan; the existing entries are already paraphrase-style "traditional" renderings, so the bar is fidelity of meaning, not a specific copyrighted text). That is a data-entry pass with verification, deliberately **not** done in the same change as the mechanics (this doc + 0.1.6 kept the moving parts separate from content).

### 4.4 `current_index` continuity when the corpus grows

When 14 becomes 48+, positional indices shift. Options:

| Option | Cost | Verdict |
| --- | --- | --- |
| Re-seed pointer on deploy (`current_index = daily seed`) | none — already the migration default | **chosen**: deploy notes say "pointer reseeds" |
| Remap by `id` (store `current_index_id` too) | one more settings row + remap step | Adopt with the fill-out, if mid-Mumonkan continuity matters then |

Bounds-checking already makes any stored pointer safe (clamped by modulo), so continuity is a UX nicety, never a correctness problem.

## 5. Componentization verdict (the 002-usr question)

> "A lot of work went into serving the same koan to all subs. Is that complexity able to be componentized? I'm concerned about potentially unnecessary complexity."

**Yes — and it is done.** Before 0.1.6, koan selection existed twice: `get_todays_koan()` in `app.py` *and* `get_todays_koan()` in `push_sender.py`, which had already drifted (different date plumbing, different error handling). That duplication was the actual unnecessary complexity — the "same koan to everyone" property itself is one deterministic function.

Now all of it lives in `koan_selector.py`, imported by both processes:

| Piece | Where |
| Date-hash selection (`daily_index`) | `koan_selector.py` — one definition |
| Held pointer + clamping (`current_index`) | `koan_selector.py` |
| Atomic advance (`advance`, BEGIN IMMEDIATE) | `koan_selector.py` |
| Mode/progression/push_time writes (`set_values`) | `koan_selector.py` |
| Migration (`ensure_settings`, idempotent, both processes run it) | `koan_selector.py` |
| Push decision + dedupe (`select_push`, `mark_pushed`) | `koan_selector.py` |
| Subscriptions storage | untouched — `app.py` routes + `push_sender.py` send loop, as before |

Residual complexity, honestly accounted: the settings drawer + three new endpoints in `app.py` (UI surface, not selection logic), and the template's Alpine additions. Nothing about *selection* lives in either process anymore. `push_sender.main()` is now ~40 lines of glue: decide → send loop → mark pushed.

The complexity that remains is *wanted*: the same-koan property requires global state somewhere, and a shared module is the smallest place it can live.

## 6. Risks / open items

- **Content accuracy** on the fill-out (4.3) — verification pass required, this doc does not license bulk generation.
- **`current_index` reseed on fill-out deploys** (4.4) — document in the deploy runbook when it happens.
- **Payload growth**: more koans does not change payload size (one koan per push, 3KB cap), but longer BCR cases may hit the cap more often — the truncate guard handles it; watch truncation frequency in the journal.
- **Push time is still one global systemd timer** — the drawer records the preference; rescheduling delivery remains an ops step (`dailykoan-push.timer` OnCalendar), by the push-pipeline ADR's "one mechanism" rule.

## 7. For dummies

Right now the app picks the next teaching from a reading list that follows the classic Zen books, in the order the tradition reads them: first the short "Gateless Gate" stories, then the two big fancy anthologies. The "level" idea is simply *which book you're in* — no points, no locks, just "you're in book one of three". Filling in all the stories from those books is the next big chore, and that chore is about careful typing and checking, not about new machinery. The machinery part is finished, tested, and shared by the website and the phone-alert script so they can never disagree.

## 8. Peer review

This analysis was not run through the plan-review skill (it is a research/proposal doc, not an execution plan). The executed mechanics it describes (0.1.6) were reviewed: gemini-2.5-pro + gpt-5 flagged the WAL-race (→ BEGIN IMMEDIATE), the lying UI risk on push time (→ honest drawer copy), file-order fragility (→ metadata sort), and daily-mode statelessness (→ date-hash only, pointer never read in daily). All folded into 002/koan_selector; see docs/002--llm--TWEAKS.md "Peer Review".