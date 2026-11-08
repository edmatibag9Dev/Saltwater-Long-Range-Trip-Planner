#!/usr/bin/env python3
"""check_rates.py — tell Ed when a fish processor's published rates move.

The Processing Calculator's PROCESSORS rates are entered by hand from two published price
sheets. Nothing watched them, so they sat stamped "June 2026" for five months. This script
closes that gap, and deliberately does only half the job:

    IT NEVER EDITS THE DASHBOARD.

Mapping a published sheet onto the calculator's fields is judgment, not parsing — both
processors publish a cash column and a credit column, Five Star publishes separate 3 mil
and 5 mil bag prices, and the calculator stores ONE cash rate per field and derives the
card price by adding the processor's ccFee. A wrong auto-edit would silently misprice every
quote the dashboard gives. So this reports, and Ed decides (his call, 2026-11-08).

Both pages carry the credit block first and the cash block second, with identical labels,
so every pattern below takes its LAST match — that is the cash column.

Sources:
  Fisherman's Processing   https://www.fishermansprocessing.com/           (rate card inline)
  Five Star Fish Processing https://www.fivestar.net/pricing.php

Usage:
  python3 check_rates.py                  # live fetch, write data/rates_check.json
  python3 check_rates.py --offline DIR    # parse saved pages (fp*.html, fs*.html) in DIR
  python3 check_rates.py --html PATH      # planner HTML to read stored rates from

Exit codes: 0 no change · 2 a rate moved · 4 both pages failed to fetch
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

from refresh_multiday import (FETCH_BUDGET_S, fetch, log, norm, now_local, read_json,
                              visible_lines, write_json)

ROOT = Path(__file__).resolve().parent

SOURCES = {
    "fp": {"name": "Fisherman's Processing", "url": "https://www.fishermansprocessing.com/"},
    "fs": {"name": "Five Star Fish Processing", "url": "https://www.fivestar.net/pricing.php"},
}

MONEY_RE = re.compile(r"\$\s?([\d,]+(?:\.\d+)?)")


def money(s: str) -> float | None:
    m = MONEY_RE.search(s or "")
    return float(m.group(1).replace(",", "")) if m else None


def last_match(lines: list[str], pattern: str) -> float | None:
    """The dollar amount on the LAST line matching pattern — i.e. the cash column."""
    rx = re.compile(pattern, re.I)
    hits = [money(l) for l in lines if rx.search(l)]
    hits = [h for h in hits if h is not None]
    return hits[-1] if hits else None


def price_after(lines: list[str], header: str, which: int = 0) -> float | None:
    """The (which+1)-th dollar amount appearing after the LAST line matching header.
    Five Star puts the price on its own line above the description, so a label-bearing
    line cannot carry the figure."""
    rx = re.compile(header, re.I)
    idx = [i for i, l in enumerate(lines) if rx.search(l)]
    if not idx:
        return None
    found = 0
    for l in lines[idx[-1] + 1:]:
        v = money(l)
        if v is not None:
            if found == which:
                return v
            found += 1
    return None


def price_before(lines: list[str], label: str) -> float | None:
    """The nearest dollar amount above the LAST line matching label."""
    rx = re.compile(label, re.I)
    idx = [i for i, l in enumerate(lines) if rx.search(l)]
    if not idx:
        return None
    for l in reversed(lines[:idx[-1]]):
        v = money(l)
        if v is not None:
            return v
    return None


def extract_fp(lines: list[str]) -> dict:
    """Fisherman's labels every rate on the same line as the figure."""
    return {
        "big":      last_match(lines, r"Fish 12 Pounds .* larger"),
        "small":    last_match(lines, r"Fish Under 12 Pounds"),
        "fillet":   last_match(lines, r"^Fillets\b"),
        "gillgut":  price_after(lines, r"^Gill, gut"),
        "collar":   price_after(lines, r"^Collars\s*$"),
        "can":      last_match(lines, r"weighing 15 pounds or more"),
        "smoke":    last_match(lines, r"Mesquite smoke after 6-hour soak"),
        "jerky":    last_match(lines, r"Mesquite smoke after thinly sliced"),
        "box":      last_match(lines, r"21x17x14"),
        "handling": last_match(lines, r"handling fees applied for every location"),
    }


def extract_fs(lines: list[str]) -> dict:
    """Five Star puts each figure on its own line above its description, and splits the
    sheet into 3 mil and 5 mil sections. The calculator quotes 5 mil bags, except smoke
    and jerky, which Five Star publishes only in the 3 mil section."""
    five = price_after(lines, r"^5 MIL", 0)
    return {
        "big":      five,
        "small":    five,          # under 10 lb uses a schedule Five Star does not publish
        # These two label lines carry their own figure, so take the line's amount, not the
        # nearest one above it — and the last such line, which is the cash block's.
        "fillet":   last_match(lines, r"accept fillets at an increased rate"),
        "gillgut":  last_match(lines, r"Gut service is available"),
        "collar":   price_before(lines, r"per a piece for Collars"),
        "can":      price_after(lines, r"^Gourmet Canning", 0),
        "smoke":    price_before(lines, r"per pound for smoking"),
        "jerky":    price_before(lines, r"per pound for jerking"),
        "box":      0.0,           # Five Star quotes shipping separately; no box line
        "handling": 0.0,
    }


EXTRACT = {"fp": extract_fp, "fs": extract_fs}


def stored_rates(html_path: Path) -> tuple[str, dict]:
    """The rates the dashboard is currently quoting, read out of PROCESSORS."""
    s = html_path.read_text(encoding="utf-8")
    m = re.search(r"const RATE_DATE\s*=\s*'([^']*)'", s)
    rate_date = m.group(1) if m else ""
    out: dict[str, dict] = {}
    for blk in re.finditer(r"key:\s*'(\w+)'(.*?)\n\s*\}", s, flags=re.S):
        key, body = blk.group(1), blk.group(2)
        rm = re.search(r"rates:\s*\{(.*?)\}", body, flags=re.S)
        if not rm:
            continue
        rates = {k: float(v) for k, v in re.findall(r"(\w+)\s*:\s*([\d.]+)", rm.group(1))}
        fee = re.search(r"ccFee:\s*([\d.]+)", body)
        out[key] = {"rates": rates, "ccFee": float(fee.group(1)) if fee else None}
    return rate_date, out


def run(args) -> int:
    started = now_local()
    deadline = time.monotonic() + FETCH_BUDGET_S
    html_path = Path(args.html)
    rate_date, stored = stored_rates(html_path)

    per: dict[str, dict] = {}
    for key, src in SOURCES.items():
        info = {"name": src["name"], "status": "ok", "http": None, "error": "",
                "scraped": {}, "stored": {}, "diffs": [], "unreadable": []}
        try:
            if args.offline:
                files = sorted(Path(args.offline).glob(f"{key}*"))
                if not files:
                    raise RuntimeError("no offline fixture")
                body = files[-1].read_text(encoding="utf-8", errors="ignore")
            else:
                status, body = fetch(src["url"], deadline)
                info["http"] = status
                if status != 200:
                    raise RuntimeError(f"http {status}")
            scraped = EXTRACT[key](visible_lines(body))
            if not any(v is not None for v in scraped.values()):
                raise RuntimeError("no rates found on the page")
            info["scraped"] = scraped
            info["stored"] = stored.get(key, {}).get("rates", {})
            for field, want in sorted(info["stored"].items()):
                got = scraped.get(field)
                if got is None:
                    info["unreadable"].append(field)
                elif abs(got - float(want)) > 0.005:
                    info["diffs"].append({"field": field, "stored": float(want), "scraped": got})
        except Exception as e:
            info["status"], info["error"] = "failed", str(e)
            log(f"WARN rates {src['name']}: {e}")
        per[key] = info

    failed = [k for k, v in per.items() if v["status"] != "ok"]
    changed = [k for k, v in per.items() if v["diffs"]]
    outcome = "failed" if len(failed) == len(SOURCES) else ("changed" if changed else "no-change")

    for k, v in per.items():
        if v["status"] != "ok":
            log(f"  {v['name']:26s} FAILED {v['error']}")
            continue
        bits = ", ".join(f"{d['field']} {d['stored']}→{d['scraped']}" for d in v["diffs"])
        log(f"  {v['name']:26s} {'CHANGED' if v['diffs'] else 'no change':10s} "
            f"{bits}{' · unreadable: ' + ','.join(v['unreadable']) if v['unreadable'] else ''}")
    log(f"rates outcome={outcome} stamped={rate_date!r}")

    # Idempotent on disk, the same way refresh_multiday.py exits "already-landed": if the
    # finding is identical to what is already recorded, leave the file alone. Rewriting it
    # for a new timestamp alone would leave the tree dirty after any manual run, and
    # data/rates_check.json is not on the Sunday preflight's ignore list — so a mid-week
    # check would abort the next scheduled run with "dirty-tree". The file answers "what
    # did we last find"; the heartbeat and refresh.log answer "when did we last look".
    out = ROOT / "data" / "rates_check.json"
    new = {"ts": started.isoformat(), "outcome": outcome, "rate_date": rate_date,
           "per_processor": per}
    old = read_json(out, None)
    if isinstance(old, dict) and {k: v for k, v in old.items() if k != "ts"} == \
            {k: v for k, v in new.items() if k != "ts"}:
        log(f"rates unchanged since {old.get('ts', '?')} — {out.name} left as it was")
    else:
        write_json(out, new)
    return {"no-change": 0, "changed": 2, "failed": 4}[outcome]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offline", metavar="DIR", help="parse saved fp*/fs* pages from DIR")
    ap.add_argument("--html", default=str(ROOT / "saltwater_trip_planner.html"))
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
