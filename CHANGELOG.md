# Changelog

All notable changes to the Saltwater Long Range Trip Planner. Newest first.

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
