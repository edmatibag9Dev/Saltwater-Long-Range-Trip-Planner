# Agent Behavior Rules — GitHub Operations
# Ed Matibag — Global AI Agent Standards
# Location: ~/Documents/Claude/AGENTS.md
# Last updated: 2026-06-02

---

## Purpose

These rules govern how Claude (and any AI agent) must behave when working with Ed's GitHub repositories. They exist to prevent incomplete commits, stub READMEs, broken pushes, and loss of context between sessions.

---

## Rule 1 — Repo Bootstrap Check

**At the start of any task involving a GitHub repository:**

1. List the repo contents via `GET /repos/{owner}/{repo}/contents/`
2. Check for `CONTRIBUTING.md` and `AGENTS.md`
3. If either file is missing — push the canonical version from `~/Documents/Claude/` **before doing anything else**
4. Read both files completely before writing any code, committing anything, or modifying the README

> Do not skip this check even if you are confident the files exist. Always verify.

---

## Rule 2 — Commit Standards

Follow `~/Documents/Claude/CONTRIBUTING.md` exactly. Summary:

- All `feat`, `fix`, `data` commits require a body with ≥ 3 bullets
- No one-liner commits — ever
- Subject line: imperative mood, max 72 chars
- Body: specific bullets describing what changed, why, and any caveats

---

## Rule 3 — README on Every Feature Commit

Every `feat`, `fix`, or `data` commit must update the README. The README must:

- Have all 9 required sections (see CONTRIBUTING.md)
- Be ≥ 400 words
- Include updated data source links, feature descriptions, and usage instructions
- Never be a stub

---

## Rule 4 — GitHub Contents API Protocol

In sandbox environments where `git clone` is blocked, use the GitHub Contents API.

**Always follow this sequence for updates:**
1. `GET /repos/{owner}/{repo}/contents/{path}` — retrieve current SHA
2. `PUT` with `{ message, content (base64), sha }` — push update

Skipping the GET will cause a **409 Conflict**. This is a known failure mode — always GET first.

**Token handling:**
- Ed provides the PAT each session — do not store it in any file or memory
- Verify token has Contents: Read & Write permission if a 403 is returned
- Use `GET /user` to confirm the authenticated username before any push

---

## Rule 5 — Data Freshness Disclosure

When the dashboard or tool contains scraped or snapshot data:

- Always include a data freshness note in the README
- Always include a visible disclaimer in the UI
- Always link to the live source so the user can verify current data
- Document the scraping method and any known blockers (e.g. CAPTCHA)

---

## Rule 6 — Scraping Protocol (fishingreservations.net)

Specific to Ed's saltwater fishing tools:

- `fishingreservations.net` blocks rapid sequential automated requests (CAPTCHA error 338)
- **Workaround:** Ed opens all boat URLs in browser tabs manually, then Claude reads via the Claude in Chrome MCP extension
- Shogun typically loads clean on the first automated request before blocking kicks in
- Red Rooster III (`redrooster3.com`) scrapes cleanly — different domain, no CAPTCHA

---

## Rule 7 — Ed's Repo Inventory

| Repo | Purpose | Key File |
|------|---------|---------|
| `Saltwater-Long-Range-Trip-Planner` | Trip finder + fish processing planner | `saltwater_trip_planner.html` |
| `ai-task-manager` | AI-powered task management app | Next.js app |
| `Wiki-Page-from-Open-Brain` | Wiki generator from Open Brain thoughts | `open-brain-wiki.html` |

GitHub username: `edmatibag9Dev`

---

## Rule 8 — Self-Contained Deliverables

When building HTML dashboards or tools:

- Single file — all CSS and JS inline, no external dependencies
- Must open directly in browser (`file://`) with no build step
- No localStorage — use in-memory JS state
- All data links open in new tab
- Include a visible "data as of [date]" disclaimer when showing snapshot data

---

## Rule 9 — Session Continuity

At the start of any session involving a known project:

1. Read `~/Documents/Claude/CONTRIBUTING.md` and `AGENTS.md`
2. Check memory for project context (`project_saltwater_planner.md` etc.)
3. Check the repo for current file state before making changes
4. Never assume the previous session's work is still current — verify by reading files

---

## Rule 10 — Never Do These

- ❌ Push a stub or placeholder README
- ❌ Write a one-liner commit message on a feat/fix/data commit
- ❌ Update an existing GitHub file without getting its SHA first
- ❌ Store Ed's PAT in any file, memory, or log
- ❌ Assume git clone will work in a sandbox — use the Contents API
- ❌ Skip the CONTRIBUTING.md / AGENTS.md bootstrap check
- ❌ Leave a dashboard without a data freshness disclaimer
