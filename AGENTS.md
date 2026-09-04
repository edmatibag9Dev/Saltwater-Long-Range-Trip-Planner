# Agent Behavior Rules — GitHub Operations
# Ed Matibag — Global AI Agent Standards
# Location: ~/Documents/Claude/AGENTS.md
# Last updated: 2026-06-02

---

## Purpose

These rules govern how Claude (and any AI agent) must behave when working with Ed's GitHub repositories. They exist to prevent incomplete commits, stub READMEs, broken pushes, and loss of context between sessions.

---

## File map

Ground truth: `git -C /Users/edmatibag/Documents/Claude/ringer-jobs/agents-fix-swarm/repos/Saltwater-Long-Range-Trip-Planner ls-files`. Every backticked path below is a real tracked path in that output.

| Path | Committed? | Purpose |
|------|------------|---------|
| `saltwater_trip_planner.html` | yes | The entire dashboard — single self-contained HTML file with all CSS/JS inline. Three tabs: Trip Finder (aggregates trips across 11 San Diego long-range boats), Processing Planner (derives boat returns per day from departure + trip length), and Processing Calculator (estimates/compares fish-processing cost between Fisherman's Processing and Five Star). Long-range trip data lives in the inline `RAW` JS array; multi-day boat rows live in the auto-generated `MULTI` block between `// ══ MULTI-DAY DATA START/END` markers (written by `refresh_multiday.py`, never hand-edited); in-memory state only, no localStorage. Opens via `file://` with no build step. |
| `index.html` | yes | GitHub Pages entry point: a meta-refresh redirect to `saltwater_trip_planner.html` so the bare Pages URL opens the dashboard. No content of its own. |
| `Saltwater_Fish_Processing_Calculator_v2.xlsx` | yes | Standalone spreadsheet version of the Fish Processing Calculator — the offline/reference model the in-dashboard Processing Calculator tab is derived from (species-based catch input, per-processor rates, card fees, value-added eligibility). Kept in-repo so the rate logic is auditable outside the HTML. |
| `test-multiday.js` | yes | jsdom integration test for the multi-day Processing Planner. Run with `node test-multiday.js` from the repo root (jsdom resolves from the Cowork project folder's `node_modules`). Must pass before any commit that touches the dashboard or `data/`. |
| `refresh_multiday.py` | yes | Headless refresh of multi-day boat schedules from the four SD landings (FL/SF/PL paged HTML, H&M JSONP). Applies the 1.5-day / 5–10 AM / no-long-range rules, fills capacity, writes `data/`, rewrites the MULTI-DAY block between marker comments in the dashboard. Never touches git. |
| `tests/test_refresh_multiday.py`, `tests/fixtures/` | yes | Offline tests + saved pages (2026-09-03) for the refresh script. Run before every data commit. |
| `data/` | yes (except `data/hold/`) | Audit outputs of the refresh: kept CSV, raw CSV, capacity table, per-source status, last-run summary, run log. `data/hold/` is gitignored. |
| `.gitignore` | yes | Ignores `data/hold/`, Python caches, `.DS_Store`, `node_modules/`. |
| `README.md` | yes | Human quickstart — overview, features, usage, data sources, refresh instructions, "Files" table, and "Last updated" date. The 9-section README per `~/Documents/Claude/CONTRIBUTING.md`, ≥ 400 words. |
| `CHANGELOG.md` | yes | Version history in Keep a Changelog format, newest first (`### Added / Changed / Fixed / Removed`). Documents the Processing Calculator addition and the Teal-Sage rebrand, among other changes. |
| `CONTRIBUTING.md` | yes | Commit + README standard pushed from `~/Documents/Claude/CONTRIBUTING.md`. Defines `feat`/`fix`/`data` commit body rules (≥ 3 bullets) and the 9-section README requirement. |
| `llms.txt` | yes | Machine-readable index of the repo's docs — plain-English summary, "Start here" links, the dashboard entry, and the key invariants (self-contained HTML, snapshot data freshness, scraping workaround, Contents-API SHA-first rule). |
| `AGENTS.md` | yes | This file — the canonical agent entry point for GitHub operations in this repo (bootstrap check, commit standards, Contents API protocol, data-freshness disclosure, scraping protocol, repo inventory, self-contained-deliverable rules, session continuity, never-do list, and the File map above). |

> ℹ️ No `.gitignore`, `BUILD-PLAN.md`, `SPEC-*.md`, `SCHEDULE.md`, or `CLAUDE.md` are tracked in this
> repo today. If generated output or real/personal data is added later, add a `.gitignore` (per
> `~/Documents/Claude/REPO-STANDARD.md`) and mark gitignored paths `no (gitignored)` here with why.

---

## Rule 1 — Repo Bootstrap Check

**At the start of any task involving a GitHub repository:**

1. List the repo contents via `GET /repos/{owner}/{repo}/contents/`
2. Check for `CONTRIBUTING.md` and `AGENTS.md`
3. If either file is missing — push the canonical version from `~/Documents/Claude/` **before doing anything else**
4. Read both files completely before writing any code, committing anything, or modifying the README

> Do not skip this check even if you are confident the files exist. Always verify.

---

## Rule 2 — Commit Standards

Follow `~/Documents/Claude/CONTRIBUTING.md` exactly. Summary:

- All `feat`, `fix`, `data` commits require a body with ≥ 3 bullets
- No one-liner commits — ever
- Subject line: imperative mood, max 72 chars
- Body: specific bullets describing what changed, why, and any caveats

---

## Rule 3 — README on Every Feature Commit

Every `feat`, `fix`, or `data` commit must update the README. The README must:

- Have all 9 required sections (see CONTRIBUTING.md)
- Be ≥ 400 words
- Include updated data source links, feature descriptions, and usage instructions
- Never be a stub

---

## Rule 4 — GitHub Contents API Protocol

In sandbox environments where `git clone` is blocked, use the GitHub Contents API.

**Always follow this sequence for updates:**
1. `GET /repos/{owner}/{repo}/contents/{path}` — retrieve current SHA
2. `PUT` with `{ message, content (base64), sha }` — push update

Skipping the GET will cause a **409 Conflict**. This is a known failure mode — always GET first.

**Token handling:**
- Ed provides the PAT each session — do not store it in any file or memory
- Verify token has Contents: Read & Write permission if a 403 is returned
- Use `GET /user` to confirm the authenticated username before any push

---

## Rule 5 — Data Freshness Disclosure

When the dashboard or tool contains scraped or snapshot data:

- Always include a data freshness note in the README
- Always include a visible disclaimer in the UI
- Always link to the live source so the user can verify current data
- Document the scraping method and any known blockers (e.g. CAPTCHA)

---

## Rule 6 — Scraping Protocol (fishingreservations.net)

Specific to Ed's saltwater fishing tools:

- `fishingreservations.net` blocks rapid sequential automated requests (CAPTCHA error 338)
- **Workaround:** Ed opens all boat URLs in browser tabs manually, then Claude reads via the Claude in Chrome MCP extension
- Shogun typically loads clean on the first automated request before blocking kicks in
- Red Rooster III (`redrooster3.com`) scrapes cleanly — different domain, no CAPTCHA
- The four **landing** schedule pages load headlessly with plain `curl` and a browser User-Agent at 1.5 s spacing (verified 2026-09-03, ~55 requests, no CAPTCHA): Fisherman's `/resos/?page=N`, Seaforth `/sales/?page=N`, Point Loma `schedules.php?page=N`, and H&M's JSONP feed `hmlanding.com/xolacache?callback=JSON_CALLBACK`. `refresh_multiday.py` owns this; a `<title>Validation request` response is the CAPTCHA page and is treated as a failed fetch
- Searcher and Intrepid's own booking pages DO CAPTCHA headlessly — they follow the long-range Chrome workaround

---

## Rule 7 — Ed's Repo Inventory

| Repo | Purpose | Key File |
|------|---------|---------|
| `Saltwater-Long-Range-Trip-Planner` | Trip finder + fish processing planner (11 long-range boats + multi-day boats from 4 landings) | `saltwater_trip_planner.html`, `refresh_multiday.py` |
| `ai-task-manager` | AI-powered task management app | Next.js app |
| `Wiki-Page-from-Open-Brain` | Wiki generator from Open Brain thoughts | `open-brain-wiki.html` |

GitHub username: `edmatibag9Dev`

---

## Rule 8 — Self-Contained Deliverables

When building HTML dashboards or tools:

- Single file — all CSS and JS inline, no external dependencies
- Must open directly in browser (`file://`) with no build step
- No localStorage — use in-memory JS state
- All data links open in new tab
- Include a visible "data as of [date]" disclaimer when showing snapshot data — two stamps: long-range (manual refresh) and multi-day (weekly auto refresh, amber when any landing is older than 14 days)
- Long-range rows derive return dates from departure + trip length. Multi-day rows store the return date and time as posted by the landing (fractional trip lengths, explicit return times) — this is the one sanctioned exception to the derive-don't-store rule

---

## Rule 9 — Session Continuity

At the start of any session involving a known project:

1. Read `~/Documents/Claude/CONTRIBUTING.md` and `AGENTS.md`
2. Check memory for project context (`project_saltwater_planner.md` etc.)
3. Check the repo for current file state before making changes
4. Never assume the previous session's work is still current — verify by reading files

---

## Rule 10 — Never Do These

- ❌ Push a stub or placeholder README
- ❌ Write a one-liner commit message on a feat/fix/data commit
- ❌ Update an existing GitHub file without getting its SHA first
- ❌ Store Ed's PAT in any file, memory, or log
- ❌ Assume git clone will work in a sandbox — use the Contents API
- ❌ Skip the CONTRIBUTING.md / AGENTS.md bootstrap check
- ❌ Leave a dashboard without a data freshness disclaimer
