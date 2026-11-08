/* test-multiday.js — verifies the planner's multi-day integration end to end in a headless DOM.
   Run from the repo root:  node test-multiday.js
   Needs jsdom (resolved from ../node_modules in the Cowork project folder, or a local install). */
"use strict";
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");

const ROOT = __dirname;
const html = fs.readFileSync(path.join(ROOT, "saltwater_trip_planner.html"), "utf8");
const csvText = fs.readFileSync(path.join(ROOT, "data", "multiday_trips.csv"), "utf8");
const lastRun = JSON.parse(fs.readFileSync(path.join(ROOT, "data", "last_run.json"), "utf8"));

const dom = new JSDOM(html, { runScripts: "dangerously" });
const { window } = dom;
const doc = window.document;
// top-level const/let in the page are script-scoped, not window properties — read them in page scope
const P = name => window.eval(name);
const MULTI = P("MULTI"), MULTI_AS_OF = P("MULTI_AS_OF"), MULTI_SOURCES = P("MULTI_SOURCES"), multi = P("multi"),
      BOATS = P("BOATS"), trips = P("trips"), plannerMonths = P("plannerMonths"), finderMonths = P("finderMonths");

let pass = 0, fail = 0;
function ok(cond, msg) { if (cond) pass++; else { fail++; console.error("  ✗ " + msg); } }

// ── tiny CSV reader (fields never contain commas except price, which is quoted by csv.DictWriter) ──
function parseCSV(text) {
  const lines = text.trim().split("\n");
  const head = lines[0].split(",");
  return lines.slice(1).map(line => {
    const cells = []; let cur = "", q = false;
    for (const ch of line) {
      if (ch === '"') q = !q;
      else if (ch === "," && !q) { cells.push(cur); cur = ""; }
      else cur += ch;
    }
    cells.push(cur);
    return Object.fromEntries(head.map((h, i) => [h, cells[i] ?? ""]));
  });
}
const csvRows = parseCSV(csvText);
const clock = t => { const m = /^(\d{1,2}):(\d{2}) (AM|PM)$/.exec(t); if (!m) return null; let h = +m[1] % 12; if (m[3] === "PM") h += 12; return h * 60 + +m[2]; };

/* ── 1. Data block ─────────────────────────────────────────────── */
ok(Array.isArray(MULTI), "MULTI array exists");
ok(MULTI.length === csvRows.length, `MULTI has ${MULTI.length} rows, CSV has ${csvRows.length}`);
ok(MULTI_AS_OF === lastRun.ts.slice(0, 10), `MULTI_AS_OF ${MULTI_AS_OF} matches last_run ${lastRun.ts.slice(0, 10)}`);
ok(Object.keys(MULTI_SOURCES).sort().join() === "FL,HM,PL,SF", "MULTI_SOURCES has the four landings");
ok(multi.length === MULTI.length, `page-side rule check kept every row (${multi.length}/${MULTI.length})`);

const lrNames = new Set(BOATS.map(b => b.name.toLowerCase()).concat(["spirit of adventure"]));
const seen = new Set();
for (const r of MULTI) {
  const [lc, boat, ttype, days, dep, deptime, ret, rettime, cap, spots] = r;
  ok(["FL", "HM", "PL", "SF"].includes(lc), `landing code ${lc}`);
  ok(days >= 1.5, `${boat} ${ttype} days ${days} >= 1.5`);
  const m = clock(rettime);
  ok(m !== null && m >= 300 && m <= 600, `${boat} ${dep} return ${rettime} within 5–10 AM`);
  ok(!lrNames.has(boat.toLowerCase()), `${boat} is not a long-range boat`);
  ok(Number.isInteger(cap) && cap > 0, `${boat} cap ${cap} is a positive integer`);
  ok(/^\d{4}-\d{2}-\d{2}$/.test(dep) && /^\d{4}-\d{2}-\d{2}$/.test(ret) && ret > dep, `${boat} dates ${dep} -> ${ret}`);
  const key = [lc, boat.toLowerCase(), dep, deptime, ttype.toLowerCase()].join("|");
  ok(!seen.has(key), `duplicate row ${key}`); seen.add(key);
}

/* ── 2. Long-range set now has Searcher + Intrepid ─────────────── */
ok(BOATS.length === 11, `BOATS has 11 entries (${BOATS.length})`);
ok(BOATS[9].name === "Searcher" && BOATS[10].name === "Intrepid", "boats 9/10 are Searcher/Intrepid");
/* These two were hand-seeded on 2026-09-03 with 30 and 45 trips. RAW is refreshed from
   the boats' own pages now, so an exact count would fail every time a schedule changed —
   what matters is that both still carry a full schedule. */
ok(trips.filter(t => t.bi === 9).length >= 25, `Searcher has a full schedule (${trips.filter(t => t.bi === 9).length})`);
ok(trips.filter(t => t.bi === 10).length >= 25, `Intrepid has a full schedule (${trips.filter(t => t.bi === 10).length})`);
ok(trips.some(t => t.bi === 9 && t.name === "3-Day" && t.retDate.getMonth() === 8 && t.retDate.getDate() === 7), "Searcher 3-Day departing Sep 4 returns Sep 7");

/* ── 3. Planner months cover LR ∪ multi-day, every month renders ── */
const months = plannerMonths;
ok(months.length >= 15, `planner months ${months.length}`);
ok(months.includes("2027-10"), "planner months include Oct 2027 (multi-day only month)");
for (const ym of months) {
  window.switchPlannerMonth(ym);
  const rows = doc.querySelectorAll("#planner-container .day-row");
  ok(rows.length > 0 || doc.querySelector("#planner-container .no-returns"), `month ${ym} renders`);
  ok(doc.getElementById("planner-header").textContent.includes(String(ym.slice(0, 4))), `header for ${ym}`);
}

/* ── 4. Spot check: Sun Sep 6 and Mon Sep 7, 2026 vs CSV + LR RAW ── */
function expected(dateStr) {
  const md = csvRows.filter(r => r.ret === dateStr);
  const d = new Date(dateStr + "T12:00:00");
  const lr = trips.filter(t => t.retDate.getFullYear() === d.getFullYear() && t.retDate.getMonth() === d.getMonth() && t.retDate.getDate() === d.getDate());
  return { md, lr, anglers: md.reduce((s, r) => s + +r.cap, 0) + lr.reduce((s, t) => s + (t.cap > 0 ? t.cap : 20), 0) };
}
window.switchPlannerMonth("2026-09");
for (const [day, id] of [["2026-09-06", "pr-9-6"], ["2026-09-07", "pr-9-7"]]) {
  const exp = expected(day);
  const row = doc.getElementById(id);
  ok(row, `day row ${id} exists`);
  if (!row) continue;
  const mdRows = row.querySelectorAll(".return-boat.md-boat");
  const lrRows = row.querySelectorAll(".return-boat:not(.md-boat)");
  ok(mdRows.length === exp.md.length, `${day}: ${mdRows.length} multi-day rows rendered, CSV has ${exp.md.length}`);
  ok(lrRows.length === exp.lr.length, `${day}: ${lrRows.length} LR rows rendered, RAW has ${exp.lr.length}`);
  const names = [...mdRows].map(e => e.querySelector(".return-boat-name").textContent.replace(/🛥️\s*/, "").replace(/(FL|HM|PL|SF)$/, "").trim()).sort();
  ok(names.join("|") === exp.md.map(r => r.boat).sort().join("|"), `${day}: boats ${names.join(", ")}`);
  ok(row.querySelector(".day-count").textContent.startsWith(String(exp.md.length + exp.lr.length)), `${day}: count badge`);
  ok(row.querySelector(".day-split").textContent === `${exp.lr.length} LR · ${exp.md.length} MD`, `${day}: split text`);
  ok(row.querySelector(".day-totals").textContent.includes(`~${exp.anglers}`), `${day}: total anglers ~${exp.anglers}`);
  const heavy = exp.md.length + exp.lr.length >= 3;
  ok(row.classList.contains("open") === heavy, `${day}: auto-open ${heavy}`);
}

/* ── 5. Trip Finder never shows multi-day boats ────────────────── */
const mdBoats = new Set(multi.map(t => t.boat));
for (const ym of finderMonths) {
  window.switchFinderMonth(ym);
  ok(!doc.querySelector("#finder-container .md-boat, #finder-container .landing-badge"), `finder ${ym} has no multi-day markup`);
  const txt = doc.getElementById("finder-container").textContent;
  ok(![...mdBoats].some(b => new RegExp("\\b" + b.replace(/[.*+?^${}()|[\]\\]/g, "\\$&") + "\\b").test(txt)), `finder ${ym} mentions no multi-day boat`);
}

/* ── 6. Header stamps ──────────────────────────────────────────── */
const stamp = doc.getElementById("multi-stamp");
ok(stamp && stamp.textContent.includes(MULTI_AS_OF), "multi-day stamp shows snapshot date");
ok(stamp && stamp.textContent.includes("4 landings"), "multi-day stamp names 4 landings");
const daysOld = (Date.now() - new Date(MULTI_AS_OF + "T12:00:00")) / 86400000;
ok(stamp.classList.contains("stamp-warn") === (daysOld > 14), `stale banner state matches age (${daysOld.toFixed(0)} d)`);
ok(doc.querySelector(".header p").textContent.includes("11 boats"), "header names 11 long-range boats");
ok(doc.getElementById("p-boats").textContent === `11 + ${mdBoats.size}`, `boats stat reads "11 + ${mdBoats.size}"`);

/* ── 7. Long-range block (RAW) ─────────────────────────────────── */
/* RAW used to be hand-maintained and drifted four months. It is generated now, so the
   page and data/longrange_trips.csv must agree, the encoding must stay legal, and Ed's
   own curation (his 'ed' flag, his shortened trip names) must have survived the refresh. */
const RAW = P("RAW"), LR_AS_OF = P("LR_AS_OF"), LR_SOURCES = P("LR_SOURCES");
const lrCsv = parseCSV(fs.readFileSync(path.join(ROOT, "data", "longrange_trips.csv"), "utf8"));

ok(Array.isArray(RAW), "RAW array exists");
ok(RAW.length === lrCsv.length, `RAW has ${RAW.length} rows, long-range CSV has ${lrCsv.length}`);
ok(/^20\d\d-\d\d-\d\d$/.test(LR_AS_OF), `LR_AS_OF is a date (${LR_AS_OF})`);
ok(Array.isArray(LR_SOURCES) && LR_SOURCES.length === BOATS.length,
   `LR_SOURCES covers all ${BOATS.length} boats`);
ok(LR_SOURCES.every(s => s.label && /^(ok|stale)$/.test(s.status)), "every boat has a status");
ok(LR_SOURCES.map(s => s.label).join("|") === BOATS.map(b => b.name).join("|"),
   "LR_SOURCES order matches BOATS");

let badRow = null, charterMispriced = null, edRows = 0;
for (const [idx, name, dep, days, cap, spots, price, flags] of RAW) {
  if (!(Number.isInteger(idx) && idx >= 0 && idx < BOATS.length) ||
      !/^20\d\d-\d\d-\d\d$/.test(dep) || !(days > 0 && days <= 30) ||
      !(typeof name === "string" && name.length) ||
      !(typeof price === "string" && price === price.trim()) ||
      !Array.isArray(flags) || !(spots >= -2 && spots <= cap || cap === -1)) badRow = badRow || [idx, name, dep];
  if (spots === -1 && price !== "Charter") charterMispriced = charterMispriced || [idx, name, dep, price];
  if (flags.includes("ed")) edRows++;
}
ok(!badRow, `every RAW row is well formed${badRow ? " — bad: " + JSON.stringify(badRow) : ""}`);
ok(!charterMispriced, `charter rows are priced "Charter"${charterMispriced ? " — bad: " + JSON.stringify(charterMispriced) : ""}`);
ok(edRows === 1, `Ed's own trip flag survived the refresh (found ${edRows})`);
ok(RAW.some(r => r[7].includes("invite")), "invite-only trips are flagged");
ok(new Set(RAW.map(r => r[0])).size === BOATS.length, "every boat has at least one trip");

// history is kept: the page still carries trips that already departed
const todayISO = new Date().toISOString().slice(0, 10);
ok(RAW.some(r => r[2] < todayISO), "departed trips are carried forward, not truncated");
ok(RAW.some(r => r[2] > todayISO), "future trips are present");

// the two surfaces stay disjoint — a long-range boat must never appear in MULTI
ok(!MULTI.some(r => BOATS.some(b => b.name.toLowerCase().replace(/\.$/, "") ===
     String(r[1]).toLowerCase().replace(/\.$/, ""))),
   "no long-range boat leaked into the multi-day block");

const lrStamp = doc.getElementById("lr-stamp");
ok(lrStamp && lrStamp.textContent.includes(LR_AS_OF), "long-range stamp shows its snapshot date");
ok(lrStamp && lrStamp.textContent.includes(`${BOATS.length} boats`), "long-range stamp counts the boats");
const lrStale = LR_SOURCES.some(s => !s.as_of || s.status !== "ok" ||
  (Date.now() - new Date(s.as_of + "T12:00:00")) / 86400000 > 14);
ok(lrStamp.classList.contains("stamp-warn") === (!LR_AS_OF || !LR_SOURCES.length || lrStale),
   "long-range stale banner state matches the per-boat statuses");

/* ── 8. Processing Calculator rates are cash figures ───────────── */
/* calcQuotes adds each processor's ccFee on top, so a stored rate must never be a value
   from a published credit-card column or the fee is applied twice. */
const PROCESSORS = P("PROCESSORS");
ok(PROCESSORS.length === 2, "two processors are compared");
for (const p of PROCESSORS) {
  ok(p.ccFee > 0 && p.ccFee < 0.1, `${p.key} has a plausible card fee`);
  for (const [field, v] of Object.entries(p.rates)) {
    ok(typeof v === "number" && v >= 0, `${p.key}.${field} is a number`);
  }
}
const fs5 = PROCESSORS.find(p => p.key === "fs");
ok(fs5.rates.big === fs5.rates.small,
   "Five Star quotes under-10 lb fish at the same rate (they publish no separate schedule)");

console.log(`\n${pass} passed, ${fail} failed`);
process.exit(fail ? 1 : 0);
