#!/usr/bin/env python3
"""refresh_multiday.py — refresh both of the planner's trip-data blocks.

Two independent surfaces, one run:

MULTI-DAY (the four San Diego landings → the MULTI block, Processing Planner only)
  FL  Fisherman's Landing   https://fishermanslanding.fishingreservations.net/resos/?page=N
  SF  Seaforth              https://seaforth.fishingreservations.net/sales/?page=N
  PL  Point Loma            https://www.pointlomasportfishing.com/schedules.php?page=N
  HM  H&M Landing           https://www.hmlanding.com/xolacache?callback=JSON_CALLBACK   (JSONP)
  Rules (Ed, 2026-09-03 — see BUILD-PLAN.md): keep trips 1.5 days or longer, returning
  5:00–10:00 AM inclusive; drop the long-range boats; never shown in Trip Finder.

LONG-RANGE (the 11 long-range boats → the RAW block, both tabs)
  https://<boat>.fishingreservations.net/sales/  for each boat in BOAT_SOURCES
  Added 2026-11-08. These pages were thought to CAPTCHA headless requests (AGENTS.md
  Rule 6) and RAW was maintained by hand through the Chrome-tab workaround until it had
  drifted four months. They are the same platform as the Seaforth and Fisherman's pages
  and all 11 load headlessly, so RAW is now refreshed here too. RAW holds curation the
  page cannot supply — Ed's 'ed' flag, his shortened trip names, and departed trips — and
  all three are carried forward.

Safety nets (BUILD-PLAN §10):
  * per-request timeout 30 s, 2 retries (10 s, 30 s backoff), 1.5 s spacing between pages
  * each surface gets its own 10-minute fetch budget
  * a landing or boat that fails, CAPTCHAs, or parses to 0 rows keeps its previous rows
    and is marked stale
  * multi-day: kept rows below 60 % of the previous run → HOLD (CSV to data/hold/)
  * long-range: the same 60 % collapse guard, judged PER BOAT, so one boat emptying cannot
    hide behind the other ten
  * long-range rows are written only when every field parsed cleanly; anything else keeps
    its previous RAW values and is counted as "unresolved", so a per-boat page quirk is
    reported as a number rather than published as wrong trip data. A handful of those is
    the steady state; only above 5 % of scraped rows does it make the run partial.
  * a future trip that vanished from a healthy page is treated as cancelled, dropped, and
    logged by name
  * idempotent per surface: unchanged data → "already-landed", nothing rewritten
  * the script never touches git; the scheduled task does that after tests pass

Usage:
  python3 refresh_multiday.py                   # live fetch, write data/ and both blocks
  python3 refresh_multiday.py --dry-run         # live fetch, write data/ only, leave HTML alone
  python3 refresh_multiday.py --offline DIR     # parse saved pages in DIR instead of fetching
  python3 refresh_multiday.py --skip-longrange  # multi-day only
  python3 refresh_multiday.py --html PATH       # planner HTML (default: ./saltwater_trip_planner.html)

Exit code is the worse of the two surfaces:
  0 landed / already-landed · 2 partial (something stale or unresolved) · 3 hold · 4 failed
data/last_run.json always carries the outcome, with per-surface detail under
"multiday" and "longrange" for the scheduled task's report.
"""
from __future__ import annotations

import argparse
import collections
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
# Share of scraped long-range rows that may fail lr_row_ok before the run counts as partial.
UNRESOLVED_PARTIAL_RATIO = 0.05

# Long-range boats live in the planner's RAW array. Any of these names on a landing page is dropped.
LR_BOATS = {
    "shogun", "american angler", "royal star", "independence", "vagabond", "polaris supreme",
    "royal polaris", "excel", "spirit of adventure", "spirit of adv.", "searcher", "intrepid",
}

# Long-range boats, in the planner's own BOATS order — boatIdx in RAW is the index here.
# Their /sales/ pages were verified to load headlessly (HTTP 200, no CAPTCHA) on 2026-11-08,
# with the same UA and spacing the landings use; see AGENTS.md Rule 6.
BOAT_SOURCES = [
    {"slug": "shogun", "name": "Shogun"},
    {"slug": "americanangler", "name": "American Angler"},
    {"slug": "royalstar", "name": "Royal Star"},
    {"slug": "independence", "name": "Independence"},
    {"slug": "vagabond", "name": "Vagabond"},
    {"slug": "polarissupreme", "name": "Polaris Supreme"},
    {"slug": "royalpolaris", "name": "Royal Polaris"},
    {"slug": "excel", "name": "Excel"},
    {"slug": "soa", "name": "Spirit of Adv."},
    {"slug": "searcher", "name": "Searcher"},
    {"slug": "intrepid", "name": "Intrepid"},
]
LR_URL = "https://{slug}.fishingreservations.net/sales/"

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
LR_MARK_START = "// ══ LONG-RANGE DATA START"
LR_MARK_END = "// ══ LONG-RANGE DATA END"

LR_CSV_FIELDS = ["idx", "boat", "name", "dep", "days", "cap", "spots", "price", "flags", "src", "note"]


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


def carry_forward(prev_kept: list[dict], kept: list[dict], sources: dict, today: str) -> list[dict]:
    """Rows from the previous run that already departed but have not returned, missing from
    this fetch because the landing no longer lists departed trips. Only for landings that
    fetched OK (stale landings already reuse all their previous rows)."""
    have = {(r["landing"], norm(r["boat"]), r["dep"], r["deptime"]) for r in kept}
    out = []
    for r in prev_kept:
        if sources.get(r["landing"], {}).get("status") != "ok":
            continue
        if r["dep"] < today and r["ret"] >= today and (r["landing"], norm(r["boat"]), r["dep"], r["deptime"]) not in have:
            out.append(dict(r, src="carried", drop=""))
    return out


# ----------------------------------------------------------------------------- data files
def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or CSV_FIELDS
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


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


def write_block(html_path: Path, block: str, start: str = MARK_START, end: str = MARK_END) -> bool:
    s = html_path.read_text(encoding="utf-8")
    a, b = s.find(start), s.find(end)
    if a < 0 or b < 0:
        return False
    b_end = s.find("\n", b)
    new = s[:a] + block + s[b_end:]
    html_path.write_text(new, encoding="utf-8")
    return True


def stamp_readme(readme: Path, as_of: str, label: str = "Last multi-day refresh") -> bool:
    """Keep a README freshness line in step with the data (CONTRIBUTING: every data commit updates the README)."""
    if not readme.exists():
        return False
    s = readme.read_text(encoding="utf-8")
    new = re.sub(r"(\*\*" + re.escape(label) + r":\*\* )\d{4}-\d{2}-\d{2}", r"\g<1>" + as_of, s, count=1)
    if new == s:
        return False
    readme.write_text(new, encoding="utf-8")
    return True


# ============================================================================ long-range
# The 11 long-range boats live in the planner's RAW array. Until 2026-11-08 this array was
# maintained by hand through the Chrome-tab workaround (AGENTS.md Rule 6) and had drifted
# four months. Their /sales/ pages are the same fishingreservations.net platform the
# Seaforth and Fisherman's landing pages use, and they load headlessly, so the refresh now
# covers them too. What makes this different from the multi-day path:
#   * the boat name is NOT in the row — it comes from BOAT_SOURCES
#   * the page carries two price columns (Check and Credit); only the cash one is stored
#   * RAW holds hand-curated values the page cannot supply: Ed's 'ed' flag, his shortened
#     trip names, and trips that already departed. All three are carried forward.
#   * availability wording varies by boat far more than on the landing pages, so a row is
#     only written when every field parsed cleanly (lr_row_ok); otherwise the previous RAW
#     row is kept and the row is counted as unresolved in the run summary. A parser quirk
#     therefore shows up as a number in the Slack line, never as silently wrong trip data.

MONTHHDR_RE = re.compile(r"^[A-Z][a-z]+, 20\d\d$")
DAYS_TOKEN_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*[- ]?Day", re.I)
PRICE_TOKEN_RE = re.compile(r"^\$[\d,]+(?:\.\d+)?")
LR_INVITE_RE = re.compile(r"invitation code is required", re.I)

# Availability wording, pooled from all 11 pages on 2026-11-08. RAW's spots encoding is
# documented in the planner: -2 in progress · -1 charter/private · 0 wait list · N open.
LR_FULL_WORDS = {"full", "join wait list", "join waitlist", "join the wait list",
                 "join the waitlist", "wait list", "waitlist only", "sold out", "-"}
LR_CHARTER_WORDS = {"charter", "chartered", "private", "private charter", "closed charter"}
LR_PROGRESS_WORDS = {"in progress", "trip in progress", "trip in", "out", "at sea"}
# Lines that sit between the trip name and the N Day token on some boats and must be
# stepped over rather than ending the name. A bare '-' is Excel's and Polaris Supreme's
# name separator; it is ALSO a wait-list token in the availability slot, which is why it
# is skipped here and still listed in LR_FULL_WORDS.
LR_NAME_SKIP = ({"-", "passport required", "meals included in price",
                 "permits included in price", "trip info"} | LR_CHARTER_WORDS)


def js_rows(src: str) -> list[list]:
    """Read a JS array-of-arrays literal into Python lists.

    Quote-aware on purpose: a regex that rewrites '...' spans mangles apostrophes inside
    double-quoted names ("Ken's Custom Reels"), which is 52 of RAW's rows.
    """
    rows: list[list] = []
    i, n = 0, len(src)
    while i < n:
        if src[i] != "[":
            i += 1
            continue
        depth, j, toks, cur, q = 0, i, [], "", None
        while j < n:
            c = src[j]
            if q:
                if c == "\\" and j + 1 < n:
                    cur += src[j + 1]
                    j += 2
                    continue
                if c == q:
                    toks.append(("s", cur))
                    cur, q = "", None
                else:
                    cur += c
                j += 1
                continue
            if c in "\"'":
                # Discard whatever sat between the comma and the quote: in an array literal
                # that is only the alignment padding RAW's hand-written rows are full of
                # ([0,'Open 3-Day',           '2026-06-02',...]). Keeping it prepends spaces
                # to the string that follows.
                cur, q = "", c
                j += 1
                continue
            if c == "[":
                depth += 1
                if depth > 1:
                    toks.append(("[", None))
                j += 1
                continue
            if c == "]":
                depth -= 1
                if cur.strip():
                    toks.append(("n", cur.strip()))
                    cur = ""
                if depth == 0:
                    rows.append(toks)
                    j += 1
                    break
                toks.append(("]", None))
                j += 1
                continue
            if c == ",":
                if cur.strip():
                    toks.append(("n", cur.strip()))
                    cur = ""
                j += 1
                continue
            cur += c
            j += 1
        i = max(j, i + 1)
    out: list[list] = []
    for toks in rows:
        vals: list = []
        flags: list[str] = []
        in_flags = False
        for kind, v in toks:
            if kind == "[":
                in_flags = True
            elif kind == "]":
                in_flags = False
                vals.append(flags)
                flags = []
            elif kind == "s":
                (flags if in_flags else vals).append(v)
            elif kind == "n":
                try:
                    vals.append(float(v) if "." in v else int(v))
                except ValueError:
                    pass
        if len(vals) >= 7 and isinstance(vals[0], int):
            if len(vals) == 7:
                vals.append([])
            out.append(vals[:8])
    return out


def read_raw_rows(html: str) -> list[dict]:
    """Current RAW rows as dicts. Works before the markers exist and after."""
    a = html.find(LR_MARK_START)
    src = html[a:html.find(LR_MARK_END, a)] if a >= 0 else html
    m = re.search(r"const RAW\s*=\s*\[", src)
    if not m:
        return []
    start, depth = m.end() - 1, 0
    for k in range(start, len(src)):
        if src[k] == "[":
            depth += 1
        elif src[k] == "]":
            depth -= 1
            if depth == 0:
                return [dict(idx=r[0], name=r[1], dep=r[2], days=r[3], cap=r[4],
                             spots=r[5], price=r[6], flags=list(r[7] or []))
                        for r in js_rows(src[start + 1:k])
                        if isinstance(r[1], str) and isinstance(r[2], str)]
    return []


def lr_spots(avail: str, has_price: bool, cap: int | None) -> int | None:
    """Map a boat page's availability cell to RAW's spots encoding, or None if unreadable.

    A row with neither a price nor a capacity is a closed charter however its availability
    cell reads — American Angler, Spirit of Adventure and Vagabond all print a bare '-'
    there, which would otherwise be read as 'wait list'.
    """
    w = norm(avail)
    if not has_price and cap is None:
        return -1
    if w in LR_CHARTER_WORDS:
        return -1
    if w in LR_PROGRESS_WORDS:
        return -2
    if w in LR_FULL_WORDS:
        return 0
    if re.fullmatch(r"\d+", w):
        return int(w)
    # Excel prints a bare 'OPEN' with no count. Assumption: a trip marked open with a known
    # capacity and no bookings shown is wholly open, so the capacity is the spot count.
    if w in ("open", "open for sign-up") and cap is not None:
        return int(cap)
    return None


def parse_boat_page(boat_idx: int, boat_name: str, page: str, src: str) -> list[dict]:
    """Rows from one long-range boat's /sales/ page.

    Row grammar in visible text, verified across all 11 boats on 2026-11-08:
        [trip name, one or more lines] [N Day] dep-date dep-time
        [ret-date ret-time]? [cap] [$price Check]? [$price Credit]? [availability]

    Two traps this is built around:
      * DATE_RE also matches a RETURN date, which is likewise followed by a time line, so
        anchoring on a date alone invents phantom trips. A departure row always has an
        'N Day' token in its back-scan and a return date never does — the N Day token, not
        the date, is what makes a row real.
      * The trip name wraps over several lines ('PENN SPONSORED ULTRA LIMITED LOAD' +
        '**DEFINTE GO**'), so the name is every name-ish line before that token.
    """
    L = visible_lines(page)
    rows: list[dict] = []
    i = 0
    while i < len(L):
        m = DATE_RE.match(L[i])
        if not m or not (i + 1 < len(L) and TIME_RE.match(L[i + 1])):
            i += 1
            continue
        days: float | None = None
        name_lines: list[str] = []
        skipped_lines: list[str] = []
        invite = False
        j = i - 1
        while j >= 0 and i - j <= 7:
            t = L[j]
            if DATE_RE.match(t) or TIME_RE.match(t):
                break
            dm = DAYS_TOKEN_RE.match(t)
            if dm and days is None:
                days = float(dm.group(1))
                j -= 1
                continue
            if days is not None:
                if (MONTHHDR_RE.match(t) or PRICE_TOKEN_RE.match(t)
                        or re.fullmatch(r"\d+", t) or len(t) > 80):
                    break
                if LR_INVITE_RE.search(t):
                    invite = True
                elif norm(t) not in LR_NAME_SKIP and norm(t) not in LR_FULL_WORDS \
                        and norm(t) not in LR_PROGRESS_WORDS and norm(t) != norm(boat_name):
                    name_lines.append(t)
                elif norm(t) != "-" and norm(t) != norm(boat_name):
                    skipped_lines.append(t)
            j -= 1
        if days is None:                      # not a departure row (usually a return date)
            i += 1
            continue
        seen: set[str] = set()
        parts: list[str] = []
        for t in reversed(name_lines or skipped_lines):
            # name_lines is empty when every line before the N Day token was a charter word
            # — but on these rows that word IS the trip name ('CLOSED CHARTER', 'PRIVATE'),
            # so fall back to what the filter threw away rather than emit a nameless row.
            if norm(t) in seen:
                continue
            seen.add(norm(t))
            parts.append(t)
        dep = mdy(m)
        k = i + 2
        if k < len(L) and DATE_RE.match(L[k]):
            k += 1
            if k < len(L) and TIME_RE.match(L[k]):
                k += 1
        cap: int | None = None
        price = avail = ""
        if k < len(L) and re.fullmatch(r"\d+", L[k]):
            cap = int(L[k])
            k += 1
        if k < len(L) and PRICE_TOKEN_RE.match(L[k]):
            price = PRICE_TOKEN_RE.match(L[k]).group(0)
            k += 1
            if k < len(L) and PRICE_TOKEN_RE.match(L[k]) and L[k].rstrip().endswith("Credit"):
                k += 1                        # the card column is derived, never stored
        if k < len(L) and not DATE_RE.match(L[k]) and not MONTHHDR_RE.match(L[k]) \
                and not DAYS_TOKEN_RE.match(L[k]) and len(L[k]) <= 40:
            avail = L[k]
            k += 1
        spots = lr_spots(avail, bool(price), cap)
        if spots == -1:                       # charter: the planner's own convention
            cap, price = None, "Charter"
        rows.append(dict(idx=boat_idx, boat=boat_name, name=" ".join(parts), dep=dep,
                         days=days, cap=cap, spots=spots, price=price,
                         flags=["invite"] if invite else [], avail=avail, src=src))
        i = max(k, i + 1)
    return rows


def lr_row_ok(r: dict) -> tuple[bool, str]:
    """A scraped row is written only if every field read cleanly. Anything else keeps the
    previous RAW values, so a per-boat page quirk is reported rather than published."""
    if not r.get("name"):
        return False, "no trip name"
    if r.get("days") is None or not (0.5 <= float(r["days"]) <= 30):
        return False, f"implausible trip length {r.get('days')}"
    if r.get("spots") is None:
        return False, f"unreadable availability {r.get('avail')!r}"
    charter = r["spots"] in (-1, -2)
    if r.get("cap") is None and not charter:
        return False, "no capacity"
    if r.get("cap") is not None and not (1 <= int(r["cap"]) <= 60):
        return False, f"implausible capacity {r['cap']}"
    if r.get("cap") is not None and r["spots"] > int(r["cap"]):
        return False, f"spots {r['spots']} > capacity {r['cap']}"
    # A blank price is NOT a gate failure. Several boats list a trip before pricing it
    # (Searcher's "Open for 2027 Sign-Up!" trips), and hiding a real trip is worse than
    # showing one with no price — the page links straight to the boat's booking system.
    # run_longrange fills the gap from the previous RAW row, or with an em dash.
    return True, ""


def render_raw_block(rows: list[dict], as_of: str, boats: list[dict]) -> str:
    lines = [f"{LR_MARK_START} (auto-generated by refresh_multiday.py — do not hand-edit) ══",
             f"const LR_AS_OF = '{as_of}';",
             "const LR_SOURCES = " + json.dumps(
                 [{"label": b["name"], "as_of": b.get("last_good", ""), "status": b.get("status", "")}
                  for b in boats], separators=(",", ":")) + ";",
             "// boatIdx indexes the BOATS array above, which stays hand-maintained — it only",
             "// changes when a boat joins the fleet. tests/test_refresh_multiday.py asserts that",
             "// BOATS and refresh_multiday.py's BOAT_SOURCES stay in the same order.",
             "// Format: [boatIdx, name, deptDate(YYYY-MM-DD), days, capacity, spots, price, flags]",
             "// spots: -1=charter/private, 0=waitlist/full, 1/2/3=low, 4+=open spots, -2=inProgress",
             "// flags: array of strings: 'invite','ed'",
             "const RAW = ["]
    for r in sorted(rows, key=lambda r: (r["idx"], r["dep"], norm(str(r["name"])))):
        days = float(r["days"])
        lines.append("[" + ",".join([
            str(int(r["idx"])), js_str(str(r["name"])), js_str(r["dep"]),
            str(int(days) if days == int(days) else days),
            str(int(r["cap"]) if r.get("cap") is not None else -1),
            str(int(r["spots"])), js_str(r.get("price") or "Charter"),
            "[" + ",".join(js_str(f) for f in sorted(r.get("flags") or [])) + "]"]) + "],")
    lines.append("];")
    lines.append(f"{LR_MARK_END} ══")
    return "\n".join(lines)


def run_longrange(args, started: dt.datetime, deadline: float, html_path: Path) -> dict:
    """Refresh the long-range RAW rows. Returns a summary; writes data files but never the
    HTML (run() owns that, so the page is only ever rewritten once per run)."""
    today = started.strftime("%Y-%m-%d")
    prev = read_raw_rows(html_path.read_text(encoding="utf-8")) if html_path.exists() else []
    prev_by_key = {(r["idx"], r["dep"]): r for r in prev}
    prev_n_by_boat = collections.Counter(r["idx"] for r in prev)

    boats: list[dict] = []
    final: list[dict] = []
    unresolved: list[dict] = []
    dropped_future: list[dict] = []

    for idx, b in enumerate(BOAT_SOURCES):
        info = dict(b, status="ok", http=[], rows_raw=0, rows_kept=0, unresolved=0,
                    last_good="", error="")
        prev_rows = [r for r in prev if r["idx"] == idx]
        try:
            if args.offline:
                files = sorted(Path(args.offline).glob(f"LR_{b['slug']}*"))
                if not files:
                    raise RuntimeError("no offline fixture")
                scraped: list[dict] = []
                for f in files:
                    scraped += parse_boat_page(idx, b["name"],
                                               f.read_text(encoding="utf-8", errors="ignore"), f.name)
            else:
                status, body = fetch(LR_URL.format(slug=b["slug"]), deadline)
                info["http"].append(status)
                if status != 200:
                    raise RuntimeError(f"http {status}")
                if is_captcha(body):
                    raise RuntimeError("captcha page")
                scraped = parse_boat_page(idx, b["name"], body, "sales")
                time.sleep(PAGE_SPACING_S)
            scraped = {(r["idx"], r["dep"], norm(r["name"])): r for r in scraped}.values()
            if not scraped:
                raise RuntimeError("parsed 0 rows")
            info["rows_raw"] = len(scraped)

            rows: list[dict] = []
            seen_keys: set[tuple] = set()
            for r in scraped:
                key = (r["idx"], r["dep"])
                old = prev_by_key.get(key)
                ok, why = lr_row_ok(r)
                if not ok:
                    info["unresolved"] += 1
                    unresolved.append(dict(r, note=why))
                    if old:                      # keep what was there rather than publish a guess
                        rows.append(dict(old, src="kept", note=why))
                        seen_keys.add(key)
                    continue
                # The page cannot supply Ed's curation: his shortened trip name and his 'ed'
                # flag. Carry both forward on a (boat, departure) match; only a genuinely new
                # trip takes the page's own name.
                flags = sorted(set(r["flags"]) | set(old["flags"])) if old else sorted(set(r["flags"]))
                price = r["price"] or (old["price"] if old and old.get("price") else "—")
                rows.append(dict(r, name=old["name"] if old else r["name"],
                                 price=price, flags=flags, src="sales", note=""))
                seen_keys.add(key)

            # Trips that already departed are removed from the page the moment they sail, so
            # carry them forward. A FUTURE trip missing from a healthy page was cancelled or
            # rescheduled, so it is dropped — and reported, in case the parser missed it.
            for r in prev_rows:
                if (r["idx"], r["dep"]) in seen_keys:
                    continue
                if r["dep"] < today:
                    rows.append(dict(r, src="carried", note=""))
                else:
                    dropped_future.append(r)

            # Per-boat collapse guard. Judged per boat, never on the 695-row total, or one
            # boat emptying would hide behind the other ten.
            pn = prev_n_by_boat.get(idx, 0)
            if pn and len(rows) < HOLD_RATIO * pn:
                raise RuntimeError(f"row collapse {len(rows)} vs {pn} previous")
            info["last_good"] = today
            final += rows
        except Exception as e:
            info["status"], info["error"] = "stale", str(e)
            info["last_good"] = ""
            final += [dict(r, src="kept", note="boat stale") for r in prev_rows]
            dropped_future = [r for r in dropped_future if r["idx"] != idx]
            log(f"WARN LR {b['name']}: {e} — keeping {len(prev_rows)} previous rows")
        info["rows_kept"] = sum(1 for r in final if r["idx"] == idx)
        boats.append(info)

    stale = [b["name"] for b in boats if b["status"] != "ok"]
    n_unres = sum(b["unresolved"] for b in boats)
    n_raw = sum(b["rows_raw"] for b in boats)
    # A couple of unresolved rows is the steady state, not an incident: two Royal Star rows
    # print the next trip's name in the availability cell and have done so every week. If
    # that alone demoted the run to "partial", every Sunday would cry wolf and the word
    # would stop meaning anything. Only a stale boat — or unresolved rows breaking out of
    # their usual handful, which is what a page format change looks like — demotes it.
    unres_spike = bool(n_raw) and n_unres > UNRESOLVED_PARTIAL_RATIO * n_raw
    if len(stale) == len(BOAT_SOURCES):
        outcome = "failed"
    elif stale or unres_spike:
        outcome = "partial"
    else:
        outcome = "landed"

    digest = hashlib.sha256("\n".join(
        "|".join(str(r.get(k, "")) for k in ("idx", "name", "dep", "days", "cap", "spots", "price"))
        for r in sorted(final, key=lambda r: (r["idx"], r["dep"], norm(str(r["name"]))))
    ).encode()).hexdigest()[:16]

    if outcome != "failed":
        write_csv(DATA / "longrange_trips.csv",
                  [dict(r, flags="|".join(r.get("flags") or [])) for r in final],
                  LR_CSV_FIELDS)
        write_json(DATA / "lr_sources.json", {b["slug"]: b for b in boats})

    for b in boats:
        log(f"  LR {b['name']:17s} {b['status']:6s} raw={b['rows_raw']:4d} kept={b['rows_kept']:4d} "
            f"unresolved={b['unresolved']:3d} {b['error']}")
    log(f"long-range outcome={outcome} rows={len(final)} unresolved={n_unres} "
        f"dropped-future={len(dropped_future)} digest={digest}")
    for r in dropped_future[:10]:
        log(f"    dropped (no longer listed): {BOAT_SOURCES[r['idx']]['name']} {r['dep']} {r['name']}")

    return {"outcome": outcome, "rows": final, "digest": digest, "rows_kept": len(final),
            "prev_rows_kept": len(prev), "unresolved": n_unres,
            "dropped_future": len(dropped_future),
            "per_boat": {b["slug"]: {"name": b["name"], "status": b["status"],
                                     "raw": b["rows_raw"], "kept": b["rows_kept"],
                                     "unresolved": b["unresolved"], "error": b["error"]}
                         for b in boats},
            "boats": boats}


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
    # Landings drop a trip from their schedule the moment it departs, so a boat that left before
    # this run and has not returned yet is invisible to the fetch. Carry those rows forward from
    # the previous run (departed before today, returns today or later, landing fetched OK).
    today = started.strftime("%Y-%m-%d")
    carried = carry_forward(prev_kept, kept, sources, today)
    kept += carried
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
    html_path = Path(args.html)
    md = {
        "outcome": outcome, "digest": digest, "rows_kept": len(kept), "rows_carried": len(carried),
        "rows_raw": len(raw_all), "prev_rows_kept": prev_n,
        "per_landing": {c: {"status": v["status"], "raw": v["rows_raw"], "kept": v["rows_kept"],
                             "pages": v["pages"], "error": v.get("error", "")} for c, v in sources.items()},
        "html_written": False,
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
            md["outcome"] = outcome
            log(f"already-landed: multi-day data unchanged since last run (digest {digest})")
        write_csv(DATA / "multiday_trips.csv", kept)
        write_csv(DATA / "landing_trips_raw.csv", raw_all)
        write_json(DATA / "boat_capacity.json", cap_table)
        write_json(DATA / "sources.json", sources)

    for c, v in sources.items():
        log(f"  {c} {v['name']:24s} {v['status']:6s} pages={v['pages']:2d} raw={v['rows_raw']:4d} kept={v['rows_kept']:4d} {v.get('error','')}")
    log(f"multi-day outcome={outcome} kept={len(kept)} (carried {len(carried)}) raw={len(raw_all)} dropped={len(dropped)} digest={digest}")

    # ---- long-range boats (RAW). Runs even when a landing failed: the two surfaces are
    # independent, and a bad H&M feed is no reason to leave RAW four months stale.
    lr: dict = {"outcome": "skipped", "rows_kept": 0, "unresolved": 0, "dropped_future": 0,
                "digest": "", "per_boat": {}, "html_written": False, "rows": []}
    if not args.skip_longrange:
        lr = run_longrange(args, started, time.monotonic() + FETCH_BUDGET_S, html_path)
        lr["html_written"] = False
        prev_lr_digest = read_json(DATA / "last_run.json", {}).get("longrange", {}).get("digest")
        if lr["outcome"] == "landed" and prev_lr_digest == lr["digest"] and not args.force:
            lr["outcome"] = "already-landed"
            log(f"already-landed: long-range data unchanged since last run (digest {lr['digest']})")

    # ---- write the page once, both blocks together
    if not args.dry_run and html_path.exists():
        wrote_md = md["outcome"] not in ("already-landed", "hold", "failed") and \
            write_block(html_path, render_block(kept, as_of, sources))
        md["html_written"] = bool(wrote_md)
        if wrote_md:
            log(f"MULTI block written to {html_path.name} ({len(kept)} rows, as of {as_of})")
            if stamp_readme(html_path.parent / "README.md", as_of):
                log("README multi-day freshness line updated")
        wrote_lr = lr["outcome"] in ("landed", "partial") and \
            write_block(html_path, render_raw_block(lr["rows"], as_of, lr["boats"]),
                        LR_MARK_START, LR_MARK_END)
        lr["html_written"] = bool(wrote_lr)
        if wrote_lr:
            log(f"RAW block written to {html_path.name} ({lr['rows_kept']} rows, as of {as_of})")
            if stamp_readme(html_path.parent / "README.md", as_of, "Last long-range refresh"):
                log("README long-range freshness line updated")
        if md["outcome"] in ("landed", "partial") and not wrote_md:
            log(f"NOTE: MULTI markers not found in {html_path} — HTML untouched")
        if lr["outcome"] in ("landed", "partial") and not wrote_lr:
            log(f"NOTE: LONG-RANGE markers not found in {html_path} — RAW untouched")

    # The run's outcome is the worse of the two surfaces; that is what the exit code and the
    # scheduled task's status mapping key off.
    rank = {"landed": 0, "already-landed": 0, "skipped": 0, "partial": 2, "hold": 3, "failed": 4}
    combined = max((md["outcome"], lr["outcome"]), key=lambda o: rank[o])
    if rank[combined] == 0:
        combined = "already-landed" if md["outcome"] == "already-landed" and \
            lr["outcome"] in ("already-landed", "skipped") else "landed"

    lr_out = {k: v for k, v in lr.items() if k not in ("rows", "boats")}
    summary = {
        "ts": started.isoformat(), "outcome": combined, "dry_run": bool(args.dry_run),
        "multiday": md, "longrange": lr_out,
        # multi-day fields stay at the top level too, so anything reading the older shape works
        **{k: md[k] for k in ("digest", "rows_kept", "rows_carried", "rows_raw",
                              "prev_rows_kept", "per_landing", "html_written")},
    }
    log(f"outcome={combined} (multi-day {md['outcome']}, long-range {lr['outcome']})")

    write_json(DATA / "last_run.json", summary)
    with (DATA / "refresh.log").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"ts": summary["ts"], "outcome": combined,
                             "multiday": {"outcome": md["outcome"], "kept": len(kept),
                                          "raw": len(raw_all), "html": md["html_written"],
                                          "per_landing": {c: f"{v['status']}:{v['rows_kept']}"
                                                          for c, v in sources.items()}},
                             "longrange": {"outcome": lr["outcome"], "kept": lr["rows_kept"],
                                           "unresolved": lr["unresolved"],
                                           "html": lr["html_written"]}}) + "\n")
    return rank[combined]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="write data/ only; never touch the HTML")
    ap.add_argument("--offline", metavar="DIR", help="parse saved pages named <CODE>_*.html / HM_*.txt from DIR")
    ap.add_argument("--html", default=str(ROOT / "saltwater_trip_planner.html"))
    ap.add_argument("--force", action="store_true", help="rewrite even if data is unchanged")
    ap.add_argument("--data", metavar="DIR", help="data directory (default: ./data)")
    ap.add_argument("--skip-longrange", action="store_true",
                    help="multi-day only; leave the long-range RAW block alone")
    return run(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
