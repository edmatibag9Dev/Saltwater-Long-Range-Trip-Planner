#!/usr/bin/env python3
"""refresh_multiday.py — pull multi-day boat schedules from the four San Diego landings
and write them into the planner's MULTI-DAY data block.

Sources (all load headlessly, verified 2026-09-03):
  FL  Fisherman's Landing   https://fishermanslanding.fishingreservations.net/resos/?page=N
  SF  Seaforth              https://seaforth.fishingreservations.net/sales/?page=N
  PL  Point Loma            https://www.pointlomasportfishing.com/schedules.php?page=N
  HM  H&M Landing           https://www.hmlanding.com/xolacache?callback=JSON_CALLBACK   (JSONP)

Rules (Ed, 2026-09-03 — see BUILD-PLAN.md):
  * keep trips 1.5 days or longer
  * keep trips returning 5:00 AM – 10:00 AM (inclusive); drop anything returning later
  * drop the long-range boats (they live in the planner's own RAW array)
  * Processing Planner only — Trip Finder never sees these rows

Safety nets (BUILD-PLAN §10):
  * per-request timeout 30 s, 2 retries (10 s, 30 s backoff), 1.5 s spacing between pages
  * whole fetch phase capped at 10 minutes wall clock
  * a landing that fails or parses to 0 rows keeps its previous rows and is marked stale
  * if kept rows fall below 60 % of the previous run → HOLD (CSV to data/hold/, HTML untouched)
  * idempotent: same data as last run → "already-landed", nothing rewritten
  * the script never touches git; the scheduled task does that after tests pass

Usage:
  python3 refresh_multiday.py                 # live fetch, write data/ and the HTML block
  python3 refresh_multiday.py --dry-run       # live fetch, write data/ only, leave HTML alone
  python3 refresh_multiday.py --offline DIR   # parse saved pages in DIR instead of fetching
  python3 refresh_multiday.py --html PATH     # planner HTML to update (default: ./saltwater_trip_planner.html)

Exit codes: 0 landed / already-landed · 2 partial (a landing was stale) · 3 hold · 4 failed
Outcome summary is always written to data/last_run.json for the scheduled task's footer.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html as htmlmod
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"   # overridable with --data
HOLD = DATA / "hold"
LOCAL_TZ = ZoneInfo("America/Los_Angeles")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")

REQUEST_TIMEOUT_S = 30
RETRY_BACKOFF_S = (10, 30)
PAGE_SPACING_S = 1.5
FETCH_BUDGET_S = 10 * 60
MAX_PAGES = 60
MIN_DAYS = 1.5
RET_WINDOW = (dt.time(5, 0), dt.time(10, 0))
HOLD_RATIO = 0.60
DEFAULT_CAP = 20  # matches the planner's charter default when a boat has no known capacity

# Long-range boats live in the planner's RAW array. Any of these names on a landing page is dropped.
LR_BOATS = {
    "shogun", "american angler", "royal star", "independence", "vagabond", "polaris supreme",
    "royal polaris", "excel", "spirit of adventure", "spirit of adv.", "searcher", "intrepid",
}

SOURCES = {
    "FL": {"name": "Fisherman's Landing", "kind": "paged",
           "url": "https://fishermanslanding.fishingreservations.net/resos/?page={page}"},
    "SF": {"name": "Seaforth", "kind": "paged",
           "url": "https://seaforth.fishingreservations.net/sales/?page={page}"},
    "PL": {"name": "Point Loma Sportfishing", "kind": "paged",
           "url": "https://www.pointlomasportfishing.com/schedules.php?page={page}"},
    "HM": {"name": "H&M Landing", "kind": "jsonp",
           "url": "https://www.hmlanding.com/xolacache?callback=JSON_CALLBACK&nocache={nonce}"},
}

CSV_FIELDS = ["landing", "boat", "ttype", "days", "dep", "deptime", "ret", "rettime",
              "cap", "cap_source", "spots", "price", "src"]

MARK_START = "// ══ MULTI-DAY DATA START"
MARK_END = "// ══ MULTI-DAY DATA END"


# ----------------------------------------------------------------------------- helpers
def log(msg: str) -> None:
    print(msg, flush=True)


def now_local() -> dt.datetime:
    return dt.datetime.now(LOCAL_TZ).replace(microsecond=0)


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def fetch(url: str, deadline: float) -> tuple[int, str]:
    """GET with UA, timeout, and two retries. Returns (status, body). status 0 = network error."""
    attempts = 1 + len(RETRY_BACKOFF_S)
    for i in range(attempts):
        if time.monotonic() > deadline:
            return 0, "fetch budget exhausted"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
                return r.status, r.read().decode("utf-8", "ignore")
        except urllib.error.HTTPError as e:
            status, body = e.code, ""
        except Exception as e:  # timeout, DNS, connection reset
            status, body = 0, str(e)
        if i < len(RETRY_BACKOFF_S):
            time.sleep(RETRY_BACKOFF_S[i])
    return status, body


def is_captcha(body: str) -> bool:
    return bool(re.search(r"<title>\s*Validation request", body, flags=re.I))


# ----------------------------------------------------------------------------- HTML landings
DATE_RE = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\. (\d{1,2})-(\d{1,2})-(20\d\d)$")
TIME_RE = re.compile(r"^\d{1,2}:\d{2} (AM|PM)$")
DAYHDR_RE = re.compile(r"^(Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day, [A-Z][a-z]+ \d{1,2}, 20\d\d$")
TAG_LINES = {"charter", "passport required", "meals included in price",
             "permits included in price", "trip info", "chartered"}


def visible_lines(page: str) -> list[str]:
    s = re.sub(r"<script.*?</script>|<style.*?</style>", "", page, flags=re.S)
    t = htmlmod.unescape(re.sub(r"<[^>]+>", "\n", s))
    return [l.strip() for l in t.split("\n") if l.strip()]


def boat_options(page: str) -> set[str]:
    m = re.search(r"<select[^>]*name=['\"]boat_filter\[\]['\"][^>]*>(.*?)</select>", page, flags=re.S)
    if not m:
        return set()
    opts = re.findall(r"<option[^>]*>(.*?)</option>", m.group(1), flags=re.S)
    return {norm(htmlmod.unescape(re.sub(r"<[^>]+>", "", o))) for o in opts}


def mdy(m: re.Match) -> str:
    return f"{m.group(4)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def parse_landing_page(code: str, page: str, src: str) -> list[dict]:
    """Positional parser for the fishingreservations.net-style schedule pages.
    Row grammar (visible text): [boat] [trip type] [tags…] [dep date] [Check In…]? [dep time]
                               [ret date] [ret time]? then either 'Chartered' or [cap] [$price] [spots]."""
    L = visible_lines(page)
    known = boat_options(page)
    rows: list[dict] = []
    i = 0
    while i < len(L):
        m = DATE_RE.match(L[i])
        if not m:
            i += 1
            continue
        off = 1
        if i + 1 < len(L) and L[i + 1].lower().startswith("check in"):
            off = 2
        if not (i + off < len(L) and TIME_RE.match(L[i + off])):
            i += 1
            continue
        # back-scan for boat + trip type
        back: list[str] = []
        j = i - 1
        while j >= 0 and len(back) < 8 and not DATE_RE.match(L[j]) and not TIME_RE.match(L[j]):
            back.append(L[j])
            j -= 1
        back = [b for b in reversed(back)
                if norm(b) not in TAG_LINES and not b.lower().startswith("check in")
                and not DAYHDR_RE.match(b)]
        boat = ttype = ""
        if known:
            for k in range(len(back) - 1, -1, -1):
                if norm(back[k]) in known:
                    boat = back[k]
                    ttype = back[k + 1] if k + 1 < len(back) else ""
                    break
        if not boat and len(back) >= 2:
            boat, ttype = back[-2], back[-1]
        dep, deptime = mdy(m), L[i + off]
        k = i + off + 1
        ret = rettime = ""
        if k < len(L) and DATE_RE.match(L[k]):
            ret = mdy(DATE_RE.match(L[k]))
            k += 1
            if k < len(L) and TIME_RE.match(L[k]):
                rettime = L[k]
                k += 1
        cap = price = spots = ""
        if k < len(L) and L[k] == "Chartered":
            spots = "Chartered"
            k += 1
        else:
            if k < len(L) and re.fullmatch(r"\d+", L[k]):
                cap = L[k]
                k += 1
            if k < len(L) and L[k].startswith("$"):
                price = L[k]
                k += 1
            if k < len(L) and (re.fullmatch(r"\d+", L[k]) or L[k] in ("Full", "Waitlist Only", "Sold Out")):
                spots = L[k]
                k += 1
        rows.append(dict(landing=code, boat=boat, ttype=ttype, dep=dep, deptime=deptime,
                         ret=ret, rettime=rettime, cap=cap, spots=spots, price=price, src=src))
        i = k
    return rows


def has_next_page(page: str, page_no: int) -> bool:
    return f"page={page_no + 1}" in page


# ----------------------------------------------------------------------------- H&M JSONP
def parse_hm(body: str, src: str) -> list[dict]:
    m = re.search(r"\((\{.*\})\)\s*;?\s*$", body, flags=re.S)
    d = json.loads(m.group(1) if m else body)
    exps = d.get("experiences", {}) or {}
    rows: list[dict] = []
    for t in d.get("trips", []) or []:
        x = exps.get(t.get("expId"), {}) or {}
        name = x.get("name", "") or ""
        parts = [p.strip() for p in name.split(" - ")]
        boat = parts[0] if parts else ""
        ttype = " - ".join(parts[1:]) if len(parts) > 1 else ""
        try:
            dep_dt = dt.datetime.fromisoformat(t["datetime"].replace("Z", "+00:00")).astimezone(LOCAL_TZ)
        except Exception:
            continue
        dur = x.get("eventDuration") or x.get("duration")
        ret_dt = dep_dt + dt.timedelta(minutes=int(dur)) if dur else None
        open_s = t.get("open_spots")
        res_s = t.get("reserved_spots")
        cap = ""
        if isinstance(open_s, int) and isinstance(res_s, int) and open_s + res_s > 0:
            cap = str(open_s + res_s)
        else:
            try:
                cap = str(x["resources"][0]["resource"]["capacity"])
            except Exception:
                cap = str((x.get("group") or {}).get("max") or "")
        spots = "Full" if open_s == 0 else (str(open_s) if isinstance(open_s, int) else "")
        price = f"${t['price']}" if t.get("price") not in (None, "") else ""
        rows.append(dict(landing="HM", boat=boat, ttype=ttype,
                         dep=dep_dt.strftime("%Y-%m-%d"), deptime=dep_dt.strftime("%-I:%M %p"),
                         ret=ret_dt.strftime("%Y-%m-%d") if ret_dt else "",
                         rettime=ret_dt.strftime("%-I:%M %p") if ret_dt else "",
                         cap=cap, spots=spots, price=price, src=src))
    return rows


# ----------------------------------------------------------------------------- rules
DAYS_RE = re.compile(r"(?<![\d/.])(\d+(?:\.\d+)?)\s*[- ]?Day", flags=re.I)


def trip_days(row: dict) -> float | None:
    """Trip length in days: the number in the trip type wins; else derive from the dates."""
    m = DAYS_RE.search(row.get("ttype", ""))
    if m:
        return float(m.group(1))
    tt = norm(row.get("ttype", ""))
    if "overnight" in tt:
        return 1.0
    try:
        d0 = dt.datetime.strptime(f"{row['dep']} {row['deptime']}", "%Y-%m-%d %I:%M %p")
        d1 = dt.datetime.strptime(f"{row['ret']} {row['rettime']}", "%Y-%m-%d %I:%M %p")
        return round((d1 - d0).total_seconds() / 86400, 2)
    except Exception:
        return None


def ret_time(row: dict) -> dt.time | None:
    try:
        return dt.datetime.strptime(row["rettime"], "%I:%M %p").time()
    except Exception:
        return None


def keep(row: dict) -> tuple[bool, str]:
    if norm(row["boat"]) in LR_BOATS:
        return False, "long-range boat"
    if not row.get("ret") or not row.get("rettime"):
        return False, "no return date/time"
    d = trip_days(row)
    if d is None:
        return False, "trip length unknown"
    if d < MIN_DAYS:
        return False, f"{d} days < {MIN_DAYS}"
    t = ret_time(row)
    if t is None or not (RET_WINDOW[0] <= t <= RET_WINDOW[1]):
        return False, f"return {row['rettime']} outside 5–10 AM"
    return True, ""


def dedupe(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        key = (r["landing"], norm(r["boat"]), r["dep"], r["deptime"], norm(r["ttype"]))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


# ----------------------------------------------------------------------------- data files
def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CSV_FIELDS})


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def apply_capacity(rows: list[dict], cap_table: dict) -> dict:
    """Fill missing capacities from the per-boat max seen (this run ∪ persisted table)."""
    for r in rows:
        if r.get("cap"):
            key = f"{r['landing']}|{norm(r['boat'])}"
            cap_table[key] = max(int(cap_table.get(key, 0)), int(r["cap"]))
    for r in rows:
        if r.get("cap"):
            r["cap_source"] = "listed"
            continue
        key = f"{r['landing']}|{norm(r['boat'])}"
        if cap_table.get(key):
            r["cap"], r["cap_source"] = str(cap_table[key]), "boat-max"
        else:
            r["cap"], r["cap_source"] = str(DEFAULT_CAP), "default"
    return cap_table


# ----------------------------------------------------------------------------- HTML block
LANDING_LABEL = {"FL": "Fisherman's Landing", "HM": "H&M Landing",
                 "PL": "Point Loma Sportfishing", "SF": "Seaforth"}


def js_str(s: str) -> str:
    return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'"


def render_block(rows: list[dict], as_of: str, sources: dict) -> str:
    lines = [f"{MARK_START} (auto-generated by refresh_multiday.py — do not hand-edit) ══",
             f"const MULTI_AS_OF = '{as_of}';",
             "const MULTI_SOURCES = " + json.dumps(
                 {k: {"label": LANDING_LABEL[k], "as_of": v.get("last_good", ""), "status": v.get("status", "")}
                  for k, v in sorted(sources.items())}, separators=(",", ":")) + ";",
             "// [landing, boat, tripType, days, deptDate, deptTime, retDate, retTime, cap, spots]",
             "const MULTI = ["]
    for r in sorted(rows, key=lambda r: (r["ret"], r["rettime"], r["landing"], r["boat"])):
        lines.append("[" + ",".join([
            js_str(r["landing"]), js_str(r["boat"]), js_str(r["ttype"]), str(trip_days(r)),
            js_str(r["dep"]), js_str(r["deptime"]), js_str(r["ret"]), js_str(r["rettime"]),
            str(int(r["cap"])), js_str(r["spots"])]) + "],")
    lines.append("];")
    lines.append(f"{MARK_END} ══")
    return "\n".join(lines)


def write_block(html_path: Path, block: str) -> bool:
    s = html_path.read_text(encoding="utf-8")
    a, b = s.find(MARK_START), s.find(MARK_END)
    if a < 0 or b < 0:
        return False
    b_end = s.find("\n", b)
    new = s[:a] + block + s[b_end:]
    html_path.write_text(new, encoding="utf-8")
    return True


# ----------------------------------------------------------------------------- main
def run(args) -> int:
    global DATA, HOLD
    if getattr(args, "data", None):
        DATA = Path(args.data)
        HOLD = DATA / "hold"
    started = now_local()
    deadline = time.monotonic() + FETCH_BUDGET_S
    DATA.mkdir(exist_ok=True)
    prev_kept = read_csv(DATA / "multiday_trips.csv")
    prev_sources = read_json(DATA / "sources.json", {})
    cap_table = read_json(DATA / "boat_capacity.json", {})
    sources: dict = {}
    raw_all: list[dict] = []

    for code, src in SOURCES.items():
        info = {"name": src["name"], "status": "ok", "http": [], "pages": 0, "rows_raw": 0,
                "rows_kept": 0, "fetched_at": started.isoformat(),
                "last_good": (prev_sources.get(code) or {}).get("last_good", "")}
        rows: list[dict] = []
        try:
            if args.offline:
                files = sorted(Path(args.offline).glob(f"{code}_*"))
                if not files:
                    raise RuntimeError("no offline fixture")
                for f in files:
                    body = f.read_text(encoding="utf-8", errors="ignore")
                    rows += parse_hm(body, f.name) if src["kind"] == "jsonp" else parse_landing_page(code, body, f.name)
                    info["pages"] += 1
            elif src["kind"] == "jsonp":
                status, body = fetch(src["url"].format(nonce=time.time()), deadline)
                info["http"].append(status)
                if status != 200:
                    raise RuntimeError(f"http {status}")
                rows = parse_hm(body, "xolacache")
                info["pages"] = 1
            else:
                for p in range(1, MAX_PAGES + 1):
                    if time.monotonic() > deadline:
                        raise RuntimeError("fetch budget exhausted")
                    status, body = fetch(src["url"].format(page=p), deadline)
                    info["http"].append(status)
                    if status != 200:
                        raise RuntimeError(f"http {status} on page {p}")
                    if is_captcha(body):
                        raise RuntimeError(f"captcha page on page {p}")
                    page_rows = parse_landing_page(code, body, f"page{p}")
                    info["pages"] += 1
                    rows += page_rows
                    if not page_rows or not has_next_page(body, p):
                        break
                    time.sleep(PAGE_SPACING_S)
            if not rows:
                raise RuntimeError("parsed 0 rows")
            info["rows_raw"] = len(rows)
            info["last_good"] = started.strftime("%Y-%m-%d")
        except Exception as e:
            info["status"], info["error"] = "stale", str(e)
            rows = [r for r in prev_kept if r["landing"] == code]
            info["rows_raw"] = len(rows)
            log(f"WARN {code} {src['name']}: {e} — keeping {len(rows)} previous rows")
        sources[code] = info
        raw_all += rows

    raw_all = dedupe(raw_all)
    kept, dropped = [], []
    for r in raw_all:
        ok, why = keep(r)
        (kept if ok else dropped).append(dict(r, drop=why))
    cap_table = apply_capacity(kept, cap_table)
    for r in kept:
        r["days"] = trip_days(r)
    for code in sources:
        sources[code]["rows_kept"] = sum(1 for r in kept if r["landing"] == code)

    stale = [c for c, v in sources.items() if v["status"] != "ok"]
    prev_n = len(prev_kept)
    outcome = "landed"
    if len(stale) == len(SOURCES):
        outcome = "failed"
    elif prev_n and len(kept) < HOLD_RATIO * prev_n:
        outcome = "hold"
    elif stale:
        outcome = "partial"

    digest = hashlib.sha256("\n".join(
        "|".join(str(r.get(k, "")) for k in CSV_FIELDS if k != "src") for r in
        sorted(kept, key=lambda r: (r["ret"], r["rettime"], r["landing"], r["boat"], r["dep"]))
    ).encode()).hexdigest()[:16]
    prev_digest = read_json(DATA / "last_run.json", {}).get("digest")

    as_of = started.strftime("%Y-%m-%d")
    summary = {
        "ts": started.isoformat(), "outcome": outcome, "digest": digest,
        "rows_kept": len(kept), "rows_raw": len(raw_all), "prev_rows_kept": prev_n,
        "per_landing": {c: {"status": v["status"], "raw": v["rows_raw"], "kept": v["rows_kept"],
                             "pages": v["pages"], "error": v.get("error", "")} for c, v in sources.items()},
        "html_written": False, "dry_run": bool(args.dry_run),
    }

    if outcome == "failed":
        log("FAILED: every source failed — nothing written except the log")
    elif outcome == "hold":
        HOLD.mkdir(parents=True, exist_ok=True)
        write_csv(HOLD / f"{as_of}.csv", kept)
        log(f"HOLD: kept {len(kept)} rows vs {prev_n} last run (< {int(HOLD_RATIO*100)}%) — HTML untouched, CSV in data/hold/")
    else:
        if outcome == "landed" and prev_digest == digest and not args.force:
            outcome = "already-landed"
            summary["outcome"] = outcome
            log(f"already-landed: data unchanged since last run (digest {digest})")
        write_csv(DATA / "multiday_trips.csv", kept)
        write_csv(DATA / "landing_trips_raw.csv", raw_all)
        write_json(DATA / "boat_capacity.json", cap_table)
        write_json(DATA / "sources.json", sources)
        if outcome != "already-landed" and not args.dry_run:
            html_path = Path(args.html)
            if html_path.exists() and write_block(html_path, render_block(kept, as_of, sources)):
                summary["html_written"] = True
                log(f"HTML block written to {html_path.name} ({len(kept)} rows, as of {as_of})")
            else:
                log(f"NOTE: markers not found in {html_path} — HTML untouched (data files updated)")

    for c, v in sources.items():
        log(f"  {c} {v['name']:24s} {v['status']:6s} pages={v['pages']:2d} raw={v['rows_raw']:4d} kept={v['rows_kept']:4d} {v.get('error','')}")
    log(f"outcome={outcome} kept={len(kept)} raw={len(raw_all)} dropped={len(dropped)} digest={digest}")

    write_json(DATA / "last_run.json", summary)
    with (DATA / "refresh.log").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": summary["ts"], "outcome": outcome, "kept": len(kept), "raw": len(raw_all),
                             "per_landing": {c: f"{v['status']}:{v['rows_kept']}" for c, v in sources.items()},
                             "html_written": summary["html_written"]}) + "\n")
    return {"landed": 0, "already-landed": 0, "partial": 2, "hold": 3, "failed": 4}[outcome]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="write data/ only; never touch the HTML")
    ap.add_argument("--offline", metavar="DIR", help="parse saved pages named <CODE>_*.html / HM_*.txt from DIR")
    ap.add_argument("--html", default=str(ROOT / "saltwater_trip_planner.html"))
    ap.add_argument("--force", action="store_true", help="rewrite even if data is unchanged")
    ap.add_argument("--data", metavar="DIR", help="data directory (default: ./data)")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
