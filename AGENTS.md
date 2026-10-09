# AGENTS.md — guide for AI agents working in this repo
> Standard: REPO-STANDARD 2026-10-09 · Commits, README and staging: CONTRIBUTING.md

This file is the canonical entry point for any AI agent (Claude Code, Cowork, Codex, etc.)
asked to **use, reference, extend, or rebuild** this project. Read it before acting.

## What this repo is

A self-contained HTML dashboard for planning long-range saltwater fishing trips out of San Diego
(Trip Finder across 11 long-range boats) and for planning fish processing around boat returns
(Processing Planner, which also counts multi-day boats from the four San Diego landings, and a
Processing Calculator comparing two processors). It is published on GitHub Pages and refreshed
weekly by a scheduled task on Ed's Mac.

Design in one line: **manual long-range `RAW` array + weekly headless `refresh_multiday.py` → one
self-contained `saltwater_trip_planner.html` (opens over `file://`) → `git push` republishes Pages.**

## File map

Ground truth: `git ls-files` in this clone. Every backticked path below is a real tracked path in that output, unless it is marked gitignored.

| Path | Committed? | Purpose |
|------|------------|---------|
| `saltwater_trip_planner.html` | yes | The entire dashboard — single self-contained HTML file with all CSS/JS inline. Three tabs: Trip Finder (aggregates trips across 11 San Diego long-range boats), Processing Planner (derives boat returns per day from departure + trip length), and Processing Calculator (estimates/compares fish-processing cost between Fisherman's Processing and Five Star). Long-range trip data lives in the inline `RAW` JS array; multi-day boat rows live in the auto-generated `MULTI` block between `// ══ MULTI-DAY DATA START/END` markers (written by `refresh_multiday.py`, never hand-edited); in-memory state only, no localStorage. Opens via `file://` with no build step. |
| `index.html` | yes | GitHub Pages entry point: a meta-refresh redirect to `saltwater_trip_planner.html` so the bare Pages URL opens the dashboard. No content of its own. |
| `Saltwater_Fish_Processing_Calculator_v2.xlsx` | yes | Standalone spreadsheet version of the Fish Processing Calculator — the offline/reference model the in-dashboard Processing Calculator tab is derived from (species-based catch input, per-processor rates, card fees, value-added eligibility). Kept in-repo so the rate logic is auditable outside the HTML. |
| `test-multiday.js` | yes | jsdom integration test for the multi-day Processing Planner. Run with `node test-multiday.js` from the repo root, or `npm test` from the Cowork project folder. jsdom resolves from that folder's `node_modules` — see "Node dependencies" below. Must pass before any commit that touches the dashboard or `data/`. |
| `refresh_multiday.py` | yes | Headless refresh of multi-day boat schedules from the four SD landings (FL/SF/PL paged HTML, H&M JSONP). Applies the 1.5-day / 5–10 AM / no-long-range rules, fills capacity, writes `data/`, rewrites the MULTI-DAY block between marker comments in the dashboard. Never touches git. |
| `tests/test_refresh_multiday.py`, `tests/fixtures/` | yes | Offline tests + saved pages (2026-09-03) for the refresh script. Run before every data commit. |
| `data/` | yes (except `data/hold/` and `data/last-success`) | Audit outputs of the refresh: kept CSV, raw CSV, capacity table, per-source status, last-run summary, run log. |
| `data/hold/` | **no (gitignored)** | Scratch CSV written when a refresh is held (row collapse below 60 %); never published. |
| `data/last-success` | **no (gitignored)** | Empty stamp touched after a verified push; the fleet watchdog reads its mtime. Machine-local state. |
| `.gitignore` | yes | Ignores `data/hold/`, `data/last-success`, Python caches, `.DS_Store`, `node_modules/`, secrets and local-only config (`.env*`, `CONFIG.local.md`), `.venv/`, `*.bak*`. |
| `BUILD-PLAN.md` | yes | The 2026-09-03 build plan for multi-day boats in the Processing Planner: problem and 8/28 calibration, Ed's decisions, data sources, design, refresh pipeline, the scheduled task, alerts and safety nets (§10), phase gates with results. Read this before touching the planner or the refresh. |
| `README.md` | yes | Human quickstart — the nine sections per `CONTRIBUTING.md` (overview, purpose, features, file descriptions, how to use incl. refresh instructions, data sources, limitations, workarounds, build notes) and the "Last updated" date. |
| `CHANGELOG.md` | yes | Version history in Keep a Changelog format, newest first (`### Added / Changed / Fixed / Removed`). Documents the Processing Calculator addition and the Teal-Sage rebrand, among other changes. |
| `CONTRIBUTING.md` | yes | Verbatim copy of `~/.claude/CONTRIBUTING.md`: commit format, the 9-section README requirement, staging rules. |
| `llms.txt` | yes | Machine-readable index of the repo's docs — plain-English summary, "Start here" links, the dashboard entry, and the key invariants. |
| `AGENTS.md` | yes | This file — the canonical agent entry point for this repo. |

> ℹ️ No `SPEC-*.md`, `SCHEDULE.md`, or `CLAUDE.md` are tracked in this repo today. `.gitignore` and
> `BUILD-PLAN.md` are — both appear in the File map above. If generated output or real/personal data
> is added later, extend `.gitignore` (per `~/.claude/REPO-STANDARD.md` §8) and mark gitignored
> paths `no (gitignored)` here with why.

## The data contract (`RAW`, the `MULTI` block, `data/`)

Three interfaces, all inside this repo:

```
// saltwater_trip_planner.html — long-range rows (hand-maintained)
// [boatIdx, name, deptDate, days, capacity, spots, price, flags]
[0,'Open 3-Day',           '2026-06-02',3,25,1,   '$1,580',[]],
// spots: -2 in progress · -1 charter/private · 0 wait list · 1–3 low · 4+ open · flag 'ed' = Ed's trip

// ══ MULTI-DAY DATA START (auto-generated by refresh_multiday.py — do not hand-edit) ══
const MULTI_AS_OF = '2026-10-04';
const MULTI_SOURCES = {"FL":{"label":"Fisherman's Landing","as_of":"2026-10-04","status":"ok"}, ...};
// [landing, boat, tripType, days, deptDate, deptTime, retDate, retTime, cap, spots]
const MULTI = [ ... ];
// ══ MULTI-DAY DATA END ══
```

```
data/multiday_trips.csv header:
landing,boat,ttype,days,dep,deptime,ret,rettime,cap,cap_source,spots,price,src

data/last_run.json keys: digest, dry_run, html_written, outcome, per_landing{FL,HM,PL,SF},
  prev_rows_kept, rows_carried, rows_kept, rows_raw, ts
outcome words: landed · already-landed · partial · hold · failed
refresh_multiday.py exit codes: 0 landed / already-landed · 2 partial · 3 hold · 4 failed
```

Rules an agent must preserve:
- Only `refresh_multiday.py` writes between the `MULTI-DAY DATA START/END` markers. Never hand-edit them; fix the script and its tests instead.
- Long-range rows derive return dates from departure + trip length. Multi-day rows store the return date and time as posted by the landing — the one sanctioned exception to derive-don't-store.
- The refresh never touches `RAW` or `BOATS`; those stay manual (Rule 6 Chrome-tab workaround).
- The dashboard stays a single self-contained file with two visible freshness stamps (see "Repo-specific additions" below).
- The scheduled task depends on `data/last_run.json`, the exit codes and the outcome words above, and `data/last-success`. Change them only together with the task's SKILL.md and `BUILD-PLAN.md` §10.3.

## How it works

1. **View (any browser).** `index.html` redirects to `saltwater_trip_planner.html`, which renders all three tabs client-side from `RAW` and `MULTI`. No server, no build step; GitHub Pages serves `main` at the repo root.
2. **Long-range refresh (manual, native Mac + Claude in Chrome).** Ed opens the boat reservation pages in browser tabs; Claude reads them through the Chrome extension and updates `RAW` (Rule 6). Committed as a `data` commit.
3. **Multi-day refresh (scheduled, native Mac).** Every Sunday the `saltwater-multiday-refresh` task runs `refresh_multiday.py`, both test suites, an explicitly staged `data(multiday)` commit and a native `git push` (Rule 11).
4. **Tests (native).** `node test-multiday.js` (jsdom from the parent folder's `node_modules`) and `python3 tests/test_refresh_multiday.py` (offline fixtures).
5. **Publish.** A push to `main` republishes GitHub Pages.

## How to extend

- **Add or refresh long-range trips:** edit the `RAW` array in `saltwater_trip_planner.html`; new months appear in both tabs automatically. Update the long-range "data as of" stamp and the README data-coverage line.
- **Flag your own trip:** add `'ed'` to the flags array of that `RAW` row.
- **Change the multi-day rules (trip length, return window, landings):** edit `refresh_multiday.py` and `tests/test_refresh_multiday.py` (add fixtures under `tests/fixtures/`); never edit the `MULTI` block.
- **Change processing rates or value-added rules:** edit the Processing Calculator tab in the HTML and keep `Saltwater_Fish_Processing_Calculator_v2.xlsx` in step; the Catch Logger's `engine.js` is the canonical implementation of these cost rules (README "How to Use").
- **Add a Node test dependency:** add it to `package.json` in the parent Cowork folder and run a plain `npm install` there (see "Node dependencies" below). Never add a `package.json` here.

## Privacy — hard rules

- This repo is **public**. Never commit secrets, tokens or the PAT (Rule 4 below), or `.env*` / `CONFIG.local.md`.
- Never add an email address, Slack workspace or channel ID, or account number. If one is ever needed, use a placeholder (`<ALERT_EMAIL>`, `<SLACK_CHANNEL_ID>`) and keep the real value in the gitignored `CONFIG.local.md` (REPO-STANDARD §8).
- `data/hold/` and `data/last-success` stay gitignored.

## Verification gates

Run before declaring a change done:

1. `node test-multiday.js` passes — required before any commit that touches the dashboard or `data/` (needs `npm install` in the parent folder first).
2. `python3 tests/test_refresh_multiday.py` passes — required before every data commit and any change to `refresh_multiday.py`.
3. Open `saltwater_trip_planner.html` over `file://`: all three tabs render and both freshness stamps show.
4. `git status --short` shows only files you meant to change, plus at most `data/refresh.log`, `data/hold/`, `data/last-success` — otherwise the Sunday preflight aborts with `dirty-tree`.
5. `python3 ~/.claude/skills/repo-standard/scripts/repo-check.py .` reports no FAIL lines.

---

## GitHub operations — generic rules live in GITHUB-OPERATIONS.md

The generic rules this file used to carry (bootstrap check, commit standards, README on every
feature commit, push workflow and Contents-API protocol, data-freshness disclosure, repo inventory,
self-contained deliverables, session continuity, never-do list) are owned by
`~/.claude/GITHUB-OPERATIONS.md` (Rules 1–5 and 7–10), with commits, README and staging owned by
`CONTRIBUTING.md`. Follow those. This repo adds the following on top:

### Repo-specific additions

- **Push (Rule 4; amended 2026-09-04, Ed's decision D7 in BUILD-PLAN.md):** on Ed's Mac, git and `gh` are already logged in as `edmatibag9Dev` — push with plain `git push origin main` from the clone at `~/Documents/Claude/Projects/Build Saltwater Trip Planner/repo/`. No PAT is created, pasted, or stored. The weekly scheduled task pushes this way. The Contents API is only for sandboxes where `git` is unavailable.
- **Self-contained deliverable (Rule 8):** show two "data as of" stamps — long-range (manual refresh) and multi-day (weekly auto refresh, amber when any landing is older than 14 days). Long-range rows derive return dates from departure + trip length; multi-day rows store the return date and time as posted by the landing (fractional trip lengths, explicit return times) — the one sanctioned exception to the derive-don't-store rule.
- **Session continuity (Rule 9):** also read `BUILD-PLAN.md` (this repo) for the multi-day design and its safety nets.
- **Never do (Rule 10):** never hand-edit the `MULTI` block.

---

## Node dependencies — they live one level up, and they are pinned

The dashboard itself has **no runtime dependencies** — `saltwater_trip_planner.html` is self-contained
and opens over `file://` with no build step. That invariant does not change. The Node packages exist
only for the test harness and for tooling that sits outside this repo.

They are declared in `package.json` in the **Cowork project folder**, the parent of this clone:

```
~/Documents/Claude/Projects/Build Saltwater Trip Planner/
├── package.json          ← the manifest + package-lock.json (NOT in this repo)
├── node_modules/
└── repo/                 ← this repository
```

| Package | Why |
|---|---|
| `jsdom` | `test-multiday.js` — the Processing Planner integration test |
| `docx` | Word-document generation for the `trips/` archive scripts, outside this repo |

**Never add a `package.json` to this repo.** It would imply a build step the dashboard does not have,
and `node_modules/` is gitignored here precisely because the dependency tree is the parent folder's
concern, not the repository's.

**Install and run from the parent folder:**

```bash
cd ~/Documents/Claude/Projects/Build\ Saltwater\ Trip\ Planner
npm install     # restores both packages from package-lock.json
npm test        # runs repo/test-multiday.js
```

> ⚠️ **Do not run `npm install <pkg> --no-save` in that folder.** With a manifest present npm now
> prunes anything not declared, so a `--no-save` install silently deletes the other package —
> `npm install docx --no-save` removed `jsdom` on 2026-09-04 and broke `test-multiday.js` until it
> was reinstalled. Add the dependency to `package.json` and run a plain `npm install` instead.

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

## Rule 11 — Weekly Multi-Day Refresh (scheduled task)

- Task `saltwater-multiday-refresh` runs Sundays 8:15 AM (plus jitter) on Ed's Mac: `git pull --rebase --autostash` → `python3 refresh_multiday.py` → `node test-multiday.js` + `python3 tests/test_refresh_multiday.py` → explicit staging with a deletion guard → `data(multiday)` commit → push → `touch data/last-success` → one Slack line to #fishing-report-alerts every run → heartbeat row. Full contract in the task's SKILL.md and `BUILD-PLAN.md` §10.
- Only `refresh_multiday.py` writes the `MULTI` block. Never hand-edit between the markers; fix the script and its tests instead.
- The long-range `RAW` array and `BOATS` stay manual (Chrome-tab workaround, Rule 6). The refresh never touches them.
- A stale landing keeps its previous rows; a row collapse below 60 % holds the page; a departed-but-unreturned boat is carried forward. These are in the script, not the prompt — keep them there.
- Interactive sessions must leave the tree clean (only `data/refresh.log`, `data/hold/`, `data/last-success` may differ) or the Sunday preflight aborts with `dirty-tree`.
- Ops coverage: ops-watcher (daily 8:04), fleet-sentinel (Class-1 auto-restart, never on STALLED), launchd fleet watchdog (`data/last-success` mtime). To rerun by hand: `rerun saltwater-multiday-refresh` in #ops-control, or "Run now" in the Scheduled sidebar.
