# BUILD PLAN — Multi-Day Boats in the Processing Planner
# Saltwater Long Range Trip Planner · drafted 2026-09-03 · status: awaiting Ed's go

---

## 1. Problem

The Processing Planner sizes a day's processor load from the 9 long-range (LR) boats only.
Multi-day boats (1.5-day and longer) from all four San Diego landings unload the same
mornings and are not counted.

**Calibration — Friday 2026-08-28** (source: sandiegofishreports.com/dock_totals/boats.php?date=2026-08-28,
fetched 2026-09-03; "anglers" there are actual, planner uses capacity):

| Fleet | Planner showed | Actually returned (≥1.5-day, AM) |
|---|---|---|
| Long range | Shogun 8-Day (23), Spirit of Adventure 5-Day (21) | same 2 boats |
| Fisherman's Landing multi-day | — | Tomahawk 1.5D 17, Constitution 2D 19, Fortune 2D (0 listed), Liberty 2D 25, Islander 3.5D 26, Poseidon 3.5D 19 |
| H&M Landing multi-day | — | Ranger 85 1.5D 28, Horizon 2.5D 15, Little G 2.5D 4, Producer 2.5D 17, Excalibur 3D 20 |
| Seaforth multi-day | — | Highliner 1.5D 17, Aztec 2D 23, Pacific Voyager 3D 11 |
| Point Loma multi-day | — | none |
| **Total** | **2 boats · 44 anglers · 🟢 LIGHT** | **16 boats · ~285 anglers · 🔴 HEAVY** |

Assumption: dock-count rows are the boats that unloaded that morning. The counts page does
not say which processor each boat used. Ed's decision (2026-09-03): count all four landings.

---

## 2. Decisions already made by Ed (2026-09-03)

| # | Decision |
|---|---|
| D1 | Fleet scope: all San Diego landings (Fisherman's, H&M, Point Loma, Seaforth) |
| D2 | Minimum trip length that uses the processor: 1.5 day and longer |
| D3 | Return window: 5:00 AM – 10:00 AM only. Boats returning after 10:00 AM are excluded |
| D4 | Volume model unchanged: angler capacity summed per day; Light <60, Moderate 60–99, Heavy 100+ |
| D5 | Multi-day boats appear in the Processing Planner only, not Trip Finder |
| D6 | Refresh: scheduled task, Sunday 8:00 AM, multi-day data only. Long-range refresh stays manual |
| D7 | The task updates the HTML and pushes to GitHub itself using the `gh` login on this Mac (no PAT) |
| D8 | Re-enable GitHub Pages |

---

## 3. Data sources (verified headless 2026-09-03 — HTTP 200, no CAPTCHA, plain `curl`)

| Landing | URL | Format | Horizon posted | Requests |
|---|---|---|---|---|
| Fisherman's Landing | `https://fishermanslanding.fishingreservations.net/resos/?page=N` | HTML, ~50 trips/page | through Aug 2027 (page 12; more pages exist) | ~13+ |
| Seaforth | `https://seaforth.fishingreservations.net/sales/?page=N` | HTML, 25/page | through Jan 2028 | 15 |
| Point Loma Sportfishing | `https://www.pointlomasportfishing.com/schedules.php?page=N` | HTML, 20/page | through Dec 2027 | 24 |
| H&M Landing | `https://www.hmlanding.com/xolacache?callback=JSON_CALLBACK` | JSONP: 520 trips + 209 "experiences" (boat, trip type, duration in minutes, capacity) | through Dec 2026 | 1 (2.6 MB) |
| Calibration / backfill | `https://www.sandiegofishreports.com/dock_totals/boats.php?date=YYYY-MM-DD` | HTML, boats by landing with anglers + trip type | any past date | 1 per day |

Fields per row, all sources: landing, boat, trip type, depart date+time, **return date+time
(explicit — posted by the landing)**, capacity, spots/price. H&M return = datetime + duration.

Known gaps found in recon:
- Chartered rows (139 at Fisherman's, 74 at Point Loma) list no capacity. Plan: default to the
  boat's maximum capacity seen anywhere in the dataset (table in `data/boat_capacity.json`,
  regenerated each run). Assumption: a chartered boat sails near full.
- Long-range boats also appear on landing pages: Shogun, Royal Star, Excel, Royal Polaris,
  Searcher (Fisherman's); American Angler, Independence, Intrepid, Vagabond (Point Loma);
  Polaris Supreme (Seaforth); Spirit of Adventure (H&M). Rule: any boat in the LR set is
  **dropped from the multi-day feed** so `RAW` stays the single source for LR.
- **Searcher and Intrepid become LR boats 10 and 11** (Ed, 2026-09-03). Their pages
  (`https://searcher.fishingreservations.net/sales/`, `https://intrepid.fishingreservations.net/sales/`)
  returned a CAPTCHA "Validation request" page headlessly on 2026-09-03, so they refresh
  manually with the other 9 through the Chrome workaround. To avoid an empty start, Phase 2
  seeds their `RAW` rows from the landing-page rows already captured on 2026-09-03: Searcher
  30 rows via Fisherman's, Intrepid 45 rows via Point Loma, every row with capacity, price and
  spots, departures through Aug 2027 (saved as `recon/landing_trips_2026-09-03.csv` in the
  project folder). Assumption: landing-page rows for these two boats match their own booking
  pages; the next manual LR refresh confirms.
- Recon scrape (2026-09-03): 1,111 unique rows across the three HTML landings + 520 H&M trips.
  Filtered to ≥1.5-day with 5–10 AM return, the multi-day set is roughly 400–500 rows.
  Assumption: exact count comes from the Phase 1 script, not this estimate.
- `fishingreservations.net` landing pages did not CAPTCHA any of ~55 sequential requests at
  1.2–1.5 s spacing. The script keeps that spacing and stops on the first non-200 or on a
  "Validation request" title (the CAPTCHA page also returns HTTP 200).
- Parser quirk: some Fisherman's rows carry a "Check In @ 10AM" line between the depart date
  and depart time (Searcher does this). The parser must skip it or the row is lost.

---

## 4. Design changes to `saltwater_trip_planner.html`

1. **New inline data block** between marker comments the refresh script can rewrite:
   ```
   // ══ MULTI-DAY DATA START (auto-generated by refresh_multiday.py — do not hand-edit) ══
   const MULTI_AS_OF = '2026-09-07';
   const MULTI = [
   // [landing, boat, tripType, days, deptDate, deptTime, retDate, retTime, cap, spots]
   ['FL','Tomahawk','1.5 Day',1.5,'2026-09-04','6:00 PM','2026-09-06','6:00 AM',29,'Full'],
   ...
   ];
   // ══ MULTI-DAY DATA END ══
   ```
   Return date/time is stored, not derived, because durations are fractional and the landings
   post the return. This amends the current "never store return dates separately" rule for
   multi-day rows only. LR rows are unchanged.
2. **Processing Planner merge**: day rows = LR returns (existing derivation) ∪ MULTI returns.
   The 5–10 AM window and ≥1.5-day filters are applied by the script at refresh time, and
   re-checked in the page so a hand edit cannot leak a PM return in.
3. **Day row shows the split**: `LR 2 boats · 44` + `Multi-day 14 boats · 241` = `285 · 🔴 HEAVY`.
   Expanded rows list each boat with landing badge (FL / H&M / PL / SF), trip type, return time.
   Existing stat boxes stay; "Heavy Days (3+)" now counts all boats.
4. **Thresholds unchanged** (D4). Auto-expand unchanged (3+ boats or Ed's trip day).
5. **Two freshness stamps** in the banner: "Long range snapshot Jul 12, 2026 (manual)" and
   "Multi-day snapshot <MULTI_AS_OF> (auto, weekly Sunday)".
6. **Planner month buttons** derive from the union of LR and multi-day return months.
7. Trip Finder untouched. Single-file, no runtime fetch, no localStorage (repo rules kept).

---

## 5. Refresh pipeline (new files in the repo)

| File | Purpose |
|---|---|
| `refresh_multiday.py` | Fetch 4 sources (UA header, 1.5 s spacing, stop on non-200) → parse → filter (D2, D3, LR-dedupe) → write MULTI block into the HTML, update `MULTI_AS_OF`, write `data/multiday_trips.csv` (audit) and `data/boat_capacity.json`, append `data/refresh.log` |
| `test-multiday.js` | jsdom: MULTI parses, no duplicate landing+boat+depart, every row ≥1.5 days with return 5–10 AM, no LR boat in MULTI, planner renders every month, a fixed spot-check day matches the CSV |
| `data/` | CSV + JSON + log (committed; small) |

Safety rules baked into the script:
- If any landing returns 0 rows or a non-200, **keep that landing's previous rows** and log
  `WARN <landing> unchanged`. Never wipe a landing on a bad fetch.
- If total rows drop more than 40% from the previous run, write the CSV but **do not touch the
  HTML**, log `HOLD`, and ping. A human looks before the page changes.
- Never `git add -A`. Stage only the HTML, `data/*`, README if changed. Deletion guard before
  commit (pattern from the daily-ai-morning-briefing task).

---

## 6. Scheduled task `saltwater-multiday-refresh`

- Cron `15 8 * * 0` (Sunday 8:15 AM local). Ed moved it off 8:00 on 2026-09-03 because
  `weekly-brain-review` (8:00 Sun) and `ops-watcher` (8:00 daily) fire in that minute.
- Steps: `git pull` → `python3 refresh_multiday.py` → `node test-multiday.js` → stage listed
  files → commit `data(multiday): refresh multi-day returns <date>` with ≥3 bullets and the
  Co-Authored-By trailer → `git push` → verify → ping (Slack webhook primary, push fallback)
  with the true outcome: rows per landing, days changed, HOLD/WARN if any.
- Permissions: `~/.claude/settings.json` already allows `Bash(git:*)`, `Bash(curl:*)`,
  `Bash(python3:*)`, Read/Edit/Write. Add `Bash(node:*)` for the test step.
- Runs only while the Claude desktop app is open; a missed Sunday runs on next launch.

---

## 7. Repo, Pages, docs

- **Working clone**: the Cowork project folder is not a git repo; the only clone is a ringer
  staging copy under `ringer-jobs/`. Plan: clone `edmatibag9Dev/Saltwater-Long-Range-Trip-Planner`
  into `~/Documents/Claude/Projects/Build Saltwater Trip Planner/repo/` and point the task there.
  The loose `saltwater_trip_planner.html` in the project folder becomes a stale copy — delete it
  after the clone, along with the already-flagged stale files (`Catch_Logger.html`, v1 xlsx,
  `october_trip_planner.html`).
- **GitHub Pages** (D8): `gh api -X POST repos/edmatibag9Dev/Saltwater-Long-Range-Trip-Planner/pages`
  with source main / root. The `gh` token has `repo` scope. Add a one-line `index.html` that
  redirects to `saltwater_trip_planner.html` so the bare Pages URL works (Ed approved 2026-09-03).
- **AGENTS.md**: Rule 4 token handling → "local `gh` login; Contents API only in sandboxes".
  Rule 8 → multi-day rows carry explicit return dates. File map + Rule 6 gain the 4 landing URLs,
  the H&M JSONP feed, and the calibration URL. README: Features, Data Sources, Known Limitations,
  Files table. CHANGELOG entry. llms.txt key rules. Copy this plan in as `BUILD-PLAN.md`.

---

## 8. Phases and gates

| Phase | Work | Gate (must pass before next phase) |
|---|---|---|
| 0 ✅ 2026-09-03 | Clone repo into project folder · re-enable Pages · delete stale files | Pages URL returns 200 · `git status` clean — **passed**: both URLs 200 at build+50 s, commit 08e94a8 pushed, tree clean, 39 calc tests pass against `repo/` |
| 1 ✅ 2026-09-03 | `refresh_multiday.py` + CSV + capacity table · offline tests (`tests/test_refresh_multiday.py`, 15 tests) | Row counts per landing within ±10% of the 2026-09-03 recon · zero LR boats in output · all rows pass D2/D3 — **passed**: live run kept 539 rows (FL 288 · SF 60 · PL 66 · HM 125) from 2,005 raw; 0 LR boats; 0 rule violations. FL −0.4% vs recon. SF +28% and PL +25% were NOT parser drift: both landings posted new series between the 3:30 PM recon and the 6:45 PM run (Tribute 1.5-Day Nov–Dec at SF, Game Changer charters at PL), confirmed by refetching the pages; every row present in both sets matched. Capacity sources: 369 listed · 144 boat-max · 26 default. jsdom page test moves to Phase 2 with the HTML change. |
| 2 ✅ 2026-09-03 | HTML: MULTI block, planner merge, split row, stamps, month union · Searcher/Intrepid as LR 10/11 · `test-multiday.js` · carry-forward in the script (F12) | Sept 6–7 planner days match the four landing pages by hand · all 39 existing calc tests still pass — **passed**: Sep 6 = 6 MD boats / Sep 7 = 8 MD boats, all present on the live pages except Constitution and Poseidon, which had departed that evening and dropped off the pages (that gap is what F12 now covers). 3,886 jsdom assertions, 16 Python tests, 39 calc tests all pass. Rendered check in the in-app browser: header stamps, `11 + 30` boats stat, split badges, September opens by default. Commit cbda3a2. |
| 3 ✅ 2026-09-04 | Scheduled task + ops registration (§10.4) + one supervised run with Ed watching | Commit pushed by the task · heartbeat row written · Slack line received · task visible on mission-control.html · watchdog row added · page on Pages shows new `MULTI_AS_OF` — **passed** except the dashboard line, which needs the next ops-watcher sweep (8:04 AM daily; `watch.py` refused my manual check on a stale snapshot, as designed). Verify Monday after the first unattended Sunday run. |
| 4 ✅ 2026-09-04 | AGENTS / README / CHANGELOG / llms.txt · BUILD-PLAN.md in repo · Open Brain capture · memory pointer | Repo-standard checklist green — **passed**: commit 02eb697 (AGENTS token rule → local gh login, Rule 11 weekly refresh, File map, never-do list; README refresh section + Files; CHANGELOG 2026-09-04; llms.txt). Open Brain thought captured; memory `saltwater-planner-multiday` written. Remaining follow-ups live in §10.4 (Monday verification) and the Open Brain action items. |

---

## 9. Decisions resolved 2026-09-03

| # | Question | Resolution |
|---|---|---|
| 1 | Searcher and Intrepid | Added to the LR set as boats 10 and 11 (Trip Finder + manual refresh). Seeded from landing-page rows. |
| 2 | Sunday run time | 8:15 AM (`15 8 * * 0`) |
| 3 | Chartered rows with no capacity | Default to the boat's max observed capacity (Claude's call, stated to Ed) |
| 4 | Pages entry point | Add `index.html` redirect |
| 5 | Clone location | `…/Build Saltwater Trip Planner/repo/` (Claude's call, stated to Ed) |

Nothing is left open. Build starts on Ed's go.

---

## 10. Alerts and safety nets (added 2026-09-03 at Ed's request)

### 10.1 What already watches scheduled tasks, and whether it will see this one

| Layer | What it does | Sees the new task? |
|---|---|---|
| `ops-watcher` (Claude task, daily 8:04 AM) | Snapshots `list_scheduled_tasks`, runs `watch.py`, alerts #ops-control on MISSED / FAILED / STALLED / PARTIAL | **Yes, automatically.** `watch.py` reads every enabled task from the snapshot. One edit needed: add the task id to the "Personal" group constant in `watch.py` so it renders in the right dashboard section. |
| `watch.py` STALLED check (added 2026-09-03) | A task that fired but wrote no heartbeat for 2 h is STALLED (alert-only, never restarted) | **Only if the task writes a heartbeat.** Without a heartbeat footer every run looks stalled and a hung run looks identical to a good one. Heartbeat is mandatory (§10.3). |
| `fleet-sentinel` (Claude task, hourly; sweeps 9 AM and 8 PM) | Auto-restarts Class-1 (transient) MISSED/FAILED routines, max 2 per day, skips if today's work already landed; drains Ed's Slack `rerun` / `ack` commands | **Yes, automatically** once `watch.py` sees it. Guard 2 (skip-if-landed) needs today's heartbeat, so again the footer is required. STALLED is never auto-restarted; Ed decides. |
| `fleet_watchdog.py` (launchd, hourly, no Claude dependency) | Judges liveness from heartbeats and work artifacts; catches the fleet-wide auth failure that killed everything for 11 days in August | **No, not until registered.** Its `ROUTINES` table is hard-coded (16 rows). Add: `("saltwater-multiday-refresh", "15 8 * * 0", 240, [(HB, None), (MT, <repo>/data/last-success)])`. Commit in the Mission-Control-Dashboard repo; launchd picks it up on the next tick. |
| Slack `#ops-control` poller (launchd, 3 min) | Ed's `rerun <task>` / `ack <task>` / `status` commands | Yes, automatically, by task id. |
| The Claude app itself | Runs the task only while the app is open; a missed fire runs at next launch; a dispatch that never starts is cleared as stale after ~13 min and **still stamps `lastRunAt`** | Covered by the layers above. Nothing in the app detects a session that started and then hung. |

Note on lanes: with GitHub Pages back on, every push publishes. ESCALATION-POLICY v1.2 puts
"a push that triggers publication" in Lane 3. Ed's decision D7 (task pushes on its own) is
the recorded standing exception for this task, the same shape as the daily-ai-morning-briefing
site push. The plan records it here so no future run re-derives it.

### 10.2 Failure modes and the net for each

| # | Failure | Detected by | Net |
|---|---|---|---|
| F1 | One landing page fails: timeout, non-200, CAPTCHA "Validation request" page, 0 rows parsed | Script, per landing | `curl --max-time 30`, 2 retries with 10 s and 30 s backoff. Then **keep that landing's previous rows**, stamp it `stale since <last good date>` in `data/sources.json`, continue with the others. Heartbeat `partial`, Slack line names the landing. Commit still lands for the healthy landings. |
| F2 | All four sources fail (network down) | Script | No HTML change, no commit. Heartbeat `failed`. Slack alert. Sentinel 8 PM sweep retries once (Class 1). |
| F3 | Page format drift: rows parse but total drops more than 40 % from the last run, or any landing drops to 0 while returning 200 | Script | **HOLD**: CSV written to `data/hold/<date>.csv`, HTML untouched, heartbeat `partial` with row counts per landing, Slack alert. This is Class 2 (the parser is wrong, not the network), so the sentinel will not restart it. Ed or a session fixes the parser. |
| F4 | Job hangs inside the script (curl stall, DNS hang) | Script | Every request has `--max-time 30`. The script wraps the whole fetch phase in a 10-minute wall-clock budget (Python `subprocess` timeouts; macOS has no GNU `timeout`) and exits non-zero with a message on overrun. Runner then takes the F2 path. |
| F5 | Job hangs outside the script (an unanswered permission prompt, a TCC dialog) | `watch.py` STALLED after 2 h; ops-watcher alerts #ops-control Monday 8:04; watchdog alerts Sunday by ~12:15 (grace 240 min) | Prevention: prestage permissions with a one-time "Run now" while Ed watches; add `Bash(node:*)` to the allow-list; simple single commands with absolute paths, no `cd … &&` chains. Recovery: Ed replies `rerun saltwater-multiday-refresh` in #ops-control. STALLED is alert-only by design because the run may have finished its real work. |
| F6 | Run never starts (app closed, auth stale) | `lastRunAt` looks fine (it lies); heartbeat absent; watchdog catches auth cause from app logs | Registered watchdog row (§10.1). App runs the task at next launch. |
| F7 | Tests fail after the HTML was rewritten | `node test-multiday.js` non-zero | `git checkout -- saltwater_trip_planner.html` (revert the page), keep the CSV in `data/hold/`, heartbeat `partial`, Slack alert. A page that fails tests is never committed. |
| F8 | Push fails (auth, network, non-fast-forward) | `git push` non-zero | Commit stays local. Heartbeat `partial: push failed`. Slack alert. Next run does `git pull --rebase` first, so both commits go out. A sentinel rerun is safe. |
| F9 | Duplicate run after a real success (sentinel restart, manual rerun) | Script | Idempotent: if `MULTI_AS_OF` is today and the new CSV hash equals the last one, exit `already-landed`, no commit, heartbeat `ok`. |
| F10 | A source keeps failing week after week (H&M changes its feed, a landing moves sites) | Page banner + weekly Slack line | The banner shows a per-landing "as of" date; any landing older than 14 days turns the banner amber with the landing named. Ed sees it on the page even if he ignores Slack. |
| F12 | Landing pages drop a trip the moment it departs, so a boat that left before the Sunday run and has not returned yet is invisible to the fetch (found 2026-09-03: Constitution and Poseidon vanished from the pages within hours of departing) | Script | **Carry-forward**: rows from the previous run that departed before today and return today or later are kept (marked `carried`) when their landing fetched OK. A future trip that disappears is treated as cancelled and dropped. Unit-tested. |
| F11 | Watchdog or watcher themselves dead | Reciprocal check (ops-watcher reads the watchdog stamp; watchdog runs without Claude) | Already in place fleet-wide. Nothing extra for this task. |

### 10.3 What the task writes every run (the contracts the layers above depend on)

1. **Heartbeat, on every exit path, before the final report**: one line appended to
   `Mission-Control-Dashboard/runs/heartbeat.jsonl` as `{"task":"saltwater-multiday-refresh","ts":<ISO with colon offset from the python one-liner>,"status":"ok|partial|failed","note":"FL 412 · H&M 88 · PL 120 · SF 96 · 3 days changed · pushed 1a2b3c4"}`.
2. **Success stamp** `data/last-success` (touched only after a verified push) for the watchdog's mtime proxy.
3. **Run log** `data/refresh.log`: one line per run with per-landing HTTP status, rows, retries, and the outcome word (`landed`, `already-landed`, `partial`, `hold`, `failed`).
4. **Slack, one line per run, every run**, to `#fishing-report-alerts` via `slack_alert.py` (webhook identity; the connector posts as Ed and never notifies): `🎣 Multi-day refresh Sun Sep 6 · OK · FL 412 / H&M 88 / PL 120 / SF 96 · 3 planner days changed · pushed`. Failures use the same line with the outcome word and the landing named. Posting on success too means **silence on a Sunday is itself the alarm**. If the webhook reports `alert-failed`, fall back to PushNotification; never fail the run on an alert error.
5. **Lane-2 digest row** for noteworthy non-blocking findings (a landing stale 2+ weeks, a HOLD) so it reaches the evening digest.

### 10.4 Registration checklist (Phase 3, before the first unattended Sunday)

- [x] 2026-09-04 · Task `saltwater-multiday-refresh` created (cron `15 8 * * 0`, fires ~8:19 with jitter). SKILL.md carries preflight, refresh, test-or-revert, explicit staging + deletion guard, commit/push, last-success stamp, Lane-2 row, Slack line every run, mandatory heartbeat with the timestamp one-liner rule.
- [x] 2026-09-04 · Row added to `ROUTINES` in `fleet_watchdog.py` (grace 240 min, heartbeat + `data/last-success` mtime proxy); `WATCHDOG.md` count 15 → 16; committed 48b3f7d and pushed.
- [x] 2026-09-04 · Task id added to the "Personal" group in `watch.py` (working tree only — `watch.py` already carried an unrelated uncommitted change from 2026-09-03, left for Ed to commit).
- [x] 2026-09-04 · `Bash(node:*)` and `Bash(touch:*)` added to `~/.claude/settings.json` allow-list.
- [x] 2026-09-04 · Supervised "Run now" by Ed: landed, all four landings ok, 539 rows (3 carried forward), commit ca37cb3 pushed, both test suites green, ping=webhook, heartbeat ok, `data/last-success` touched, Pages shows `MULTI_AS_OF = '2026-09-04'`. Finding: the step-6 ping line is appended to `data/refresh.log` after the commit and left the tree dirty (the run committed it as 3601309 on its own judgment). Fix applied to the contract, not the script: preflight now ignores `data/refresh.log`, `data/hold/`, `data/last-success`; pull uses `--autostash`; step 4 stages the log so the ping line rides the next commit; no second commit.
- [x] 2026-09-04 · `#fishing-report-alerts` webhook confirmed: `alert-sent`.
- [ ] First unattended Sunday (2026-09-06) verified Monday: heartbeat row present, Slack line received, `mission-control.html` shows the task OK.
