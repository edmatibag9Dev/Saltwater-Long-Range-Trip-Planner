# 🎣 Saltwater Long Range Trip Planner

A self-contained HTML dashboard for planning long-range saltwater fishing trips out of San Diego and coordinating fish processing schedules based on boat return dates — including the multi-day boats from all four San Diego landings that unload the same mornings. No server, no build step — open the HTML file directly in any browser.

---

## Overview / Purpose

Planning a long-range fishing trip out of San Diego means checking 11 different boat reservation websites, each with its own layout and availability system. This tool aggregates all of them into a single dashboard so you can compare trips, check availability, and click directly to the booking page — all in one place.

The second problem this solves is **fish processing planning**. Knowing how many boats are returning on any given day — and how many anglers are on each — lets you plan processing capacity, staffing, and timing in advance rather than reacting on the day. Since September 2026 this counts the **multi-day boats** (1.5-day trips and longer) from Fisherman's Landing, H&M Landing, Point Loma Sportfishing, and Seaforth alongside the long-range fleet. On 2026-08-28 the long-range-only view showed 2 boats and 44 anglers; the dock actually took 16 boats and about 285 anglers that morning.

This dashboard was built to answer two questions at a glance:
1. Which boats have open trips during the dates I'm available?
2. How many boats and anglers are returning on each day this month?

---

## Features

- **Trip Finder tab** — browse all trips across 11 long-range boats for any month posted (June 2026 through December 2027 at the last refresh)
- **Month filter** — switch between months with a single click on both tabs
- **Availability badges** — color-coded by open spots (green), low spots (yellow), wait list (red), charter/private (gray), and your personal trip (amber)
- **Trip length filter** — filter by short (≤5 days), medium (6–8 days), or long (9+ days)
- **Boat filter** — narrow to a single vessel
- **Direct booking links** — every trip card links to the live reservation page for current availability
- **Processing Planner tab** — see every boat unloading each morning of the selected month: long-range returns derived from departure + trip length, plus multi-day boats (1.5 days or longer, returning 5:00–10:00 AM) from the four San Diego landings, with the long-range / multi-day split and estimated angler counts
- **Volume indicators** — daily processing load flagged as Light / Moderate / Heavy with color-coded bars (thresholds unchanged: under 60 / 60–99 / 100+ anglers)
- **Freshness stamps** — the header shows the long-range snapshot date and the multi-day snapshot date separately; the multi-day stamp turns amber and names any landing whose data is older than 14 days
- **Auto-expand** — heavy days (3+ boats) and your personal trip return day expand automatically on load
- **Personal trip flag** — your trip is marked 📍 across both tabs
- **Invite/code flags** — trips requiring an invitation code are clearly marked ⚠️
- **Derived return dates** — processing planner data is computed from departure date + trip duration, no manual entry needed
- **Processing Calculator tab** — estimate and compare fish-processing cost across two San Diego processors (Fisherman's Processing vs Five Star) by species and service

---

## Files

| File | Description |
|------|-------------|
| `saltwater_trip_planner.html` | Main dashboard — self-contained, open directly in browser. Long-range trips live in the inline `RAW` array; multi-day trips in the auto-generated `MULTI` block between marker comments |
| `test-multiday.js` | jsdom integration test of the multi-day Processing Planner (data block vs CSV, rules, Searcher/Intrepid seed, every month renders, Sep 6–7 spot check, Trip Finder isolation, header stamps). `node test-multiday.js` |
| `index.html` | GitHub Pages entry point — redirects the bare site URL to `saltwater_trip_planner.html` |
| `CONTRIBUTING.md` | Commit message and README standards for this repo |
| `AGENTS.md` | AI agent behavior rules for GitHub operations and repo maintenance |
| `Saltwater_Fish_Processing_Calculator_v2.xlsx` | Offline per-fish processing-cost workbook (Numbers-compatible) — same engine rules, for use at sea |
| `refresh_multiday.py` | Fetches multi-day boat schedules from the four San Diego landings, applies the processing-planner rules, writes `data/` and (in Phase 2) the planner's MULTI-DAY block. Headless, no browser. |
| `tests/test_refresh_multiday.py` | 15 offline tests for the refresh script (parser, rules, capacity fill, dedupe, block writer, stale/hold safety nets) using saved pages in `tests/fixtures/` |
| `data/multiday_trips.csv` | Latest kept multi-day rows (1.5-day+, returning 5–10 AM, long-range boats removed) — the audit copy of what the planner shows |
| `data/landing_trips_raw.csv` | Every trip parsed from the four landings before filtering, for audit |
| `data/boat_capacity.json`, `data/sources.json`, `data/last_run.json`, `data/refresh.log` | Per-boat max capacity (fills chartered rows), per-landing fetch status and last-good date, last-run summary for the scheduled task, append-only run log |
| `README.md` | This file |

---

## How to Use

### Opening the Dashboard

Open the hosted copy at https://edmatibag9dev.github.io/Saltwater-Long-Range-Trip-Planner/ (GitHub Pages, re-enabled 2026-09-03), or download `saltwater_trip_planner.html` and open it in any browser. No internet connection required for the dashboard itself — it runs entirely from the file.

### Trip Finder Tab

1. Click a **month button** at the top (Jun through Jan) to load trips for that month
2. Use the **Availability filter** to show only open spots, wait list trips, or charter/private trips
3. Use the **Boat filter** to narrow to a single vessel
4. Use the **Trip Length filter** to find short (≤5 day), medium (6–8 day), or long (9+ day) trips
5. Click **Book Now →** on any card to open the boat's live reservation page in a new tab — this is where you'll see current real-time availability and place a deposit
6. Trips marked ⚠️ require an invitation code — contact the boat directly

**Availability color coding on trip cards:**
- 🟢 Green left border — 4 or more spots open
- 🟡 Yellow left border — 1–3 spots remaining
- 🔴 Red left border — wait list only (trip is full, join wait list for cancellations)
- ⬜ Gray left border — charter or private, not open to general public
- 🟠 Amber left border — your personal trip

### Processing Planner Tab

1. Click a **month button** to view boat returns for that month (months come from both fleets' schedules)
2. Each day row shows: number of boats returning, the split (`2 LR · 6 MD` = long-range · multi-day), estimated total angler count, and a volume bar
3. Click any **day row** to expand the details — long-range boats first (🚢, LR badge), then multi-day boats (🛥️, landing badge FL / HM / PL / SF) with trip type, departure, posted return time, and angler count. Chartered multi-day trips list no capacity on the landing pages, so they show the boat's usual capacity marked *(charter, est.)*
4. **Heavy days (3+ boats) auto-expand on load** — these are your high-volume processing days
5. Your personal trip return day is marked 📍 and auto-expands

**Volume thresholds:**
- 🟢 Light — under 60 anglers returning that day
- 🟡 Moderate — 60–99 anglers returning
- 🔴 Heavy — 100+ anglers returning

Long-range boats return approximately **6:00–8:00 AM**. Multi-day boats are included only when their posted return time falls between **5:00 and 10:00 AM**; boats returning later in the day do not compete for the morning processing window and are excluded.

### Processing Calculator Tab

Estimate and compare what your catch will cost to process at two San Diego processors — **Fisherman's Processing** and **Five Star Fish Processing**.

1. Toggle **Cash** or **Credit Card** (credit adds each processor's own fee — Fisherman's 3%, Five Star 3.95% — on the processing subtotal)
2. Enter **total pounds per species** (Yellowtail, Bluefin, Yellowfin, Wahoo, Rockfish); leave a species at 0 if you kept none
3. For Yellowtail, Yellowfin, and Rockfish, use the **"under 12 lb"** sub-field to bill that portion at Fisherman's lower weight tier (Bluefin, Wahoo never qualify for the under-12 rate — species-gated, not weight-derived)
4. **Opt in** to Smoking, Jerky, or Canning to reveal weight fields for the eligible species only — those pounds come out of the fillet weight and are billed at the value-added rate
   - Smoking: tuna, yellowtail, wahoo (15 lb minimum **per fish**)
   - Jerky: bluefin and yellowfin only (15 lb minimum **per fish**)
   - Canning: bluefin and yellowfin only (15 lb minimum **per fish**)
   - **The 15 lb minimum is per individual fish — pounds do not pool across fish.** Two 10 lb yellowfin cannot combine into a 20 lb smoke order; the processor will not perform it. Enter only pounds sourced from single fish of 15 lb or more. For exact per-fish billing at sea, use the companion [Catch Logger](https://edmatibag9dev.github.io/catch-logger/) — its `engine.js` is the canonical implementation of these cost rules
5. Read the side-by-side quote: processing subtotal → card fee → **Est. total**, with Fisherman's also showing a **Net est. total** after its prepaid $100 deposit
6. The lower-cost processor is flagged; the **comparison matrix** below covers locations, dock pickup, hours, rates, deposit terms, and shipping

> Rates are entered from each processor's published price sheet (June 2026) and may change — always confirm at drop-off. For offline use at sea, `Saltwater_Fish_Processing_Calculator_v2.xlsx` in this repo applies the same per-fish rules in the Numbers app (one row per kept fish). San Diego Fish Processing is excluded because it publishes no rates.

---

## Data Sources

All trip data was scraped directly from each boat's live reservation system. The data shown is a **snapshot** — availability changes daily as bookings and cancellations occur.

| Boat | Reservation Page |
|------|-----------------|
| Shogun Sportfishing | https://shogun.fishingreservations.net/sales/ |
| American Angler Sportfishing | https://americanangler.fishingreservations.net/sales/ |
| Royal Star Long-Range | https://royalstar.fishingreservations.net/sales/ |
| Independence Sportfishing | https://independence.fishingreservations.net/sales/ |
| Vagabond Sportfishing | https://vagabond.fishingreservations.net/sales/ |
| Polaris Supreme | https://polarissupreme.fishingreservations.net/sales/ |
| Royal Polaris | https://royalpolaris.fishingreservations.net/sales/ |
| Excel Sportfishing | https://excel.fishingreservations.net/sales/ |
| Spirit of Adventure | https://soa.fishingreservations.net/sales/ |
| Searcher | https://searcher.fishingreservations.net/sales/ |
| Intrepid | https://intrepid.fishingreservations.net/sales/ |

Searcher and Intrepid were added 2026-09-03 and seeded from the Fisherman's Landing and Point Loma landing schedule pages (their own booking pages serve a CAPTCHA to headless requests). Verify them at the next manual long-range refresh.

**Multi-day boats (Processing Planner only)** — refreshed weekly by `refresh_multiday.py`, no browser needed:

| Landing | Schedule source |
|------|-----------------|
| Fisherman's Landing | https://fishermanslanding.fishingreservations.net/resos/ (paged) |
| Seaforth Sportfishing | https://seaforth.fishingreservations.net/sales/ (paged) |
| Point Loma Sportfishing | https://www.pointlomasportfishing.com/schedules.php (paged) |
| H&M Landing | https://www.hmlanding.com/xolacache (JSONP feed behind the trip calendar) |

**Last multi-day refresh:** 2026-09-04 (updated automatically by `refresh_multiday.py`)

Calibration source for past days: https://www.sandiegofishreports.com/dock_totals/boats.php?date=YYYY-MM-DD (boats by landing with anglers and trip type).

**Red Rooster III** (`https://www.redrooster3.com/trips.htm`) is tracked but had no 2026 fall schedule posted at the time of the last data pull — only 2025 dates were available.

**Data coverage:** long-range trips through December 2027 (snapshot 2026-07-12; Searcher/Intrepid 2026-09-03). Multi-day trips as far as each landing posts — H&M posts about four months ahead, the other three post 12–16 months ahead — so far-future months undercount H&M until they publish.

---

## Known Limitations & Workarounds

### CAPTCHA on fishingreservations.net

8 of the 9 boats use the `fishingreservations.net` booking platform. This platform applies bot/CAPTCHA detection (error 338) when receiving rapid sequential automated requests from the same IP address.

**Workaround for data refreshes:**
1. Open each of the 9 boat reservation links manually in your browser (all at once in separate tabs is fine)
2. Once the pages are loaded in your browser, use the Claude in Chrome extension to read each tab's content
3. Claude reads through your authenticated browser session — the CAPTCHA does not trigger because the pages are already loaded
4. Shogun typically loads cleanly on the first automated request before blocking kicks in

### Availability is a snapshot

The open spot counts and wait list statuses shown in the dashboard reflect the state at the time of the last data pull. Always click **Book Now →** to verify current availability on the live reservation page before making plans.

### Red Rooster III — no 2026 schedule

Red Rooster III posts their schedule on a custom site (`redrooster3.com`) rather than `fishingreservations.net`. As of the last data pull, only the 2025 fall season schedule was available. Check their site directly for 2026 dates.

### Angler counts are capacity-based

The Processing Planner shows **boat capacity** as the angler count, not actual bookings. Real passenger counts may be lower. Charter and private trips with no listed capacity default to ~20 for planning purposes.

---

## Build Notes

- **Zero dependencies** — pure HTML, CSS, and vanilla JavaScript. No npm, no build step, no server required
- **Single file** — all CSS and JS are inline. The entire dashboard is one `.html` file
- **Works as `file://`** — open directly from your desktop or any static host
- **Trip data structure** — stored as a compact JS array in the format `[boatIdx, name, deptDate, days, capacity, spots, price, flags]`. Spot codes: `-2` = in progress, `-1` = charter/private, `0` = wait list, `1–3` = low spots, `4+` = open
- **Processing Planner is derived** — return dates are computed from `deptDate + days` at runtime, not stored separately. This means the processing planner is always in sync with the trip data with no extra maintenance
- **Month filtering** — both tabs filter client-side from the same dataset using JavaScript
- **Personal trip flagging** — Ed's trips are marked with the `'ed'` flag in the data array and receive amber styling + 📍 marker across both tabs
- **Teal-Sage brand** — dashboard uses brand tokens (#2C7A6B teal, #2B4C7E navy) with Fraunces / Inter / IBM Plex Mono fonts; availability green/yellow/red kept distinct from brand teal

---

## Update / Refresh Instructions

### Multi-day boats (Processing Planner only)

Multi-day boats from Fisherman's Landing, H&M Landing, Point Loma Sportfishing, and Seaforth are refreshed by `refresh_multiday.py`, which needs no browser — all four sources load headlessly:

```
python3 refresh_multiday.py            # fetch, write data/, update the planner's MULTI-DAY block
python3 refresh_multiday.py --dry-run  # fetch and write data/ only
python3 tests/test_refresh_multiday.py # offline tests against saved pages
```

Rules applied: trip length 1.5 days or longer, return time 5:00–10:00 AM, long-range boats dropped (they live in `RAW`). Safety nets: 30 s per-request timeout with two retries, 10-minute fetch budget, a failed landing keeps its previous rows and is marked stale, a row-count collapse below 60 % of the last run holds the page and writes the CSV to `data/hold/`, and an unchanged result exits `already-landed` without rewriting anything. Exit codes: 0 landed / already-landed, 2 partial, 3 hold, 4 failed. A weekly scheduled task (Sunday 8:15 AM) runs this and pushes the result.


To pull fresh availability data:

1. Open all 9 reservation links in your browser (see Data Sources above)
2. Use the Claude in Chrome extension to read each page — ask Claude to extract all trip data for the target months
3. Update the `RAW` array in `saltwater_trip_planner.html` with new spot counts, availability codes, and any new/removed trips
4. Save the file and open it in your browser to verify
5. Commit using the `data` type: `data(trip-planner): refresh availability snapshot — <month> <year>`
6. Push the updated file to GitHub via the Contents API (GET sha first, then PUT with sha)

**To add a new month's data** — simply append new entries to the `RAW` array with the correct departure dates. The month filter and processing planner will pick them up automatically.

**To flag your own trip** — add `'ed'` to the flags array in the trip's data row: `[boatIdx, name, deptDate, days, capacity, spots, price, ['ed']]`

---

## Reservation Tips

- Most boats require a **50% deposit** to hold a spot — full balance due 45–60 days before departure
- **Passports required** on all trips fishing in Mexican waters
- **Mexican fishing permits** are not included in most trip prices — budget an additional fee
- **Fuel surcharges** may be added at time of sailing depending on diesel prices
- **Travel insurance strongly recommended** — most deposits are non-refundable within 90–180 days of departure
- For wait list trips, call the boat office directly — cancellations open spots frequently
- Trips marked "invite only" require a code from the charter master — Claude cannot book these for you

---

*Last data pull: June 2026 | Processing rates: June 2026 | Built with Claude (Anthropic) | Standards: CONTRIBUTING.md + AGENTS.md*
