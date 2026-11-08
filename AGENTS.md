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

Design in one line: **weekly headless `refresh_multiday.py` writes both trip-data blocks (and
`check_rates.py` reports rate changes without touching anything) → one self-contained
`saltwater_trip_planner.html` (opens over `file://`) → `git push` republishes Pages.**

All three data surfaces are now on the Sunday schedule. Until 2026-11-08 only the multi-day block
was: the long-range `RAW` array was hand-maintained and four months stale, and the processor rates
were stamped "June 2026" with nothing watching them.

## File map

Ground truth: `git ls-files` in this clone. Every backticked path below is a real tracked path in that output, unless it is marked gitignored.

| Path | Committed? | Purpose |
|------|------------|---------|
| `saltwater_trip_planner.html` | yes | The entire dashboard — single self-contained HTML file with all CSS/JS inline. Three tabs: Trip Finder (aggregates trips across 11 San Diego long-range boats), Processing Planner (derives boat returns per day from departure + trip length), and Processing Calculator (estimates/compares fish-processing cost between Fisherman's Processing and Five Star). Long-range trip data lives in the inline `RAW` JS array; multi-day boat rows live in the auto-generated `MULTI` block between `// ══ MULTI-DAY DATA START/END` markers (written by `refresh_multiday.py`, never hand-edited); in-memory state only, no localStorage. Opens via `file://` with no build step. |
| `index.html` | yes | GitHub Pages entry point: a meta-refresh redirect to `saltwater_trip_planner.html` so the bare Pages URL opens the dashboard. No content of its own. |
| `Saltwater_Fish_Processing_Calculator_v2.xlsx` | yes | Standalone spreadsheet version of the Fish Processing Calculator — the offline/reference model the in-dashboard Processing Calculator tab is derived from (species-based catch input, per-processor rates, card fees, value-added eligibility). Kept in-repo so the rate logic is auditable outside the HTML. |
| `test-multiday.js` | yes | jsdom integration test for the multi-day Processing Planner. Run with `node test-multiday.js` from the repo root, or `npm test` from the Cowork project folder. jsdom resolves from that folder's `node_modules` — see "Node dependencies" below. Must pass before any commit that touches the dashboard or `data/`. |
| `refresh_multiday.py` | yes | Headless refresh of **both** trip-data blocks. Multi-day: the four SD landings (FL/SF/PL paged HTML, H&M JSONP), applying the 1.5-day / 5–10 AM / no-long-range rules and filling capacity → the MULTI block. Long-range: all 11 boats' own `/sales/` pages → the `RAW` block, preserving Ed's curation (see Rule 11). Writes `data/`, rewrites both blocks between their marker comments, never touches git. `--skip-longrange` does multi-day only. |
| `check_rates.py` | yes | Compares both fish processors' published **cash** rates to what `PROCESSORS` quotes and writes `data/rates_check.json`. **Reports only — never edits the dashboard** (Rule 11). Exit 0 no change, 2 a rate moved, 4 both pages unreachable. |
| `tests/test_refresh_multiday.py`, `tests/fixtures/` | yes | Offline tests + saved pages for both scripts: the four landings (2026-09-03), three long-range boats and both rate pages (2026-11-08). The boat fixtures are chosen for their quirks — Shogun for the plain grammar and multi-line names, American Angler for charter rows that print a bare `-`, Excel for the `-` name separator and a bare `OPEN`. Run before every data commit. |
| `data/` | yes (except `data/hold/` and `data/last-success`) | Audit outputs of both scripts: multi-day kept + raw CSVs, long-range CSV, capacity table, per-landing and per-boat status, last-run summary, rate-check result, run log. |
| `data/hold/` | **no (gitignored)** | Scratch CSV written when a refresh is held (row collapse below 60 %); never published. |
| `data/last-success` | **no (gitignored)** | Empty stamp touched after a verified push; the fleet watchdog reads its mtime. Machine-local state. |
| `.gitignore` | yes | Ignores `data/hold/`, `data/last-success`, Python caches, `.DS_Store`, `node_modules/`, secrets and local-only config (`.env*`, `CONFIG.local.md`), `.venv/`, `*.bak*`. |
| `BUILD-PLAN.md` | yes | The planner's data-refresh design, in two parts. §1–10: the 2026-09-03 plan for multi-day boats in the Processing Planner — problem and 8/28 calibration, Ed's decisions, data sources, design, refresh pipeline, the scheduled task, alerts and safety nets (§10, with the task's operational contract in §10.3), phase gates with results. §11: the 2026-11-08 extension to the long-range boats and the processor rates — decisions D8–D13, what changed in §10.3's contract, first-run results. Read this before touching the planner or either refresh script. |
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
// ══ LONG-RANGE DATA START (auto-generated by refresh_multiday.py — do not hand-edit) ══
const LR_AS_OF = '2026-11-08';
const LR_SOURCES = [{"label":"Shogun","as_of":"2026-11-08","status":"ok"}, ...];   // one per boat, in BOATS order
// [boatIdx, name, deptDate, days, capacity, spots, price, flags]
[0,'Izorline Sponsored 8-Day','2026-11-06',8,22,-2,'$3,895',[]],
// spots: -2 in progress · -1 charter/private · 0 wait list · 1–3 low · 4+ open
// capacity -1 and price 'Charter' mark a charter · flags: 'invite', 'ed' (= Ed's trip)
const RAW = [ ... ];
// ══ LONG-RANGE DATA END ══

// ══ MULTI-DAY DATA START (auto-generated by refresh_multiday.py — do not hand-edit) ══
const MULTI_AS_OF = '2026-11-08';
const MULTI_SOURCES = {"FL":{"label":"Fisherman's Landing","as_of":"2026-11-08","status":"ok"}, ...};
// [landing, boat, tripType, days, deptDate, deptTime, retDate, retTime, cap, spots]
const MULTI = [ ... ];
// ══ MULTI-DAY DATA END ══
```

`BOATS` sits above the LONG-RANGE block and is **not** generated — `MONTH_LABELS` and
`MONTH_FULL` sit between the two, so one contiguous marker pair cannot hold both.

```
data/multiday_trips.csv header:
landing,boat,ttype,days,dep,deptime,ret,rettime,cap,cap_source,spots,price,src

data/longrange_trips.csv header:
idx,boat,name,dep,days,cap,spots,price,flags,src,note
  src: sales (scraped) · carried (departed, kept from the previous run) · kept (unresolved or stale boat)
  note: why a row was not taken from the page

data/last_run.json keys: ts, outcome (COMBINED — the worse of the two surfaces), dry_run,
  multiday{outcome, digest, rows_kept, rows_carried, rows_raw, prev_rows_kept,
           per_landing{FL,HM,PL,SF}, html_written},
  longrange{outcome, digest, rows_kept, prev_rows_kept, unresolved, dropped_future,
            per_boat{<slug>}, html_written}
  plus every multiday field repeated at the top level, for anything reading the older shape
outcome words (both surfaces): landed · already-landed · partial · hold · failed · skipped
refresh_multiday.py exit codes: 0 landed / already-landed · 2 partial · 3 hold · 4 failed

data/rates_check.json keys: ts, outcome (no-change · changed · failed), rate_date,
  per_processor{fp,fs}{status, http, error, scraped, stored, diffs[{field,stored,scraped}], unreadable[]}
check_rates.py exit codes: 0 no change · 2 a rate moved · 4 both pages unreachable
```

Rules an agent must preserve:
- Only `refresh_multiday.py` writes between the `MULTI-DAY DATA START/END` and `LONG-RANGE DATA START/END` markers. Never hand-edit either; fix the script and its tests instead.
- Long-range rows derive return dates from departure + trip length. Multi-day rows store the return date and time as posted by the landing — the one sanctioned exception to derive-don't-store.
- `BOATS` stays hand-maintained and `boatIdx` indexes it; a test asserts it matches `BOAT_SOURCES` in order.
- A refresh must carry forward everything the boat pages cannot supply: the `'ed'` flag, curated trip names, and departed trips (Rule 11).
- `check_rates.py` never writes to the dashboard. Stored rates are cash figures; the card price is derived by adding `ccFee`.
- The dashboard stays a single self-contained file with two visible freshness stamps (see "Repo-specific additions" below).
- The scheduled task depends on `data/last_run.json`, `data/rates_check.json`, the exit codes and the outcome words above, and `data/last-success`. Change them only together with the task's SKILL.md and `BUILD-PLAN.md` §10.3.

## How it works

1. **View (any browser).** `index.html` redirects to `saltwater_trip_planner.html`, which renders all three tabs client-side from `RAW` and `MULTI`. No server, no build step; GitHub Pages serves `main` at the repo root.
2. **Refresh (scheduled, native Mac).** Every Sunday the `saltwater-multiday-refresh` task runs `refresh_multiday.py` (both blocks), `check_rates.py`, both test suites, an explicitly staged `data(refresh)` commit and a native `git push` (Rule 11). Nothing about the trip data is manual any more.
3. **Rate changes (manual, prompted).** `check_rates.py` tells Ed when a processor's published cash rate moves; he edits `PROCESSORS` himself. The script never does.
4. **Tests (native).** `node test-multiday.js` (jsdom from the parent folder's `node_modules`) and `python3 tests/test_refresh_multiday.py` (offline fixtures).
5. **Publish.** A push to `main` republishes GitHub Pages.

## How to extend

- **Refresh long-range trips:** run `python3 refresh_multiday.py`. Do not hand-edit `RAW` — it is generated, and the next run would overwrite the edit. New months appear in both tabs automatically and the stamp updates itself.
- **Flag your own trip:** add `'ed'` to the flags array of that `RAW` row. The refresh preserves it, keyed on `(boatIdx, deptDate)` — so a trip whose departure date is rescheduled loses the flag and needs it re-added.
- **Fix a trip name the page prints badly:** edit the name in that `RAW` row. The refresh keeps an existing name on a `(boatIdx, deptDate)` match and only takes the page's name for a trip it has not seen before.
- **Add a boat:** add it to `BOATS` in the HTML *and* to `BOAT_SOURCES` in `refresh_multiday.py`, in the same position — `boatIdx` indexes `BOATS`, and a test asserts the two match.
- **Change the multi-day rules (trip length, return window, landings) or the long-range parser/gate:** edit `refresh_multiday.py` and `tests/test_refresh_multiday.py` (add fixtures under `tests/fixtures/`); never edit the `MULTI` or `RAW` blocks.
- **Change processing rates or value-added rules:** edit `PROCESSORS` in the HTML — store the **cash** figure, never a credit-column one, since `calcQuotes` adds `ccFee` on top. Keep `Saltwater_Fish_Processing_Calculator_v2.xlsx` in step and update `RATE_DATE`; the Catch Logger's `engine.js` is the canonical implementation of these cost rules (README "How to Use"). Run `python3 check_rates.py` afterwards — it must report no change.
- **Add a Node test dependency:** add it to `package.json` in the parent Cowork folder and run a plain `npm install` there (see "Node dependencies" below). Never add a `package.json` here.

## Privacy — hard rules

- This repo is **public**. Never commit secrets, tokens or the PAT (Rule 4 below), or `.env*` / `CONFIG.local.md`.
- Never add an email address, Slack workspace or channel ID, or account number. If one is ever needed, use a placeholder (`<ALERT_EMAIL>`, `<SLACK_CHANNEL_ID>`) and keep the real value in the gitignored `CONFIG.local.md` (REPO-STANDARD §8).
- `data/hold/` and `data/last-success` stay gitignored.

## Verification gates

Run before declaring a change done:

1. `node test-multiday.js` passes — required before any commit that touches the dashboard or `data/` (needs `npm install` in the parent folder first).
2. `python3 tests/test_refresh_multiday.py` passes — required before every data commit and any change to `refresh_multiday.py` or `check_rates.py`.
3. `python3 check_rates.py` reports **no change** — required after any edit to `PROCESSORS`. A diff means a stored rate is not the published cash figure.
4. Open `saltwater_trip_planner.html` over `file://`: all three tabs render and both freshness stamps show today's snapshot date, neither amber.
5. `git status --short` shows only files you meant to change, plus at most `data/refresh.log`, `data/hold/`, `data/last-success` — otherwise the Sunday preflight aborts with `dirty-tree`.
6. `python3 ~/.claude/skills/repo-standard/scripts/repo-check.py .` reports no FAIL lines.

---

## GitHub operations — generic rules live in GITHUB-OPERATIONS.md

The generic rules this file used to carry (bootstrap check, commit standards, README on every
feature commit, push workflow and Contents-API protocol, data-freshness disclosure, repo inventory,
self-contained deliverables, session continuity, never-do list) are owned by
`~/.claude/GITHUB-OPERATIONS.md` (Rules 1–5 and 7–10), with commits, README and staging owned by
`CONTRIBUTING.md`. Follow those. This repo adds the following on top:

### Repo-specific additions

- **Push (Rule 4; amended 2026-09-04, Ed's decision D7 in BUILD-PLAN.md):** on Ed's Mac, git and `gh` are already logged in as `edmatibag9Dev` — push with plain `git push origin main` from the clone at `~/Documents/Claude/Projects/Build Saltwater Trip Planner/repo/`. No PAT is created, pasted, or stored. The weekly scheduled task pushes this way. The Contents API is only for sandboxes where `git` is unavailable.
- **Self-contained deliverable (Rule 8):** show two "data as of" stamps, both now weekly auto-refreshed and both amber when any of their sources is older than 14 days or not `ok` — long-range (`#lr-stamp`, per-boat statuses from `LR_SOURCES`) and multi-day (`#multi-stamp`, per-landing statuses from `MULTI_SOURCES`). Long-range rows derive return dates from departure + trip length; multi-day rows store the return date and time as posted by the landing (fractional trip lengths, explicit return times) — the one sanctioned exception to the derive-don't-store rule.
- **Session continuity (Rule 9):** also read `BUILD-PLAN.md` (this repo) — §1–10 for the multi-day design and its safety nets, §11 for the long-range and rate surfaces.
- **Never do (Rule 10):** never hand-edit the `MULTI` or `RAW` blocks; never let `check_rates.py` write to the dashboard; never store a credit-column rate in `PROCESSORS`.

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

Specific to Ed's saltwater fishing tools. **Rewritten 2026-11-08: everything the planner needs
now loads headlessly.** The rule used to say the boat booking pages CAPTCHA automated requests,
so `RAW` was maintained by hand through the Chrome-tab workaround below — and drifted four
months as a result. That claim no longer holds.

- All **15** sources the refresh uses load headlessly with plain `curl`/`urllib` and a browser
  User-Agent at 1.5 s spacing. A `<title>Validation request` response is the CAPTCHA page and is
  treated as a failed fetch:
  - the four **landing** pages (verified 2026-09-03, ~55 requests): Fisherman's `/resos/?page=N`,
    Seaforth `/sales/?page=N`, Point Loma `schedules.php?page=N`, H&M's JSONP feed
    `hmlanding.com/xolacache?callback=JSON_CALLBACK`
  - all **11 long-range boat** pages (verified 2026-11-08, HTTP 200 with full schedule tables):
    `https://<boat>.fishingreservations.net/sales/`. These are the same platform and URL shape as
    the Seaforth and Fisherman's pages, which is why the old blanket claim about the domain was
    wrong. Searcher and Intrepid load too — the 2026-09-03 note that they CAPTCHA is superseded.
    They are single pages, not paged: one page spans Nov 2026 → Jan 2028.
- `refresh_multiday.py` owns every one of them.
- The two **fish processor** rate pages also load headlessly and are read by `check_rates.py`:
  `fishermansprocessing.com` (rate card inline) and `fivestar.net/pricing.php`.
- Red Rooster III (`redrooster3.com`) scrapes cleanly — different domain, no CAPTCHA.
- **Fallback, still valid if the CAPTCHA ever returns:** Ed opens the boat URLs in browser tabs
  and Claude reads them through the Claude in Chrome MCP extension. If a boat starts CAPTCHAing,
  the refresh marks it stale and keeps its previous rows — it does not fail the run — so the
  fallback is a repair path, not part of the weekly job. Re-verify before assuming it is needed:
  `curl -s -o /dev/null -w '%{http_code}' -A '<browser UA>' https://shogun.fishingreservations.net/sales/`

---

## Rule 11 — Weekly Refresh (scheduled task)

- Task `saltwater-multiday-refresh` (shown as "Saltwater Trip Planner refresh") runs Sunday mornings on Ed's Mac — see the fire-time note at the end of this rule for the actual clock time: `git pull --rebase --autostash` → `python3 refresh_multiday.py` → `python3 check_rates.py` → `node test-multiday.js` + `python3 tests/test_refresh_multiday.py` → explicit staging with a deletion guard → `data(refresh)` commit → push → `touch data/last-success` → one Slack line to #fishing-report-alerts every run → heartbeat row. Full contract in the task's SKILL.md and `BUILD-PLAN.md` §10.
- **One script, two surfaces** (since 2026-11-08). `refresh_multiday.py` writes the `MULTI` block *and* the long-range `RAW` block. Never hand-edit between either pair of markers; fix the script and its tests instead. `--skip-longrange` refreshes multi-day only.
- `BOATS` stays hand-maintained — it changes only when a boat joins the fleet, and `boatIdx` indexes it. `tests/test_refresh_multiday.py` asserts it stays in the same order as the script's `BOAT_SOURCES`.
- **`RAW` carries curation the boat pages cannot supply, and a refresh must preserve all of it:** Ed's `'ed'` flag, his shortened trip names (matched on `(boatIdx, deptDate)`), and trips that already departed. A refresh that drops the `'ed'` flag is a failed refresh; both suites assert it survives.
- Safety nets, all in the script rather than the prompt — keep them there: a stale landing or boat keeps its previous rows; a multi-day row collapse below 60 % holds the page; the same 60 % guard runs **per boat** on the long-range side; a departed-but-unreturned multi-day boat is carried forward; a long-range row whose fields did not all parse cleanly keeps its previous `RAW` values and is counted as `unresolved` instead of publishing a guess (a couple is the steady state — only above 5 % of scraped rows does it make the run partial); a future trip that vanished from a healthy page is dropped as cancelled and logged by name.
- `check_rates.py` **reports only and never edits the dashboard.** Mapping a published cash/credit, 3-mil/5-mil price sheet onto `PROCESSORS` is Ed's call (his decision, 2026-11-08). Every stored rate is the **cash** figure; `calcQuotes` adds each processor's `ccFee` on top, so storing a credit-column value charges the fee twice.
- Interactive sessions must leave the tree clean (only `data/refresh.log`, `data/hold/`, `data/last-success` may differ) or the Sunday preflight aborts with `dirty-tree`.
- Ops coverage: ops-watcher (daily 8:04), fleet-sentinel (Class-1 auto-restart, never on STALLED), launchd fleet watchdog (`data/last-success` mtime). To rerun by hand: `rerun saltwater-multiday-refresh` in #ops-control, or "Run now" in the Scheduled sidebar.
- **Fire time — the cron's nominal time is not the clock time.** The cron is `15 8 * * 0` (Sunday 8:15 AM local) plus a fixed ~6 min jitter, but the scheduler holds the fire time as a UTC instant, **15:21 UTC**. That is **8:21 AM during PDT and 7:21 AM during PST** — observed 08:21 on 2026-10-25, then 07:21 on 2026-11-01 and 2026-11-08 after DST ended, with the next run due 15:21 UTC on 2026-11-15. Documented rather than corrected (Ed's call, 2026-11-08): the landings and boats post days ahead, so an hour earlier changes no data. Do not "fix" the cron expecting the clock time to move — re-pinning it would shift the PDT time instead. The fleet watchdog's 240-minute grace absorbs the hour either way.
