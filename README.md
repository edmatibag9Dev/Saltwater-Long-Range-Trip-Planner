# 🎣 Saltwater Long Range Trip Planner

A self-contained HTML dashboard for planning long-range saltwater fishing trips out of San Diego and tracking fish processing schedules based on boat return dates.

---

## 📋 Overview

This tool was built to solve two problems:

1. **Trip Planning** — Quickly see which long-range boats have open spots for a given month without visiting 9 different reservation websites
2. **Fish Processing Planning** — Know exactly how many boats are returning on any given day so processing capacity and timing can be planned in advance

---

## 🚢 Boats Tracked

| Boat | Reservation Page |
|------|-----------------|
| Shogun Sportfishing | https://shogun.fishingreservations.net/sales/ |
| American Angler Sportfishing | https://americanangler.fishingreservations.net/sales/ |
| Royal Star Long-Range Sportfishing | https://royalstar.fishingreservations.net/sales/ |
| Independence Sportfishing | https://independence.fishingreservations.net/sales/ |
| Vagabond Sportfishing | https://vagabond.fishingreservations.net/sales/ |
| Polaris Supreme Long Range | https://polarissupreme.fishingreservations.net/sales/ |
| Royal Polaris Sportfishing | https://royalpolaris.fishingreservations.net/sales/ |
| Excel Sportfishing | https://excel.fishingreservations.net/sales/ |
| Spirit of Adventure Sportfishing | https://soa.fishingreservations.net/sales/ |

> **Note:** Red Rooster III (`redrooster3.com/trips.htm`) is tracked but had no 2026 fall schedule posted at the time of the last data pull — only 2025 dates were available. Check their site directly for updates.

---

## 📁 Files

| File | Description |
|------|-------------|
| `saltwater_trip_planner.html` | Main dashboard — open directly in any browser, no server required |

---

## 🖥️ How to Use the Dashboard

Open `saltwater_trip_planner.html` in your browser. The dashboard has two tabs:

### Tab 1 — 🚢 Trip Finder

Browse all available trips across all 9 boats for any month from **June 2026 through January 2027**.

**Controls:**
- **Month buttons** (top) — switch between months
- **Availability filter** — show only open spots, wait list, or charter/private trips
- **Boat filter** — narrow to a single vessel
- **Trip length filter** — short (≤5 days), medium (6–8 days), or long (9+ days)

**Availability color coding:**
- 🟢 **Green border** — 4 or more open spots
- 🟡 **Yellow border** — 1–3 spots remaining
- 🔴 **Red border** — wait list only (trip is full)
- ⬜ **Gray border** — charter or private, not open to public
- 🟠 **Amber border** — your personal trip

Each card shows departure date, return date, duration, price, and links directly to the boat's reservation page. Trips requiring an invitation or code are flagged with ⚠️.

**Booking:** Click **Book Now →** on any card to go directly to that boat's live reservation page for current availability and to place a deposit.

---

### Tab 2 — 🐟 Processing Planner

Shows every boat returning on each day of the selected month, with estimated angler counts for planning fish processing capacity.

**Controls:**
- **Month buttons** (top) — switch between June–December 2026
- Each day row shows: number of boats returning, estimated total angler count, and a volume bar
- Click any day row to expand and see individual boat details (boat name, trip name, departure date, trip length, angler count)
- Heavy days (3+ boats returning) **auto-expand** on load
- Your personal trip return day is marked with 📍 and auto-expands

**Volume thresholds:**
- 🟢 **Light** — under 60 anglers returning
- 🟡 **Moderate** — 60–99 anglers returning
- 🔴 **Heavy** — 100+ anglers returning

**How return dates are calculated:** The planner derives all return dates automatically from each trip's departure date plus trip duration — no manual data entry. This means every trip on every boat is represented in the processing view for its actual return day.

> All boats depart from San Diego and return approximately **6:00–8:00 AM**.

---

## ⚠️ Important: Data Freshness

The availability data (open spots, wait list status) in this dashboard is a **snapshot** pulled at the time of the last update. Trip availability changes daily as reservations are made and cancellations occur.

**Two ways to get current availability:**

1. **Quick lookup** — Click the **Book Now →** link on any trip card to go directly to the boat's live reservation page
2. **Full refresh** — Re-scrape all boat schedules and rebuild the dashboard for the most accurate picture (see Data Update section below)

The trip schedule itself (dates, prices, boat capacity, trip names) is generally stable once posted and is reliable for planning purposes.

---

## 🔄 Updating the Data

The reservation sites use `fishingreservations.net` as their booking platform. All 9 boats share this platform except Red Rooster III.

**Known scraping behavior:**
- The `fishingreservations.net` platform applies bot/CAPTCHA detection on rapid sequential requests from the same IP
- The first boat fetched typically loads cleanly; subsequent requests in the same session may be blocked
- **Workaround:** Open each boat's reservation link manually in your browser, then use a browser automation tool (such as the Claude in Chrome extension) to read the page text — this bypasses the CAPTCHA because the page loads through your authenticated browser session

**Reservation links to open for a data refresh:**
1. https://shogun.fishingreservations.net/sales/
2. https://americanangler.fishingreservations.net/sales/
3. https://royalstar.fishingreservations.net/sales/
4. https://independence.fishingreservations.net/sales/
5. https://vagabond.fishingreservations.net/sales/
6. https://polarissupreme.fishingreservations.net/sales/
7. https://royalpolaris.fishingreservations.net/sales/
8. https://excel.fishingreservations.net/sales/
9. https://soa.fishingreservations.net/sales/
10. https://www.redrooster3.com/trips.htm

---

## 🐟 Fish Processing Planning Notes

The Processing Planner is designed to help coordinate fish processing capacity around boat arrival days. Key planning considerations:

- **Angler counts** shown are the listed boat capacity — actual passenger counts may be lower depending on how full the trip sold
- **Charter and private trips** are included in return date calculations using an estimated count of ~20 anglers when no capacity is listed
- **Multiple boats returning the same day** — plan for maximum capacity if more than 2 boats return on the same day
- **Return time** — all boats return approximately 6:00–8:00 AM, so processing can begin in the morning

---

## 🗓️ Data Coverage

| Month | Trip Finder | Processing Planner |
|-------|-------------|-------------------|
| June 2026 | ✅ | ✅ |
| July 2026 | ✅ | ✅ |
| August 2026 | ✅ | ✅ |
| September 2026 | ✅ | ✅ |
| October 2026 | ✅ | ✅ |
| November 2026 | ✅ | ✅ |
| December 2026 | ✅ | ✅ |
| January 2027 | ✅ (Trip Finder only) | — |

---

## 🛠️ Build Notes

- **No dependencies** — pure HTML, CSS, and vanilla JavaScript. Open the file directly in any browser
- **No server required** — works as a local file (`file://`) or hosted on any static host
- **Trip data** is stored as a compact JavaScript array in the HTML file and parsed at runtime
- **Processing Planner data** is derived programmatically from the trip array — return dates are computed from departure date + trip duration, so there is no separate data source to maintain for the planner
- All booking links open in a new tab and point to the live reservation page for that boat

---

## 📬 Reservation Tips

- Most boats require a **50% deposit** to hold a spot
- **Passports are required** on all trips fishing in Mexican waters
- **Mexican fishing permits** are not included in most trip prices (check each boat's terms)
- **Fuel surcharges** may be added depending on diesel prices at time of sailing
- Travel insurance is strongly recommended — most deposits are non-refundable within 90–180 days of departure
- For wait list trips, call the boat office directly — cancellations open up frequently

---

*Last data pull: June 2026 | Built with Claude (Anthropic)*
