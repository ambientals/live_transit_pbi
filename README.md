# Transit Analytics Power BI Dashboard

> **Status — 2026-10-11: IN PROGRESS.** The ETL pipeline is complete and verified (external scheduling tested & paused by choice; rolling CSV + run log active). Still open: the DAX measures / modeling depth and the final dashboard (currently a 1-table skeleton). See the [PL-300 skills map](#pl-300-skills-map) and [Next steps](#next-steps) below.

**Goal:** Build an interactive Power BI report from real-world public transit data (BVG/VBB in Berlin), focused on data modeling and dataviz, powered by a lightweight, free pipeline.

---

## Table of Contents

- [What's in this repo](#whats-in-this-repo)
- [Current architecture](#current-architecture)
- [Pipeline run log (observability)](#pipeline-run-log-observability)
- [Power BI app](#power-bi-app)
- [PL-300 skills map](#pl-300-skills-map)
- [Status & incident log](#status--incident-log)
- [Next steps](#next-steps)
- [Scheduling setup](#scheduling-setup)
- [Power BI storyboard](#power-bi-storyboard-report-plan)
- [DAX measures library](#dax-measures-library)
- [Portfolio narrative](#portfolio-narrative)

---

## What's in this repo

- `scripts/update_transit.py` — the data bridge: fetch VBB departures, append to a rolling CSV, and write a run-log receipt (gracefully skips when the API is down).
- `.github/workflows/main.yml` — trigger-only pipeline: `workflow_dispatch` (with a `station` input); runs the script and commits the CSV + run log. No internal cron.
- `pbip_dev_02/` — the Power BI project (POC): a semantic model + a 1-page report connected to the CSV.
- `data/transit_history.csv` — the rolling history = the pure payload (the Power BI source).
- `logs/runs.csv` — the run log = the receipt (one line per execution: `ok` / `empty` / `skip`).
- `docs/` — design notes.

## Current architecture

```text
cron-job.org (external scheduler, free)
        |  POST .../dispatches  (PAT header)
        v
GitHub Actions  (workflow_dispatch, input: station)
        |  update_transit.py: fetch VBB -> append -> trim CSV + write run log, commit
        v
data/transit_history.csv  (payload)   +   logs/runs.csv  (receipt)
        |  raw URL (Power BI Web connector)
        v
Power BI  (pbip_dev_02)
```

## Repository layout

```text
live_transit_pbi/
|-- .github/workflows/main.yml      # trigger-only pipeline: workflow_dispatch (station input)
|-- data/transit_history.csv        # rolling history = pure payload (the Power BI source)
|-- logs/runs.csv                   # run log = receipt (one line per execution)
|-- docs/                           # design notes
|-- pbip_dev_02/                    # Power BI project (POC)
|   |-- pbip_dev_02.Report/         # report: 1 page, 1 visual (skeleton)
|   `-- pbip_dev_02.SemanticModel/  # model: transit_history + date table
|-- scripts/
|   |-- update_transit.py           # data bridge: fetch -> append -> trim + write run log
|   `-- push_vbb.py                 # v1 streaming bridge (superseded)
|-- _archive/                       # v1 prototype + old workflow (historical)
|-- .env.example                    # template for local secrets
`-- README.md
```

## Pipeline run log (observability)

The CSV is **payload only** — it never carries pipeline state. The **receipt** lives separately in `logs/runs.csv`, one line per execution, committed to git on every run (including skips):

```csv
Timestamp;GitHubRunId;Station;Status;Rows;Note
2026-10-10T19:00:00Z;123456;Alexanderplatz;ok;15;
2026-10-10T19:15:00Z;123457;Alexanderplatz;skip;0;locations lookup failed (upstream down?)
2026-10-10T19:30:00Z;123458;Alexanderplatz;empty;0;no departures returned (late night)
```

- **`ok`** — appended rows (data arrived); no annotation — the run is simply green.
- **`empty`** — valid response but 0 departures (quiet window, benign); `::notice::` (neutral).
- **`skip`** — upstream unavailable (transient outage); `::warning::` (yellow) — run stays green.

How to check "was data sent or not":

- `git log --oneline -- logs/runs.csv` → one commit per run, message tagged `[ok]` / `[skip]` / `[empty]`.
- Open `logs/runs.csv` for the full history.

Two separate GitHub features carry the state, and they land in different places:

| Feature          | Trigger in code                           | Where it shows                               |
| ---------------- | ----------------------------------------- | -------------------------------------------- |
| Workflow command | `print("::warning::…")` / `::notice::…`   | "Annotations" on the run summary page        |
| Step summary     | `emit_summary()` → `$GITHUB_STEP_SUMMARY` | The "Summary" markdown block in the job view |

> **Note on GitHub Annotations:** There is no "positive" annotation command in GitHub Actions — a clean run is green by default (the _absence_ of a warning/error), and the step summary carries the "Appended N rows" line. `::error::` (red) is the only failing annotation; `::notice::` (neutral) and `::warning::` (yellow) both leave the run green.

**Planned (not built yet):** a "pipeline health" page in Power BI reading `logs/runs.csv` — runs over time, ok/empty/skip split, rows-per-run, and gap detection. It turns the pipeline's own reliability into a second story alongside the transit data.

## Power BI app

Currently a working proof-of-concept, not the final report.

**Semantic model** (`pbip_dev_02.SemanticModel`):

- Table `transit_history`: `Timestamp` (dateTime), `Line` (text), `Direction` (text), `DelaySec` (int).
- Date table (`LocalDateTable`) with a relationship `transit_history.Timestamp` -> `LocalDateTable.Date` (enables time intelligence).
- The M query loads the CSV from the raw GitHub URL with `Delimiter=";"` and `Encoding=65001` (UTF-8), so the semicolon format and diacritics are handled correctly.

**Report** (`pbip_dev_02.Report`):

- 1 page ("Page 1"), 1 visual — a minimal skeleton. Visuals and DAX measures are still to be built.

**Still missing (the gap between the POC and the storyboard):**

- No DAX measures are defined in the model yet — the library below is the plan, not the implementation.
- No measures table, no time-of-day dimension (required for the rush-hour curve), no delay-severity buckets.
- The report is a single raw `tableEx` dump, not a dashboard: no KPIs, charts, slicers, conditional formatting or tooltips.

## PL-300 skills map

How this project maps to the four exam domains, and where it still needs work:

| Domain              | Weight | Status | What it proves / what's still needed                                                                       |
| ------------------- | ------ | ------ | ---------------------------------------------------------------------------------------------------------- |
| Prepare the data    | ~25%   | 🟡     | M query loads + types the CSV; still needs profiling and derived columns (hour, weekday, delay bucket)     |
| Model the data      | ~25%   | 🟡     | Star schema + date table ✅; still needs measures, measures table, time-of-day dim, severity buckets       |
| Visualize & analyze | ~25%   | 🔴     | One raw table only; needs the storyboard (KPIs, charts, conditional formatting, tooltips)                  |
| Deploy & maintain   | ~15%   | 🟡     | PBIP + git = ALM ✅; run log + graceful skip = monitoring ✅; still needs publish, refresh, (optional) RLS |

## Prerequisites

- Power BI Desktop & Power BI Service account.
- Python 3 (for local testing) + `requests`.
- GitHub account (public repo = free Actions minutes).
- cron-job.org account (free, no card) + a GitHub fine-grained PAT (Actions: write on this repo).

## Status & incident log

### 2026-10-10

| Time (UTC)  | Event                                                                                     |
| ----------- | ----------------------------------------------------------------------------------------- |
| 03:57       | Run #1 — manual — green, 13s                                                              |
| 08:38       | Run #2 — scheduled — red: `KeyError: 0` (API returned empty)                              |
| ~09:00      | Manual re-run — green                                                                     |
| 08:40-10:00 | No further cron runs despite `*/15` -> GitHub free-tier cron throttling suspected         |
| later       | Runs KO with `ReadTimeout` — VBB `transport.rest` API down (timeout / 503)                |
| (evening)   | Root cause = flaky VBB API, not GitHub scheduling. Fixed: graceful skip + run-log receipt |

### 2026-10-11

| Time (UTC)  | Event                                                                                                    |
| ----------- | -------------------------------------------------------------------------------------------------------- |
| 16:44–16:46 | Runs #5–#7 — first cron-job.org dispatches (test runs + first slot) — red: VBB timeout window / overlaps |
| 16:46       | TEST RUN → HTTP 204 + `x-accepted-github-permissions: actions=write` — fine-grained PAT verified         |
| 17:00       | Run #8 — first external scheduled dispatch — green 13s (cron-job.org: 204 in 1.41s)                      |
| later       | `concurrency` guard added to `main.yml`; job **paused by choice** pending Phase 1                        |

## Next steps

**Phase 0 — backend ETL: DONE (verified 2026-10-11; job paused by choice)**

- [x] Data source verified (`v6.vbb.transport.rest`).
- [x] Harden `update_transit.py` (retries, validation, graceful skip, run-log receipt).
- [x] External scheduling via cron-job.org (204 verified; first scheduled run green).
- [x] Overlap guard (`concurrency` block added to `main.yml`).
- [ ] **Ops:** Enable cron-job.org failure notifications (email/webhook) to catch silent API drops.
- [ ] **Ops:** Calendar reminder for PAT expiry (**2027-01-09**) — expiry fails silently with 401.
- [ ] **Decision:** Re-enable cron-job.org scheduler when Phase 1 starts (model needs fresh data).

**Phase 1 — model depth (PL-300 "Model the data")**

- [ ] Add a measures table and implement the DAX library below.
- [ ] Add a time-of-day dimension (`Hour`, `RushHour` flag, `Weekday/Weekend`) — required for the rush-hour curve.
- [ ] Add delay-severity buckets (on time / late / very late) for the conditional-color KPI cards.
- [ ] _Optional:_ Role-level security demo (a role filtered by `Line`) for the "Deploy & maintain" domain.

**Phase 2 — the dashboard (PL-300 "Visualize & analyze")**

- [ ] Build the storyboard below in Power BI Desktop, then commit the PBIP.
- [ ] Apply a custom transit theme (see "Design language" below).
- [ ] Add a "pipeline health" page over `logs/runs.csv`.

**Phase 3 — deploy & maintain (PL-300 "Deploy & maintain")**

- [ ] Publish + scheduled refresh (free tier, 8 refreshes/day); optional workspace app / dashboard.

## Scheduling setup

> Note: the cron-job.org job is currently **paused** — re-enable it when you want unattended collection to resume.

This GitHub pipeline/workflow is intentionally trigger-only (no internal cron). To run it automatically:

1. Create a GitHub **fine-grained PAT** scoped to this repo, with **Actions: Read and write**.
2. On cron-job.org, create a job:
   - URL: `https://api.github.com/repos/ambientals/live_transit_pbi/actions/workflows/main.yml/dispatches`
   - Method: POST
   - Headers: `Authorization: Bearer <PAT>`, `Accept: application/vnd.github+json`, `Content-Type: application/json`
   - Body: `{"ref":"main"}`
   - Schedule: every 15 minutes
3. Use cron-job.org's "Run now" to test; a `workflow_dispatch` run should appear on GitHub.

## Power BI storyboard (report plan)

Each row answers one commuter question — the "story" the dashboard tells:

- _Which line ruins my commute?_ → line ranking
- _When is it worst?_ → rush-hour curve
- _Is today worse than normal?_ → time intelligence vs. city average
- _Which direction is the friction?_ → on-time vs. late by direction

| Row                    | Content                                                 | Visual                                   |
| ---------------------- | ------------------------------------------------------- | ---------------------------------------- |
| KPI row                | Total departures, avg delay, on-time %, severe-delay %  | Cards with conditional color             |
| Story row, left (60%)  | "Rush-hour effect": avg delay by hour of day            | Line/area chart + average reference line |
| Story row, right (40%) | "Directional friction": on-time vs delayed by direction | Donut / 100% stacked bar                 |
| Category row           | "Usual suspects": avg delay per line, sorted desc       | Bar chart, green->red gradient           |
| Detail row             | Line -> Direction with volumes & reliability            | Matrix + conditional data bars           |

### Design language

Treat the dashboard like architecture (one clear idea per view, negative space, a deliberate palette) rather than decoration:

- **Identity:** Berlin transit (BVG yellow `#F0D722`) as the accent on the dark `ReportThemeDark` base.
- **Palette:** accent yellow + neutral dark slate + a green -> amber -> red gradient for `DelaySec`.
- **Type:** a single clean sans (Segoe UI / Inter / DIN-style, fitting the transit theme), 2-3 weights max.
- **Grid:** one consistent margin/column grid across all pages; each visual gets breathing room.

## DAX measures library

```dax
Total Departures = COUNTROWS('transit_history')

Avg Delay (Mins) =
DIVIDE(SUM('transit_history'[DelaySec]), COUNTROWS('transit_history'), 0) / 60

On-Time % =
VAR OnTime = CALCULATE(COUNTROWS('transit_history'), 'transit_history'[DelaySec] <= 0)
RETURN DIVIDE(OnTime, [Total Departures], 0)

Severe Delay % =
VAR Severe = CALCULATE(COUNTROWS('transit_history'), 'transit_history'[DelaySec] > 300)
RETURN DIVIDE(Severe, [Total Departures], 0)

Delay vs City Average =
VAR CityAvg = CALCULATE([Avg Delay (Mins)], ALL('transit_history'))
RETURN [Avg Delay (Mins)] - CityAvg
```

## Portfolio narrative

**Abstract (repo header / CV):**

> Serverless ELT pipeline + Power BI analytics on public transit data. A Python bridge harvests departures into a self-trimming ("rolling") CSV via GitHub Actions; Power BI models it into an interactive reliability dashboard — on-time %, rush-hour degradation, line rankings — with no cloud warehouse and no license cost.

**Talking points:**

- **Problem:** transit APIs are ephemeral; historical analysis normally requires paid warehousing/streaming infrastructure.
- **Solution:** serverless ELT (Actions -> rolling flat file) + Import-mode semantic model with contextual DAX.
- **Engineering judgment:** a real-time streaming variant (Power BI push datasets) was prototyped, evaluated and archived — tradeoffs in `_archive/`.
- **Analytics:** contextual measures (vs city average), conditional formatting, slicer-driven storytelling.

**CV one-liner:**

> Built an end-to-end, zero-cost analytics pipeline (Python / GitHub Actions / Power BI) turning a live transit API into a historical reliability dashboard.

## Swap-in Sources (Alternative APIs)

Change only the `FETCH`/shape block in `update_transit.py`:

- **Italy (Trenord):** ViaggiaTreno API (`partenze/{station_id}/{timestamp}`)
- **Planes over your city:** OpenSky Network API (`states/all?lamin=...`)
- **Local Weather:** Open-Meteo API (free, no key)
- **Air Quality:** Sensor.Community API

---

## Appendix — v1 real-time streaming prototype (superseded)

Historical record in [`_archive/live-transit-pbi.md`](_archive/live-transit-pbi.md); bridge code in [`scripts/push_vbb.py`](scripts/push_vbb.py).

**Why replaced:** streaming datasets only drive dashboard tiles (no Desktop modeling/DAX), the data is ephemeral, and the loop needs an always-on machine — not serverless.
