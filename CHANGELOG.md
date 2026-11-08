# Changelog

All notable changes to the Saltwater Long Range Trip Planner. Newest first.
Format follows [Keep a Changelog](https://keepachangelog.com/); dates are America/Los_Angeles.
Gitignored data/output files are never committed.

## [2026-11-08] — Put the long-range boats and the processor rates on the weekly schedule

Review of the planner's update schedule found only one of its three data surfaces was being
refreshed. The long-range `RAW` array was four months stale and the processor rates five, with
nothing watching either.

### Added
- **Long-range refresh in `refresh_multiday.py`.** All 11 boats' own `/sales/` pages are read weekly
  into the `RAW` block, which is now generated between `// ══ LONG-RANGE DATA START/END` markers.
  `AGENTS.md` Rule 6 said these pages CAPTCHA headless requests, which is why `RAW` was maintained
  by hand; all 11 were verified to return HTTP 200 with full schedule tables using the same
  User-Agent and 1.5 s spacing the landing pages already use. First run: 901 rows across the fleet,
  May 2026 → January 2028.
- **Curation carry-forward.** `RAW` holds three things the boat pages cannot supply, and all three
  survive a refresh: Ed's `'ed'` trip flag, his shortened trip names (an existing name wins on a
  `(boatIdx, deptDate)` match; only a new trip takes the page's wording), and trips that already
  departed, which the pages drop the moment a boat sails. Both suites assert the `'ed'` flag survives.
- **Per-row confidence gate.** A long-range row is written only when every field parses cleanly;
  otherwise it keeps its previous values and is counted as `unresolved`. The 11 pages vary more than
  the landings do — five wait-list spellings, five charter spellings, three price formats — so a
  parser quirk is reported as a number rather than published as wrong trip data. Currently 2 rows,
  both on Royal Star; only above 5 % of scraped rows does it make the run partial.
- **Per-boat collapse guard**, and cancelled-trip detection: a future trip missing from a healthy
  page is dropped and logged by name.
- **`check_rates.py`** — compares both processors' published **cash** rates to `PROCESSORS` and
  writes `data/rates_check.json`. Reports only; it never edits the dashboard, because choosing
  between a cash and credit column and 3-mil and 5-mil bag prices is a judgement call (Ed's
  decision). Exit 0 no change, 2 a rate moved, 4 both pages unreachable.
- `#lr-stamp` on the page: a generated long-range freshness stamp with per-boat statuses, amber when
  any boat is stale or older than 14 days — matching the multi-day stamp, which was the only
  self-checking one before.
- 24 tests and 5 fixtures (three boat pages chosen for their quirks, both rate pages). Suites now
  run 2538 jsdom assertions and 41 Python tests.

### Fixed
- **Five Star rates mixed the published cash and credit columns.** `big`, `small` (1.97) and `collar`
  (5.19) were credit-column figures while the rest were cash, and `calcQuotes` adds the 3.95 % card
  fee on top — so those three were surcharged twice. Corrected to the cash figures (1.90 and 5.00).
  The block comment claiming rates were `[cash, card]` pairs with the fee baked in described neither
  the data nor the code; rewritten to state the actual contract. `RATE_DATE` June 2026 → November 2026.
  A test now asserts no stored rate equals its page's credit figure.
- `js_rows`, reading the existing `RAW`, prepended the array's alignment padding to every string it
  preceded, and a regex-based reader mangled apostrophes inside double-quoted trip names
  ("Ken's Custom Reels" — 52 rows). Both covered by tests.
- Trip-length error in `RAW`: Shogun 2027-03-26 was stored as 2 days where the page and the row's own
  name both say 1.5-Day. The refresh corrects data like this automatically now.
- Two jsdom assertions pinned the hand-seeded 2026-09-03 trip counts for Searcher and Intrepid, which
  a live refresh legitimately changes; they now assert a full schedule rather than an exact number.

### Changed
- Task `saltwater-multiday-refresh` → shown as "Saltwater Trip Planner refresh". Its SKILL.md gains a
  rate-check step, the new staging paths, a four-segment Slack line, and the two-surface
  `last_run.json` shape. Commit subject is now `data(refresh): …`.
- `data/last_run.json` keeps every field it had at the top level and adds `multiday` and `longrange`
  sub-objects; `outcome` is now the worse of the two surfaces, and so is the exit code.
- `refresh_multiday.py` gains `--skip-longrange`. `write_block` and `stamp_readme` take the marker
  pair and README label as arguments; `write_csv` takes a field list.
- AGENTS.md Rule 6 rewritten (the CAPTCHA claim was wrong for every page the planner reads, and the
  Chrome-tab method is now a documented repair path, not the weekly job); Rule 11 covers both
  surfaces and the rate check. README refresh instructions rewritten accordingly.
- Schedule documentation corrected (decision D14). The cron reads `15 8 * * 0` but the scheduler
  holds the fire time as a UTC instant, 15:21 UTC — so the task runs at 8:21 AM in summer and
  7:21 AM in winter, which is why it moved an hour after the 2026-11-01 DST change. The schedule is
  deliberately left alone: the boats and landings post days ahead, the watchdog's 240-minute grace
  covers both seasons, and re-pinning the cron would only move the discrepancy to the other half of
  the year. The two dashboard stamps, the README and AGENTS.md Rule 11 now say "Sunday morning"
  instead of "8:15 AM"; BUILD-PLAN.md §11 carries the full explanation.
- BUILD-PLAN.md retitled "Trip Planner data refresh" and the long-range work moved out of §10
  (alerts and safety nets, which is multi-day scoped) into its own §11. §1–10 remain the 2026-09
  multi-day plan; the stale "status: awaiting Ed's go" header is replaced with the built state.

### Removed
- The manual six-step long-range refresh procedure from the README, replaced by the automated
  description. The browser-tab method is kept under Workarounds as the repair path.

## [2026-10-10] — Fix docs that contradicted the code

### Fixed
- README long-range refresh step 6 now says `git push origin main` (decision D7) instead of the GitHub Contents API.

## [2026-10-09] — Conform to repo standard 2026-10-09

### Changed
- AGENTS.md restructured to the standard: fixed opening line and `Standard:` stamp, then the seven required sections (What this repo is, File map, The data contract, How it works, How to extend, Privacy — hard rules, Verification gates). The generic GitHub-operations rules (Rules 1–5, 7–10, forked from the June global rulebook) are replaced by a link to `~/.claude/GITHUB-OPERATIONS.md`; the repo-specific additions to Rules 4, 8, 9 and 10, the File map, Node dependencies, Rule 6 scraping protocol and Rule 11 weekly refresh are kept.
- README.md split into the nine separate CONTRIBUTING.md sections: "Overview / Purpose" → Project Overview + Purpose, "Files" → File Descriptions (missing files added), "Known Limitations & Workarounds" → Known Limitations + Workarounds. "Update / Refresh Instructions" and "Reservation Tips" moved under How to Use as subsections. Added the `Last updated` line.
- .gitignore gains the standard entries `.env`, `.env.*`, `!.env.example`, `CONFIG.local.md`, `*.bak*`, `.venv/`.
- CHANGELOG.md now declares the Keep a Changelog format.
- llms.txt: AGENTS.md entry re-described to match its new contents.

## [2026-09-04]

### Added
- **Scheduled task `saltwater-multiday-refresh`** (Sundays 8:15 AM): pulls the four landings, tests, commits, pushes, touches `data/last-success`, posts one line to #fishing-report-alerts every run, writes a heartbeat. Registered with the fleet watchdog and ops-watcher. Supervised first run landed commit ca37cb3.
- **Carry-forward** in `refresh_multiday.py`: landings drop a trip the moment it departs, so previous rows that departed before the run and return later are kept.
- **README freshness line** ("Last multi-day refresh") stamped by the script on every refresh.
- **`BUILD-PLAN.md`** — the full plan with decisions, safety nets, and phase gate results.

### Changed
- AGENTS.md: token rule now uses the local `gh` login (Contents API only in sandboxes); new Rule 11 for the weekly refresh; File map and never-do list updated.
- AGENTS.md: new "Node dependencies" section — `jsdom` and `docx` are declared in a `package.json` in the parent Cowork folder, not in this repo; documents `npm test`, the never-add-a-manifest-here rule, and the `--no-save` pruning trap that deleted `jsdom` and broke `test-multiday.js`. Corrected the stale File map footnote that claimed `.gitignore` and `BUILD-PLAN.md` were untracked when both are listed as tracked directly above it.


## [2026-09-03]

### Added
- **Multi-day boats in the Processing Planner** — every day now merges long-range returns with multi-day boats (1.5 days or longer, returning 5:00–10:00 AM) from Fisherman's Landing, H&M Landing, Point Loma Sportfishing, and Seaforth. Day rows show the split (`2 LR · 6 MD`), expanded rows carry a landing badge and the posted return time, totals show long-range / multi-day / combined. Trip Finder is unchanged. Motivation: on 2026-08-28 the planner showed 2 boats / 44 anglers (Light); the dock took 16 boats / ~285 anglers (Heavy).
- **Searcher and Intrepid** added as long-range boats 10 and 11 (30 and 45 trips seeded from the landing pages on 2026-09-03).
- **Freshness stamps** — separate long-range and multi-day snapshot dates in the header; the multi-day stamp turns amber and names any landing older than 14 days.
- **`test-multiday.js`** — jsdom integration test (3,886 assertions on the first run).
- Processing Planner opens on the current month when it has data.
- **`refresh_multiday.py`** — headless fetch of multi-day boat schedules from Fisherman's Landing, Seaforth, Point Loma Sportfishing, and H&M Landing; keeps 1.5-day+ trips returning 5–10 AM, drops long-range boats, fills chartered capacities from per-boat maximums, writes `data/`. Safety nets: retries, fetch budget, stale-landing carry-forward, hold on row collapse, idempotent exit.
- **`tests/test_refresh_multiday.py`** with saved fixtures — 15 offline tests.
- **`data/`** audit outputs from the first live run (539 kept rows from 2,005 raw).
- **`index.html`** — GitHub Pages entry point that redirects the bare site URL to `saltwater_trip_planner.html`.

### Changed
- GitHub Pages re-enabled (main branch, root). The Pages config had been deleted when the repo was temporarily made private in July 2026.

## [2026-06-21]

### Added
- **Processing Calculator tab** — estimate and compare fish-processing cost across two San Diego processors (Fisherman's Processing vs Five Star Fish Processing).
  - Species-based catch input: Yellowtail, Bluefin, Yellowfin, Wahoo, Rockfish (total lbs each; zero drops the species from the quote).
  - Per-species Fisherman's price tier (Rockfish under-12 lb, others 12 lb+), with an "under 12 lb" split for Yellowtail and Yellowfin.
  - Opt-in value-added with enforced eligibility — Smoking (tuna/yellowtail/wahoo), Jerky (bluefin/yellowfin only), Canning (bluefin/yellowfin only); 15 lb minimum on smoking and jerky; value-added pounds deduct from fillet weight.
  - Per-processor credit-card fee applied to the processing subtotal (Fisherman's 3%, Five Star 3.95%, derived from each shop's published cash vs credit columns).
  - Est. total = processing subtotal + card fee; Fisherman's also shows a Net est. total after the prepaid $100 deposit.
  - At-a-glance comparison matrix: locations, dock pickup, hours, rates, deposit terms (forfeit clause flagged), card fees, storage, shipping.
  - San Diego Fish Processing excluded — no published rates.

### Changed
- Rebranded the entire dashboard to the Teal-Sage palette (#2C7A6B teal, #2B4C7E navy) with Fraunces / Inter / IBM Plex Mono typography. Availability green/yellow/red kept distinct from brand teal.
