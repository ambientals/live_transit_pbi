# Transit Analytics Power BI Dashboard

---

> **Goal:** Build an interactive Power BI report from real-world public transit data (BVG/VBB in Berlin), focused on data modeling and dataviz, powered by a lightweight, free, and serverless pipeline.
>
> **Status — 2026-10-12: IN PROGRESS.** ETL pipeline is complete and verified.
> Dashboard's modeling depth and DAX measures are under development.
> See [Next steps](#next-steps) below for a more actionable recap.

---

**Abstract:**

End-to-end, zero-cost analytics pipeline (Python / GitHub Actions / Power BI), that turns a live transit API into a historical reliability dashboard.
Serverless ELT pipeline + Power BI analytics on public transit data:

- A Python bridge harvests departures into a self-trimming ("rolling") CSV via GitHub Actions;
- Power BI models it into an interactive reliability dashboard — on-time %, rush-hour degradation, line rankings — with no cloud warehouse and no license cost.

**Talking points:**

- **Problem:** transit APIs are ephemeral; historical analysis normally requires paid warehousing/streaming infrastructure.
- **Solution:** serverless ELT (Actions -> rolling flat file) + Import-mode semantic model with contextual DAX.
- **Engineering judgment:** a real-time streaming variant (Power BI push datasets) was prototyped, evaluated and archived — tradeoffs in `_archive/`.
- **Analytics:** contextual measures (vs city average), conditional formatting, slicer-driven storytelling.

**Improvement points**

For a monitoring project of real proportions, one instead would rather make better use of paid (FOSS or not):

- cloud storage to store cold, historical data.
- cloud ETL service for the jobs and scheduling.
- IoT streaming BI platform for real-time dataviz.

---

## Table of Contents

- [NEEDS AN UPDATE]

---

## Repository layout

```text
live_transit_pbi/
|-- .github/workflows/main.yml      # trigger-only pipeline: workflow_dispatch (station input), runs script and commits data CSV + log CSV.
|-- data/transit_history.csv        # rolling history = pure payload (the Power BI source)
|-- logs/runs.csv                   # run log = receipt (one line per execution)
|-- docs/                           # design notes
|-- pbip_dev_%/                     # Power BI project
|   |-- pbip_dev_%.Report/          # report: pages and visuals
|   `-- pbip_dev_%.SemanticModel/   # data model: transit_history
|-- scripts/
|   |-- update_transit.py           # data bridge: fetch from API -> append to CSV -> trim + write run log
|-- .env.example                    # template for local secrets
`-- README.md                       # this document
```

Specifically:

- `pbip_dev_%/` — the Power BI project: a semantic model + a report connected to the CSV files.

- `logs/runs.csv` — the run log = the receipt. Contais one line per execution: `ok` / `empty` / `skip`.

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
Power BI  (pbip_dev_%)
```

> **Note:** Initial major version presented real-time data streaming, but was replaced.
> On a free tenant, PBI Streaming Datasets only work well on dashboard tiles (no Desktop modeling/DAX), but the loop needs an always-on machine and the app cannot be published.
> Historical record (mainly 'live-transit-pbi.md' and 'push_vbb.py') can be found in previous commits.

## Execution prerequisites

- Power BI Desktop & Power BI Service account.
- Python 3 (for local testing) + `requests`.
- GitHub account with public repo + fine-grained PAT (Personal Access Token): free Actions minutes for repo write transactions.
- cron-job.org account (free, no card).

---

## Pipeline observability

The transit CSV carries only the pipeline's payload, never its state.
Its "receipt" lives separately in `logs/runs.csv`, where each record represents each run, commited to GitHub (including skips/missing API responses).
Layout:

```csv
Timestamp;GitHubRunId;Station;Status;Rows;Note
2026-10-10T19:00:00Z;123456;Alexanderplatz;ok;15;
2026-10-10T19:15:00Z;123457;Alexanderplatz;skip;0;locations lookup failed (upstream down?)
2026-10-10T19:30:00Z;123458;Alexanderplatz;empty;0;no departures returned (late night)
```

- **`ok`** — appended rows (data arrived); no annotation. Run ends green/OK.
- **`empty`** — valid response but 0 departures (quiet window, benign); `::notice::` (neutral). Run ends green/OK.
- **`skip`** — upstream unavailable (transient outage); `::warning::` (yellow). Run ends green/OK.

### How to check if data was sent or not

- Using Github UI:

| Feature          | Triggered in code                         | Where it shows up                         |
| ---------------- | ----------------------------------------- | ----------------------------------------- |
| Workflow command | `print("::warning::…")` / `::notice::…`   | "Annotations", on the run summary page    |
| Step summary     | `emit_summary()` → `$GITHUB_STEP_SUMMARY` | "Summary" markdown block, in the job view |

- Not using Github UI:
  - `git log --oneline -- logs/runs.csv` → one commit per run, message tagged `[ok]` / `[skip]` / `[empty]`.
  - Open `logs/runs.csv` for the full history.

## Scheduling setup

The GitHub pipeline/workflow is triggered programatically from its outside (as internal Github cron-jobs tend not to follow schedule).
To run the automation:

1. Create a GitHub fine-grained PAT scoped to this repo, with "Actions: Read and write".
2. On cron-job.org, create a job:
   - URL: `https://api.github.com/repos/ambientals/live_transit_pbi/actions/workflows/main.yml/dispatches`
   - Method: POST
   - Headers: `Authorization: Bearer <PAT>`, `Accept: application/vnd.github+json`, `Content-Type: application/json`
   - Body: `{"ref":"main"}`
   - Schedule: every 15 minutes
3. Use cron-job.org's "Run now" to test; a `workflow_dispatch` run should appear on GitHub.

## Status & incident log

| Time (UTC+0)            | Event                                                                                                   |
| ----------------------- | ------------------------------------------------------------------------------------------------------- |
| 2026-10-10, 03:57       | Run#1 — manual — green, 13s                                                                             |
| 2026-10-10, 08:38       | Run#2 — scheduled — red: `KeyError: 0` (API returned empty)                                             |
| 2026-10-10, ~09:00      | Manual re-run — green                                                                                   |
| 2026-10-10, 08:40-10:00 | No further cron runs despite`*/15` -> GitHub free-tier cron throttling suspected                        |
| 2026-10-10, later       | Runs KO with`ReadTimeout` — VBB `transport.rest` API down (timeout / 503)                               |
| 2026-10-10, (evening)   | Root cause = flaky VBB API, not GitHub scheduling. Fixed: graceful skip + run-log receipt               |
| 2026-10-11, 16:44–16:46 | Runs#5–#7 — first cron-job.org dispatches (test runs + first slot) — red: VBB timeout window / overlaps |
| 2026-10-11, 16:46       | TEST RUN → HTTP 204 +`x-accepted-github-permissions: actions=write` — fine-grained PAT verified         |
| 2026-10-11, 17:00       | Run#8 — first external scheduled dispatch — green 13s (cron-job.org: 204 in 1.41s)                      |
| 2026-10-11, later       | `concurrency` guard added to `main.yml`; job **paused by choice** pending Phase 1                       |

---

## Power BI app

Currently a working proof-of-concept, not the final report.

**Semantic model** (`pbip_dev_%.SemanticModel`):

- Table `transit_history`: `Timestamp` (dateTime), `Line` (text), `Direction` (text), `DelaySec` (int).
- Date table (`LocalDateTable`) with a relationship `transit_history.Timestamp` -> `LocalDateTable.Date` (enables time intelligence).
- The M query loads the CSV from the raw GitHub URL with `Delimiter=";"` and `Encoding=65001` (UTF-8), so the semicolon format and diacritics are handled correctly.

**Report** (`pbip_dev_%.Report`):

- 1 page ("Page 1"), 1 visual — a minimal skeleton. Visuals and DAX measures are still to be built.

**Still missing (the gap between the POC and the storyboard):**

- No DAX measures are defined in the model yet — the library below is the plan, not the implementation.
- No measures table, no time-of-day dimension (required for the rush-hour curve), no delay-severity buckets.
- The report is a single raw `tableEx` dump, not a dashboard: no KPIs, charts, slicers, conditional formatting or tooltips.

**TBD:** "pipeline health" page in Power BI reading `logs/runs.csv` — runs over time, ok/empty/skip split, rows-per-run, and gap detection. It turns the pipeline's own reliability into a second story alongside the transit data.

## PL-300 applied skills map

How this project maps to the four exam domains, and where it still needs work:

| Domain              | Weight | Status | What it proves / what's still needed                                                                                                              |
| ------------------- | ------ | ------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| Prepare the data    | ~25%   | 🟡     | M query loads + types the CSV; still needs profiling and derived dimension columns (p.es. hour, weekday) and metric columns (p.es. delay buckets) |
| Model the data      | ~25%   | 🟡     | Star schema + date table ✅; still needs measures and measures table, time-of-day dimension, and severity buckets classification                  |
| Visualize & analyze | ~25%   | 🔴     | One raw table only; needs the storyboard (KPIs, charts, conditional formatting, tooltips)                                                         |
| Deploy & maintain   | ~15%   | 🟡     | PBIP + git = ALM ✅; run log + graceful skip = monitoring ✅; still needs publish, refresh, RLS for monitoring page                               |

## App storyboard

Each row answers one commuter question, that completes the "story" the dashboard tells:

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

---

## Next steps

**Phase 0 — backend ETL: IN PROGRESS**

- [x] Data source verified (`v6.vbb.transport.rest`).
- [x] Harden `update_transit.py` (retries, validation, graceful skip, run-log receipt).
- [x] External scheduling via cron-job.org (204 verified; first scheduled run green).
- [x] Overlap guard (`concurrency` block added to `main.yml`).
- [ ] **Operations:** Enable cron-job.org failure notifications (email/webhook) to catch silent API drops.

**Phase 1 — model depth (PL-300 "Model the data"): TBD**

- [ ] Add a measures table and implement the DAX library below.
- [ ] Add a time-of-day dimension (`Hour`, `RushHour` flag, `Weekday/Weekend`) — required for the rush-hour curve.
- [ ] Add delay-severity buckets (on time / late / very late) for the conditional-color KPI cards.
- [ ] _Optional:_ Role-level security demo (a role filtered by `Line`) for the "Deploy & maintain" domain.

**Phase 2 — the dashboard (PL-300 "Visualize & analyze"): TBD**

- [ ] Build the storyboard below in Power BI Desktop, then commit the PBIP.
- [ ] Apply a custom transit theme (see "Design language" below).
- [ ] Add a "pipeline health" page over `logs/runs.csv`.

**Phase 3 — deploy & maintain (PL-300 "Deploy & maintain"): TBD**

- [ ] Publish + scheduled refresh (free tier, 8 refreshes/day); optional workspace app / dashboard.

---

## NOTES

- [OPTIONAL?] Maybe create a local process/ client daemon to, on remote repo status change, synchronize/push from it (in order to push the new data and have it always fresh).
