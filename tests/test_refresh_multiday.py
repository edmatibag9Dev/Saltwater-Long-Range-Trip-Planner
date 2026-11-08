#!/usr/bin/env python3
"""Offline tests for refresh_multiday.py — run: python3 tests/test_refresh_multiday.py

Fixtures in tests/fixtures/ are real pages saved 2026-09-03 (page 1 of each landing and a
trimmed H&M feed). They exercise the parser, the keep/drop rules, capacity fill, dedupe,
the HTML block writer, and the stale-landing / hold safety nets — with no network.
"""
import datetime as dt
import re
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import refresh_multiday as rm  # noqa: E402

FIX = HERE / "fixtures"


def load(code):
    f = next(FIX.glob(f"{code}_*"))
    body = f.read_text(encoding="utf-8", errors="ignore")
    return rm.parse_hm(body, f.name) if code == "HM" else rm.parse_landing_page(code, body, f.name)


class ParserTests(unittest.TestCase):
    def test_each_landing_parses_rows(self):
        for code, lo in (("FL", 30), ("SF", 15), ("PL", 15), ("HM", 40)):
            rows = load(code)
            self.assertGreaterEqual(len(rows), lo, code)
            for r in rows:
                self.assertTrue(r["boat"], f"{code} row without boat: {r}")
                self.assertRegex(r["dep"], r"^20\d\d-\d\d-\d\d$")
                self.assertRegex(r["deptime"], r"^\d{1,2}:\d\d [AP]M$")

    def test_fl_boat_names_come_from_the_filter_list(self):
        page = (FIX / "FL_page1.html").read_text(encoding="utf-8", errors="ignore")
        known = rm.boat_options(page)
        self.assertIn("tomahawk", known)
        for r in load("FL"):
            self.assertIn(rm.norm(r["boat"]), known, r)

    def test_check_in_line_does_not_lose_the_searcher_row(self):
        rows = [r for r in load("FL") if r["boat"] == "Searcher"]
        self.assertTrue(rows, "Searcher row (has a 'Check In @ 10AM' line) was lost")
        r = rows[0]
        self.assertEqual((r["dep"], r["deptime"], r["ret"], r["rettime"]), ("2026-09-04", "10:00 AM", "2026-09-07", "8:00 AM"))
        self.assertEqual((r["cap"], r["price"], r["spots"]), ("27", "$1595", "Waitlist Only"))

    def test_chartered_row_has_no_capacity(self):
        r = next(r for r in load("FL") if r["boat"] == "Pegasus" and r["dep"] == "2026-09-03")
        self.assertEqual(r["spots"], "Chartered")
        self.assertEqual(r["cap"], "")
        self.assertEqual((r["ret"], r["rettime"]), ("2026-09-06", "6:00 AM"))

    def test_hm_times_are_converted_to_pacific(self):
        rows = load("HM")
        r = next(r for r in rows if r["boat"] == "Grande" and r["dep"] == "2026-09-03")
        self.assertEqual(r["deptime"], "5:30 AM")  # datetime 12:30Z → 05:30 PDT
        r = next(r for r in rows if r["boat"] == "Excalibur" and r["dep"] == "2026-09-03")
        self.assertEqual(r["ttype"], "3 Day - Freelance")
        self.assertEqual(r["deptime"], "10:00 AM")
        # 3 Day = 4080 min = 2 d 20 h → returns 6:00 AM three days later
        self.assertEqual((r["ret"], r["rettime"]), ("2026-09-06", "6:00 AM"))
        self.assertTrue(r["cap"].isdigit() and int(r["cap"]) > 0)


class RuleTests(unittest.TestCase):
    def row(self, **kw):
        base = dict(landing="FL", boat="Tomahawk", ttype="1.5 Day", dep="2026-09-04", deptime="6:00 PM",
                    ret="2026-09-06", rettime="6:00 AM", cap="29", spots="Full", price="$569", src="t")
        base.update(kw)
        return base

    def test_trip_days_parsing(self):
        for tt, d in (("1.5 Day", 1.5), ("2 Day Limited Load", 2.0), ("3/4 Day Local", None),
                      ("Overnight Limited Load", 1.0), ("Reverse 1.5 Day", 1.5), ("10 Day", 10.0),
                      ("Lobster - 2.5 Day Dive Trip", 2.5)):
            got = rm.trip_days(self.row(ttype=tt, ret="", rettime=""))
            self.assertEqual(got, d, tt)
        # no number → derived from dates (5:30 AM → 5:00 PM same day = 0.48 d)
        self.assertAlmostEqual(rm.trip_days(self.row(ttype="Full Day", dep="2026-09-04", deptime="5:30 AM",
                                                     ret="2026-09-04", rettime="5:00 PM")), 0.48, places=2)

    def test_keep_rules(self):
        self.assertTrue(rm.keep(self.row())[0])
        self.assertFalse(rm.keep(self.row(ttype="Overnight", rettime="5:00 PM"))[0])       # < 1.5 d
        self.assertFalse(rm.keep(self.row(rettime="5:00 PM"))[0])                          # after 10 AM
        self.assertTrue(rm.keep(self.row(rettime="5:00 AM"))[0])                           # window inclusive
        self.assertTrue(rm.keep(self.row(rettime="10:00 AM"))[0])
        self.assertFalse(rm.keep(self.row(rettime="10:01 AM"))[0])
        self.assertFalse(rm.keep(self.row(boat="Shogun", ttype="8 Day"))[0])               # long range
        self.assertFalse(rm.keep(self.row(boat="Searcher", ttype="3 Day"))[0])
        self.assertFalse(rm.keep(self.row(boat="Intrepid", ttype="8 Day"))[0])
        self.assertFalse(rm.keep(self.row(landing="HM", boat="Spirit of Adventure", ttype="3 Day"))[0])
        self.assertFalse(rm.keep(self.row(ret="", rettime=""))[0])                          # no return

    def test_fixture_rows_all_obey_rules_after_filter(self):
        rows = []
        for c in ("FL", "SF", "PL", "HM"):
            rows += load(c)
        kept = [r for r in rm.dedupe(rows) if rm.keep(r)[0]]
        self.assertGreater(len(kept), 20)
        for r in kept:
            self.assertGreaterEqual(rm.trip_days(r), 1.5, r)
            t = rm.ret_time(r)
            self.assertTrue(dt.time(5, 0) <= t <= dt.time(10, 0), r)
            self.assertNotIn(rm.norm(r["boat"]), rm.LR_BOATS, r)
        landings = {r["landing"] for r in kept}
        self.assertEqual(landings, {"FL", "SF", "PL", "HM"})

    def test_dedupe(self):
        a, b = self.row(), self.row(src="other")
        self.assertEqual(len(rm.dedupe([a, b])), 1)
        self.assertEqual(len(rm.dedupe([a, self.row(deptime="7:00 PM")])), 2)

    def test_carry_forward_keeps_departed_unreturned_rows(self):
        prev = [self.row(boat="Constitution", ttype="2.5 Day", dep="2026-09-03", deptime="7:00 PM", ret="2026-09-06"),   # departed, at sea → carry
                self.row(boat="Islander", ttype="3 Day", dep="2026-09-01", ret="2026-09-04"),                            # already returned → drop
                self.row(boat="Fortune", ttype="2 Day", dep="2026-09-10", ret="2026-09-12"),                             # future, missing now → cancelled → drop
                self.row(landing="HM", boat="Legend", ttype="3 Day", dep="2026-09-03", ret="2026-09-06"),                # HM stale → handled elsewhere → skip
                self.row(boat="Tomahawk", dep="2026-09-03", deptime="6:00 PM", ret="2026-09-05")]                       # still listed → not duplicated
        kept = [self.row(boat="Tomahawk", dep="2026-09-03", deptime="6:00 PM", ret="2026-09-05")]
        sources = {"FL": {"status": "ok"}, "HM": {"status": "stale"}}
        out = rm.carry_forward(prev, kept, sources, today="2026-09-05")
        self.assertEqual([r["boat"] for r in out], ["Constitution"])
        self.assertEqual(out[0]["src"], "carried")

    def test_capacity_fill(self):
        rows = [self.row(cap="29"), self.row(cap="", spots="Chartered", dep="2026-09-10"),
                self.row(boat="Mystery", cap="", spots="Chartered")]
        table = rm.apply_capacity(rows, {})
        self.assertEqual((rows[0]["cap"], rows[0]["cap_source"]), ("29", "listed"))
        self.assertEqual((rows[1]["cap"], rows[1]["cap_source"]), ("29", "boat-max"))
        self.assertEqual((rows[2]["cap"], rows[2]["cap_source"]), (str(rm.DEFAULT_CAP), "default"))
        self.assertEqual(table["FL|tomahawk"], 29)


class PipelineTests(unittest.TestCase):
    def run_offline(self, data_dir, html=None, extra=(), skip_lr=True):
        # These tests cover the multi-day surface, so they skip the long-range one by
        # default. LongRangePipelineTests exercises that path with its own fixtures.
        argv = ["--offline", str(FIX), "--data", str(data_dir), *extra]
        if skip_lr:
            argv += ["--skip-longrange"]
        if html:
            argv += ["--html", str(html)]
        else:
            argv += ["--dry-run"]
        return rm.main(argv)

    def test_offline_run_writes_data_files(self):
        with tempfile.TemporaryDirectory() as d:
            code = self.run_offline(Path(d))
            self.assertEqual(code, 0)
            for f in ("multiday_trips.csv", "landing_trips_raw.csv", "boat_capacity.json",
                      "sources.json", "last_run.json", "refresh.log"):
                self.assertTrue((Path(d) / f).exists(), f)
            last = json.loads((Path(d) / "last_run.json").read_text())
            self.assertEqual(last["outcome"], "landed")
            self.assertTrue(all(v["status"] == "ok" for v in last["per_landing"].values()))
            # second identical run is idempotent
            code = self.run_offline(Path(d))
            self.assertEqual(code, 0)
            self.assertEqual(json.loads((Path(d) / "last_run.json").read_text())["outcome"], "already-landed")

    def test_html_block_is_written_between_markers(self):
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "planner.html"
            html.write_text("<script>\nconst BOATS=[];\n" + rm.MARK_START + " ══\nconst MULTI = [];\n"
                            + rm.MARK_END + " ══\nconst trips = [];\n</script>", encoding="utf-8")
            code = self.run_offline(Path(d), html=html)
            self.assertEqual(code, 0)
            s = html.read_text(encoding="utf-8")
            self.assertIn("const MULTI_AS_OF = '", s)
            self.assertIn("const MULTI_SOURCES = {", s)
            self.assertRegex(s, r"\['FL','Tomahawk','1\.5 Day',1\.5,'2026-09-04','6:00 PM','2026-09-06','6:00 AM',29,'Full'\],")
            self.assertTrue(s.startswith("<script>\nconst BOATS=[];\n"))
            self.assertTrue(s.endswith("const trips = [];\n</script>"))
            self.assertEqual(s.count(rm.MARK_START), 1)

    def test_readme_stamp(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d) / "README.md"
            rd.write_text("x\n**Last multi-day refresh:** 2026-01-01 (auto)\ny\n", encoding="utf-8")
            self.assertTrue(rm.stamp_readme(rd, "2026-09-06"))
            self.assertIn("**Last multi-day refresh:** 2026-09-06 (auto)", rd.read_text(encoding="utf-8"))
            self.assertFalse(rm.stamp_readme(rd, "2026-09-06"))  # already current → no change

    def test_missing_markers_leave_html_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "planner.html"
            html.write_text("<script>const RAW=[];</script>", encoding="utf-8")
            self.assertEqual(self.run_offline(Path(d), html=html), 0)
            self.assertEqual(html.read_text(encoding="utf-8"), "<script>const RAW=[];</script>")

    def test_stale_landing_keeps_previous_rows_and_reports_partial(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.run_offline(Path(d)), 0)
            # second run with the H&M fixture missing → HM stale, previous HM rows retained
            with tempfile.TemporaryDirectory() as fx:
                for f in FIX.iterdir():
                    if not f.name.startswith("HM_"):
                        (Path(fx) / f.name).write_bytes(f.read_bytes())
                code = rm.main(["--offline", fx, "--data", d, "--dry-run", "--skip-longrange"])
            self.assertEqual(code, 2)
            last = json.loads((Path(d) / "last_run.json").read_text())
            self.assertEqual(last["outcome"], "partial")
            self.assertEqual(last["per_landing"]["HM"]["status"], "stale")
            self.assertGreater(last["per_landing"]["HM"]["kept"], 0)

    def test_hold_when_rows_collapse(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.run_offline(Path(d)), 0)
            with tempfile.TemporaryDirectory() as fx:
                # only Seaforth page 1 present → FL/PL/HM stale (kept), but simulate a collapse by
                # writing a tiny previous CSV that says last run had 10x the rows
                for f in FIX.iterdir():
                    (Path(fx) / f.name).write_bytes(f.read_bytes())
                prev = (Path(d) / "multiday_trips.csv").read_text().splitlines()
                big = prev + prev[1:] * 9
                (Path(d) / "multiday_trips.csv").write_text("\n".join(big) + "\n")
                code = rm.main(["--offline", fx, "--data", d, "--dry-run", "--force",
                                "--skip-longrange"])
            self.assertEqual(code, 3)
            last = json.loads((Path(d) / "last_run.json").read_text())
            self.assertEqual(last["outcome"], "hold")
            self.assertTrue(list((Path(d) / "hold").glob("*.csv")))


LR_FIXTURES = {"shogun": 0, "americanangler": 1, "excel": 7}   # slug -> boatIdx in BOATS
PLANNER = HERE.parent / "saltwater_trip_planner.html"


def load_boat(slug):
    idx = LR_FIXTURES[slug]
    page = (FIX / f"LR_{slug}.html").read_text(encoding="utf-8", errors="ignore")
    return rm.parse_boat_page(idx, rm.BOAT_SOURCES[idx]["name"], page, f"LR_{slug}")


class LongRangeParserTests(unittest.TestCase):
    """The boat /sales/ pages, saved 2026-11-08. Each fixture is here for a specific quirk:
    Shogun for the plain grammar and multi-line names, American Angler for charter rows
    that print a bare '-', Excel for the '-' name separator and a bare 'OPEN'."""

    def test_every_fixture_parses_plausible_rows(self):
        for slug in LR_FIXTURES:
            rows = load_boat(slug)
            self.assertGreaterEqual(len(rows), 30, slug)
            for r in rows:
                self.assertRegex(r["dep"], r"^20\d\d-\d\d-\d\d$")
                self.assertIsNotNone(r["days"], r)
                self.assertTrue(0.5 <= r["days"] <= 30, r)
                self.assertEqual(r["idx"], LR_FIXTURES[slug])

    def test_shogun_row_reads_every_field(self):
        r = next(r for r in load_boat("shogun") if r["dep"] == "2026-11-06")
        self.assertIn("IZORLINE", r["name"])
        self.assertEqual(r["days"], 8.0)
        self.assertEqual(r["cap"], 22)
        self.assertEqual(r["price"], "$3,895")      # the Check column, never the Credit one
        self.assertEqual(r["spots"], -2)            # 'In Progress'

    def test_multi_line_trip_name_is_joined(self):
        r = next(r for r in load_boat("shogun") if r["dep"] == "2026-11-28")
        self.assertIn("PENN SPONSORED ULTRA LIMITED LOAD", r["name"])
        self.assertIn("DEFINTE GO", r["name"])

    def test_a_return_date_never_becomes_a_phantom_departure(self):
        """11-14-2026 is both the return of the 11-6 trip and a real departure. Only the
        departure may survive, and it must carry the departing trip's own name."""
        rows = [r for r in load_boat("shogun") if r["dep"] == "2026-11-14"]
        self.assertEqual(len(rows), 1)
        self.assertIn("NONOGUCHI", rows[0]["name"])
        self.assertEqual(rows[0]["days"], 10.0)

    def test_charter_rows_have_no_price_and_no_capacity(self):
        rows = [r for r in load_boat("americanangler") if r["spots"] == -1]
        self.assertGreaterEqual(len(rows), 10)
        for r in rows:
            self.assertEqual(r["price"], "Charter")
            self.assertIsNone(r["cap"])
            self.assertTrue(r["name"], r)

    def test_dash_separated_name_survives_on_excel(self):
        rows = load_boat("excel")
        named = [r for r in rows if r["name"]]
        self.assertGreater(len(named), len(rows) * 0.9)
        self.assertTrue(any("Merritt" in r["name"] for r in rows))

    def test_closed_charter_is_its_own_trip_name(self):
        """'CLOSED CHARTER' is a charter word AND the trip's only name line, so the name
        filter must fall back to it instead of emitting a nameless row."""
        r = next(r for r in load_boat("shogun") if r["dep"] == "2027-05-05")
        self.assertIn("CHARTER", r["name"].upper())

    def test_every_fixture_row_passes_the_gate(self):
        for slug in LR_FIXTURES:
            for r in load_boat(slug):
                ok, why = rm.lr_row_ok(r)
                self.assertTrue(ok, f"{slug} {r['dep']} {r['name']!r}: {why}")

    def test_spots_word_table(self):
        for word, want in (("Join wait list", 0), ("FULL", 0), ("Join Waitlist", 0),
                           ("Join the wait list", 0), ("Sold Out", 0), ("-", 0),
                           ("In Progress", -2), ("OUT", -2), ("Trip In", -2),
                           ("CHARTER", -1), ("Private Charter", -1), ("PRIVATE", -1),
                           ("7", 7), ("24", 24)):
            self.assertEqual(rm.lr_spots(word, True, 24), want, word)
        self.assertEqual(rm.lr_spots("OPEN", True, 32), 32)   # bare OPEN → the capacity
        self.assertIsNone(rm.lr_spots("Royal Star", True, 22))  # a leaked name is unreadable
        self.assertEqual(rm.lr_spots("-", False, None), -1)  # no price, no cap → charter

    def test_gate_rejects_unusable_rows(self):
        good = dict(name="Open 3-Day", days=3.0, cap=24, spots=4, price="$1,500", avail="4")
        self.assertTrue(rm.lr_row_ok(good)[0])
        for bad in (dict(good, name=""), dict(good, days=None), dict(good, days=99.0),
                    dict(good, spots=None), dict(good, cap=None),
                    dict(good, cap=99), dict(good, spots=30)):
            self.assertFalse(rm.lr_row_ok(bad)[0], bad)
        # a charter needs no capacity, and a blank price is allowed through
        self.assertTrue(rm.lr_row_ok(dict(good, spots=-1, cap=None, price="Charter"))[0])
        self.assertTrue(rm.lr_row_ok(dict(good, price=""))[0])


class RawLiteralTests(unittest.TestCase):
    def test_js_rows_handles_apostrophes_and_alignment_padding(self):
        src = ("""[0,"Ken's Custom Reels 3-Day",'2026-07-17',3,26,0,"$1,750",[]],\n"""
               """[1,'Open 3-Day',           '2026-06-02',3,25,1,   '$1,580',['ed','invite']],""")
        rows = rm.js_rows(src)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], "Ken's Custom Reels 3-Day")
        self.assertEqual(rows[0][2], "2026-07-17")
        self.assertEqual(rows[1][2], "2026-06-02")       # no leading padding
        self.assertEqual(rows[1][6], "$1,580")
        self.assertEqual(rows[1][7], ["ed", "invite"])

    def test_read_raw_rows_reads_the_real_dashboard(self):
        rows = rm.read_raw_rows(PLANNER.read_text(encoding="utf-8"))
        self.assertGreater(len(rows), 600)
        for r in rows:
            self.assertRegex(r["dep"], r"^20\d\d-\d\d-\d\d$")
            self.assertEqual(r["price"], str(r["price"]).strip())
            self.assertIn(r["idx"], range(len(rm.BOAT_SOURCES)))
        self.assertEqual(sum(1 for r in rows if "ed" in r["flags"]), 1)

    def test_boat_sources_match_the_dashboard_boats_array(self):
        """BOATS stays hand-maintained, and boatIdx indexes it, so the two orders must not
        drift. The generated block's comment promises this test exists."""
        s = PLANNER.read_text(encoding="utf-8")
        blk = s[s.index("const BOATS = ["):]
        names = re.findall(r"name:\s*'([^']*)'", blk[:blk.index("];")])
        self.assertEqual(names, [b["name"] for b in rm.BOAT_SOURCES])

    def test_render_raw_block_round_trips(self):
        rows = [dict(idx=0, name="Ken's 3-Day", dep="2026-06-02", days=3.0, cap=25,
                     spots=1, price="$1,580", flags=["ed"]),
                dict(idx=1, name="Charter", dep="2026-06-03", days=1.5, cap=None,
                     spots=-1, price="Charter", flags=[])]
        block = rm.render_raw_block(rows, "2026-11-08", [{"name": "Shogun", "status": "ok",
                                                          "last_good": "2026-11-08"}])
        back = rm.read_raw_rows(block)
        self.assertEqual(len(back), 2)
        self.assertEqual(back[0]["name"], "Ken's 3-Day")
        self.assertEqual(back[0]["flags"], ["ed"])
        self.assertEqual(back[1]["cap"], -1)             # None capacity renders as -1
        self.assertEqual(back[1]["days"], 1.5)
        self.assertIn("const LR_AS_OF = '2026-11-08';", block)


class LongRangePipelineTests(unittest.TestCase):
    SEED = [
        # curated name + Ed's own flag, still listed on the Shogun fixture → both must survive
        """[0,'Izorline Sponsored 8-Day','2026-11-06',8,22,0,'$3,895',['ed']],""",
        # a departed trip the page no longer lists → carried forward
        """[0,'Ancient History 3-Day','2026-06-02',3,25,1,'$1,580',[]],""",
        # a FUTURE trip absent from a healthy page → treated as cancelled and dropped
        """[0,'Cancelled 4-Day','2027-12-30',4,25,5,'$2,000',[]],""",
    ]

    def planner(self, d):
        html = Path(d) / "planner.html"
        html.write_text(
            "<script>\nconst BOATS=[];\n"
            + rm.LR_MARK_START + " ══\nconst LR_AS_OF = '2026-07-12';\nconst LR_SOURCES = [];\n"
            + "const RAW = [\n" + "\n".join(self.SEED) + "\n];\n"
            + rm.LR_MARK_END + " ══\n"
            + rm.MARK_START + " ══\nconst MULTI = [];\n" + rm.MARK_END + " ══\n</script>",
            encoding="utf-8")
        return html

    def run_lr(self, d, html):
        return rm.main(["--offline", str(FIX), "--data", str(d), "--html", str(html)])

    def test_curation_and_history_survive_a_refresh(self):
        with tempfile.TemporaryDirectory() as d:
            html = self.planner(d)
            code = self.run_lr(d, html)
            self.assertEqual(code, 2)          # 8 boats have no fixture → stale → partial
            rows = rm.read_raw_rows(html.read_text(encoding="utf-8"))

            ed = [r for r in rows if "ed" in r["flags"]]
            self.assertEqual(len(ed), 1, "Ed's flag must never be dropped by a refresh")
            self.assertEqual(ed[0]["dep"], "2026-11-06")
            self.assertEqual(ed[0]["name"], "Izorline Sponsored 8-Day",
                             "the curated short name must win over the page's own")
            self.assertEqual(ed[0]["spots"], -2, "live availability must still be applied")

            deps = {(r["idx"], r["dep"]) for r in rows}
            self.assertIn((0, "2026-06-02"), deps, "a departed trip must be carried forward")
            self.assertNotIn((0, "2027-12-30"), deps, "a vanished future trip must be dropped")

            last = json.loads((Path(d) / "last_run.json").read_text())
            self.assertEqual(last["outcome"], "partial")
            self.assertEqual(last["longrange"]["outcome"], "partial")
            self.assertEqual(last["longrange"]["dropped_future"], 1)
            self.assertEqual(last["longrange"]["per_boat"]["shogun"]["status"], "ok")
            self.assertEqual(last["longrange"]["per_boat"]["intrepid"]["status"], "stale")
            self.assertTrue((Path(d) / "longrange_trips.csv").exists())
            self.assertTrue((Path(d) / "lr_sources.json").exists())
            # the multi-day surface still landed in the same run
            self.assertEqual(last["multiday"]["outcome"], "landed")
            self.assertTrue(last["multiday"]["html_written"])
            self.assertTrue(last["longrange"]["html_written"])

    def test_second_identical_run_changes_nothing(self):
        """A re-run must not churn the page. 'already-landed' is reserved for a surface that
        fully landed — a partial run keeps reporting itself partial, exactly as the
        multi-day path does — so what is asserted here is a stable digest and a byte-identical
        page, which is what decides whether the Sunday job has anything to commit."""
        with tempfile.TemporaryDirectory() as d:
            html = self.planner(d)
            self.run_lr(d, html)
            before = html.read_text(encoding="utf-8")
            first = json.loads((Path(d) / "last_run.json").read_text())["longrange"]["digest"]
            self.run_lr(d, html)
            last = json.loads((Path(d) / "last_run.json").read_text())
            self.assertEqual(last["longrange"]["digest"], first)
            self.assertEqual(html.read_text(encoding="utf-8"), before)

    def test_a_fully_landed_surface_reports_already_landed(self):
        """With every boat's page present, an unchanged second run short-circuits."""
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as fx:
            for f in FIX.iterdir():
                (Path(fx) / f.name).write_bytes(f.read_bytes())
            for b in rm.BOAT_SOURCES:                    # give the other 8 boats a page
                p = Path(fx) / f"LR_{b['slug']}.html"
                if not p.exists():
                    p.write_bytes((FIX / "LR_shogun.html").read_bytes())
            html = self.planner(d)
            rm.main(["--offline", fx, "--data", str(d), "--html", str(html)])
            self.assertEqual(json.loads((Path(d) / "last_run.json").read_text())
                             ["longrange"]["outcome"], "landed")
            rm.main(["--offline", fx, "--data", str(d), "--html", str(html)])
            self.assertEqual(json.loads((Path(d) / "last_run.json").read_text())
                             ["longrange"]["outcome"], "already-landed")

    def test_a_boat_whose_rows_collapse_keeps_its_previous_rows(self):
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "planner.html"
            many = "\n".join(f"""[0,'Filler {i} 3-Day','2027-0{i % 9 + 1}-1{i % 9}',3,25,5,'$1,500',[]],"""
                             for i in range(400))
            html.write_text("<script>\n" + rm.LR_MARK_START + " ══\nconst RAW = [\n" + many
                            + "\n];\n" + rm.LR_MARK_END + " ══\n</script>", encoding="utf-8")
            self.run_lr(d, html)
            last = json.loads((Path(d) / "last_run.json").read_text())
            self.assertIn("collapse", last["longrange"]["per_boat"]["shogun"]["error"])
            self.assertEqual(last["longrange"]["per_boat"]["shogun"]["status"], "stale")
            rows = rm.read_raw_rows(html.read_text(encoding="utf-8"))
            self.assertGreaterEqual(sum(1 for r in rows if r["idx"] == 0), 400)

    def test_skip_longrange_leaves_the_raw_block_alone(self):
        with tempfile.TemporaryDirectory() as d:
            html = self.planner(d)
            before = html.read_text(encoding="utf-8")
            lr_before = before[before.index(rm.LR_MARK_START):before.index(rm.LR_MARK_END)]
            rm.main(["--offline", str(FIX), "--data", str(d), "--html", str(html),
                     "--skip-longrange"])
            after = html.read_text(encoding="utf-8")
            self.assertEqual(after[after.index(rm.LR_MARK_START):after.index(rm.LR_MARK_END)],
                             lr_before)
            last = json.loads((Path(d) / "last_run.json").read_text())
            self.assertEqual(last["longrange"]["outcome"], "skipped")


class RateCheckTests(unittest.TestCase):
    """check_rates.py reports; it must never edit the dashboard."""

    def setUp(self):
        import check_rates
        self.cr = check_rates

    def test_stored_rates_are_read_from_the_dashboard(self):
        rate_date, stored = self.cr.stored_rates(PLANNER)
        self.assertTrue(rate_date)
        self.assertEqual(set(stored), {"fp", "fs"})
        self.assertEqual(stored["fp"]["ccFee"], 0.03)
        self.assertEqual(stored["fs"]["ccFee"], 0.0395)

    def test_published_cash_rates_match_what_the_dashboard_quotes(self):
        """The whole point of the Phase 0 correction: every stored rate is the CASH figure,
        so a clean run of the detector finds no difference. A failure here means either a
        processor moved its prices or PROCESSORS has drifted back to a credit-column value."""
        _, stored = self.cr.stored_rates(PLANNER)
        for key, extract in (("fp", self.cr.extract_fp), ("fs", self.cr.extract_fs)):
            page = next(FIX.glob(f"{key}*")).read_text(encoding="utf-8", errors="ignore")
            scraped = extract(rm.visible_lines(page))
            for field, want in stored[key]["rates"].items():
                self.assertIsNotNone(scraped.get(field), f"{key}.{field} unreadable")
                self.assertAlmostEqual(scraped[field], want, places=2,
                                       msg=f"{key}.{field}: page {scraped[field]} vs stored {want}")

    def test_credit_column_is_never_what_gets_stored(self):
        """Fisherman's credit column is exactly cash x 1.03. If a stored rate ever equals
        the credit figure, calcQuotes would add the 3% a second time."""
        page = (FIX / "fp.html").read_text(encoding="utf-8", errors="ignore")
        cash = self.cr.extract_fp(rm.visible_lines(page))
        _, stored = self.cr.stored_rates(PLANNER)
        for field in ("big", "small", "fillet", "gillgut", "collar", "can"):
            self.assertNotAlmostEqual(stored["fp"]["rates"][field], cash[field] * 1.03, places=2)

    def test_a_changed_rate_is_detected_and_nothing_is_written(self):
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "planner.html"
            s = PLANNER.read_text(encoding="utf-8").replace("big:1.95", "big:9.99", 1)
            html.write_text(s, encoding="utf-8")
            before = html.read_text(encoding="utf-8")
            code = self.cr.main(["--offline", str(FIX), "--html", str(html)])
            self.assertEqual(code, 2)
            self.assertEqual(html.read_text(encoding="utf-8"), before,
                             "check_rates.py must never edit the dashboard")
            out = json.loads((HERE.parent / "data" / "rates_check.json").read_text())
            self.assertEqual(out["outcome"], "changed")
            diffs = out["per_processor"]["fp"]["diffs"]
            self.assertEqual([(x["field"], x["stored"], x["scraped"]) for x in diffs],
                             [("big", 9.99, 1.95)])

    def test_repeat_check_leaves_the_file_untouched(self):
        """An unchanged re-check must not rewrite the file just to stamp a new ts.
        data/rates_check.json is not on the Sunday preflight's ignore list, so a dirty
        one from a mid-week run would abort the next scheduled job with 'dirty-tree'."""
        out = HERE.parent / "data" / "rates_check.json"
        self.cr.main(["--offline", str(FIX), "--html", str(PLANNER)])
        first = out.read_bytes()
        self.cr.main(["--offline", str(FIX), "--html", str(PLANNER)])
        self.assertEqual(out.read_bytes(), first,
                         "a no-change re-check rewrote rates_check.json")

    def test_a_real_change_still_rewrites_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            html = Path(d) / "planner.html"
            html.write_text(PLANNER.read_text(encoding="utf-8").replace("big:1.95", "big:9.99", 1),
                            encoding="utf-8")
            out = HERE.parent / "data" / "rates_check.json"
            self.cr.main(["--offline", str(FIX), "--html", str(PLANNER)])
            before = out.read_bytes()
            self.cr.main(["--offline", str(FIX), "--html", str(html)])
            self.assertNotEqual(out.read_bytes(), before)
            self.assertEqual(json.loads(out.read_text())["outcome"], "changed")
            self.cr.main(["--offline", str(FIX), "--html", str(PLANNER)])   # restore

    def test_unreachable_pages_exit_four(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(self.cr.main(["--offline", empty, "--html", str(PLANNER)]), 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
