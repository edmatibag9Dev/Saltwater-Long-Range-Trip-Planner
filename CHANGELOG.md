# Changelog

All notable changes to the Saltwater Long Range Trip Planner. Newest first.

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
