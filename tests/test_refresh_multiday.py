#!/usr/bin/env python3
"""Offline tests for refresh_multiday.py — run: python3 tests/test_refresh_multiday.py

Fixtures in tests/fixtures/ are real pages saved 2026-09-03 (page 1 of each landing and a
trimmed H&M feed). They exercise the parser, the keep/drop rules, capacity fill, dedupe,
the HTML block writer, and the stale-landing / hold safety nets — with no network.
"""
import datetime as dt
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
    def run_offline(self, data_dir, html=None, extra=()):
        argv = ["--offline", str(FIX), "--data", str(data_dir), *extra]
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
                code = rm.main(["--offline", fx, "--data", d, "--dry-run"])
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
                code = rm.main(["--offline", fx, "--data", d, "--dry-run", "--force"])
            self.assertEqual(code, 3)
            last = json.loads((Path(d) / "last_run.json").read_text())
            self.assertEqual(last["outcome"], "hold")
            self.assertTrue(list((Path(d) / "hold").glob("*.csv")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
