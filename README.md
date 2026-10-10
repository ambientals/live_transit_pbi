# Transit Analytics Power BI Dashboard

---

> **Status — 2026-10-10: RE-ARCHITECTED, verification pending.**
> Internal GitHub cron removed after confirmed free-tier throttling; scheduling moved to an external alarm clock (cron-job.org → `workflow_dispatch`). Fetch logic hardened (retries + payload validation). Manual runs are green; awaiting the first externally-triggered runs before flipping to operational.

**Goal:** Build an interactive Power BI report using real-world public transit data (BVG/VBB in Berlin or Trenord in Italy). The focus is on data modeling and dataviz, powered by a lightweight, free and _reliably scheduled_ pipeline.

---

## Changelog

- **v03 (2026-10-10):** external alarm clock replaces internal cron; station parameterized via workflow input; hardened fetch (`get_json`); incident log + decisions log; known-boundary note for live dropdown.
- **v02 (2026-10-10):** status/blocker section, repo layout, storyboard, DAX library, portfolio narrative.
- **v01 (2026-10-10):** original rolling-CSV documentation.

---

## Architecture

```text
cron-job.org (external alarm clock — free, no card)
        │  POST .../dispatches  (PAT in header)
        ▼
GitHub Actions (workflow_dispatch · input: station)
        │  runs scripts/update_transit.py
        ▼
Public API (VBB, Trenord, …) ──fetch──► Python bridge (retries + validation)
        │  write / trim rolling CSV
        ▼
GitHub repo → data/transit_history.csv
        │  raw URL (Web connector, Anonymous)
        ▼
Power BI Desktop / Service (Import mode · 8 refreshes/day on Free)
```

Historical records: v1 real-time streaming prototype → [`_archive/live-transit-pbi.md`](_archive/live-transit-pbi.md); v02 internal-cron pipeline → git history.

## Repository layout

```text
live_transit_pbi/
├── .github/workflows/main.yml   # trigger-only pipeline (workflow_dispatch + inputs)
├── data/transit_history.csv     # rolling history — the Power BI source
├── docs/                        # design notes & report screenshots
├── pbip_dev_01/                 # Power BI project (Report + SemanticModel)
│   └── transit_pbi_v01.pbip
├── scripts/
│   ├── update_transit.py        # current bridge: fetch → append → trim (hardened)
│   └── push_vbb.py              # v1 streaming bridge (superseded, reference only)
├── _archive/                    # v1 docs & workflow (historical record)
├── .env.example                 # template for local secrets (.env must stay gitignored)
└── README.md
```

## Prerequisites

- Power BI Desktop & Power BI Service account
- Python 3 (local testing) + `requests`
- GitHub account (public repo = free unlimited Actions minutes)
- cron-job.org account (free, no card) + a GitHub PAT used **only** inside cron-job.org

---

## Status & incident log (2026-10-10)

| Time (UTC)  | Event                                                                                         |
| ----------- | --------------------------------------------------------------------------------------------- |
| 03:57       | Run #1 — manual (`workflow_dispatch`) — ✅ green, 13s                                         |
| 08:38       | Run #2 — scheduled — ❌ red, 14s: `KeyError: 0` at `station_id = loc[0]["id"]`                |
| ~09:00      | Manual re-run after hardening fix — ✅ green                                                  |
| 08:40–10:00 | **No further internal cron runs at all** despite `*/15` → free-tier cron throttling confirmed |
| v03         | Internal cron removed; external alarm clock adopted; station parameterized                    |

### Root cause: two independent failure modes

| #   | Failure mode                                                                     | Symptom                                                                                          | Fix (v03)                                                                                              |
| --- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| 1   | Scheduler never wakes the job                                                    | Zero scheduled runs for >1h                                                                      | External alarm clock (cron-job.org → dispatch API)                                                     |
| 2   | API returns an error _object_ (transient 429/5xx from shared Actions egress IPs) | `KeyError: 0` — a `KeyError` (not `IndexError`) proves `loc` was a dict (error body), not a list | `get_json()`: HTTP status check, 3 retries with backoff, payload shape validation, printed diagnostics |

> Forensic note for future debugging: in the Actions log zip, only the file named after the red step matters (here: `5_Run python scripts_update_transit.py.txt`). Everything else is runner boilerplate.

---

## Phase 1 — The Python Bridge (rolling CSV, hardened)

[scripts/update_transit.py](scripts/update_transit.py) resolves the station **dynamically from a parameter** (no hardcoding), fetches departures with retries, appends to the CSV and trims the oldest rows so the repo never bloats.

```python
import os, time, requests, csv
from datetime import datetime, timezone

BASE = "https://v6.vbb.transport.rest"
STATION_QUERY = os.environ.get("VBB_STATION", "Alexanderplatz")  # parameter, not hardcode
CSV_FILE = "data/transit_history.csv"
FIELDS = ["Timestamp", "Line", "Direction", "DelaySec"]
MAX_ROWS = 15000
HDRS = {"User-Agent": "pbi-transit-portfolio/1.0 (hobby)"}


def get_json(url, params=None, tries=3, pause=10):
    """GET with status check, retries + backoff, loud diagnostics."""
    for attempt in range(1, tries + 1):
        r = requests.get(url, params=params, timeout=15, headers=HDRS)
        if r.status_code == 200:
            return r.json()
        print(f"attempt {attempt}/{tries}: HTTP {r.status_code} -> {r.text[:200]}")
        if attempt < tries:
            time.sleep(pause * attempt)
    raise SystemExit(f"API unreachable after {tries} attempts: {url}")


os.makedirs("data", exist_ok=True)

# 1) resolve station dynamically — but defended
loc = get_json(f"{BASE}/locations", params={"query": STATION_QUERY, "results": 1})
if not isinstance(loc, list) or not loc:
    raise SystemExit(f"Unexpected locations payload for '{STATION_QUERY}': {str(loc)[:200]}")
station_id = loc[0]["id"]
print("Station:", loc[0].get("name"), "| ID:", station_id)

# 2) departures — defended
data = get_json(f"{BASE}/stops/{station_id}/departures",
                params={"duration": 10, "results": 15})
deps = data.get("departures", []) if isinstance(data, dict) else data
if not isinstance(deps, list) or not deps:
    raise SystemExit(f"Unexpected departures payload: {str(data)[:200]}")

now = datetime.now(timezone.utc).isoformat()
payload = [{
    "Timestamp": now,
    "Line": (d.get("line") or {}).get("name", "?"),
    "Direction": d.get("direction", "?"),
    "DelaySec": d.get("delay") or 0,
} for d in deps]

# 3) rolling CSV: append + trim
lines = []
if os.path.exists(CSV_FILE):
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
header = lines[0] if lines else ",".join(FIELDS) + "\n"
kept = (lines[1:] + [
    f"{p['Timestamp']},{p['Line']},{p['Direction']},{p['DelaySec']}\n"
    for p in payload
])[-MAX_ROWS:]
with open(CSV_FILE, "w", encoding="utf-8") as f:
    f.write(header)
    f.writelines(kept)

print(f"appended {len(payload)} rows -> {len(kept)} rows kept")
```

## Phase 2 — GitHub Actions (trigger-only workflow)

The workflow no longer owns a schedule. It accepts a `station` input and can be triggered by: the external alarm clock, the GitHub "Run workflow" button, or (future) a Power BI / Power Automate one-click.

[.github/workflows/main.yml](.github/workflows/main.yml):

```yaml
name: transit-data-pipeline
on:
  workflow_dispatch:
    inputs:
      station:
        description: "Station name to track (VBB)"
        required: false
        default: "Alexanderplatz"

jobs:
  update-csv:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python scripts/update_transit.py
        env:
          VBB_STATION: ${{ inputs.station || 'Alexanderplatz' }}
      - name: Commit and push CSV
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add data/transit_history.csv || true
          git diff --cached --quiet || git commit -m "update transit data $(date -u +%H:%M)"
          git push
```

> ⚠️ The `git add` path, the script's `CSV_FILE`, and the Power BI Web-connector URL must all point to the same file (`data/transit_history.csv`).

## Phase 2b — The external alarm clock (cron-job.org)

GitHub's free-tier cron throttled this repo; a dedicated free cron service is now the clock. Setup:

1. **PAT:** create a GitHub Personal Access Token (classic `repo` scope, or fine-grained with _Actions: Read and write_ on this repo only). Store it **only** in cron-job.org — never in the repo.
2. **New job** in cron-job.org:
   - **URL:** `https://api.github.com/repos/ambientals/live_transit_pbi/actions/workflows/main.yml/dispatches`
   - **Method:** `POST`
   - **Headers:** `Authorization: Bearer <PAT>` · `Accept: application/vnd.github+json` · `Content-Type: application/json`
   - **Body:** `{"ref":"main","inputs":{"station":"Alexanderplatz"}}`
3. **Schedule:** every 5 or 15 minutes.
4. **Verify:** a new run appears in the Actions tab (actor = your user, via API) and a commit lands on `data/transit_history.csv`. Two consecutive green external runs → status flips to 🟢.

## Decisions log (v03 additions)

| Option                                  | Verdict | Reason                                                                                           |
| --------------------------------------- | ------- | ------------------------------------------------------------------------------------------------ |
| GitHub internal cron (free tier)        | ❌      | Throttled/delayed on free tier; silent gaps >1h at `*/15`                                        |
| cron-job.org external trigger           | ✅      | Free, no card, dedicated cron; reuses existing Actions pipeline                                  |
| Hardcoded station ID                    | ❌      | Station is a workflow input (`inputs.station`) — no hardcode, and a seed for the future dropdown |
| PySpark / Databricks                    | ❌      | Sledgehammer for a 15-row JSON fetch; adds cost & complexity                                     |
| Retry + validation wrapper (`get_json`) | ✅      | Survives transient 429/5xx from shared Actions egress IPs                                        |

---

## Phase 3 — Power BI Desktop project

1. **Get Data → Web** → `https://raw.githubusercontent.com/ambientals/live_transit_pbi/main/data/transit_history.csv` (Anonymous, Import mode).
2. **Power Query:** `Timestamp` → Date/Time; `DelaySec` → Whole Number; add `DelayMinutes = [DelaySec] / 60`; add an `Hour` column for time-series.
3. **Measures:** DAX library below. **Layout:** storyboard below.
4. Save as Power BI project: `pbip_dev_01/transit_pbi_v01.pbip`.

### Report layout (storyboard)

| Zone                   | Content                                                   | Visual                                   |
| ---------------------- | --------------------------------------------------------- | ---------------------------------------- |
| Header                 | Title, subtitle, last-refresh timestamp                   | Textboxes + card                         |
| Slicers (top right)    | Date range, Line, Direction                               | Slicers                                  |
| KPI row                | Total departures · Avg delay · On-time % · Severe-delay % | Cards with conditional color             |
| Story row, left (60%)  | "Rush-hour effect": avg delay by hour of day              | Line/area chart + average reference line |
| Story row, right (40%) | "Directional friction": on-time vs delayed by direction   | Donut / 100% stacked bar                 |
| Category row           | "Usual suspects": avg delay per line, sorted desc         | Bar chart, green→red gradient            |
| Detail row             | Line → Direction with volumes & reliability               | Matrix + conditional data bars           |

### DAX measures library

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

## Phase 4 — Publish & Schedule

1. **Publish** the `.pbip` to the free Service workspace.
2. Dataset settings → **Scheduled refresh** ON (Free tier: up to 8/day).
3. Accepted tradeoff: the CSV updates every 5–15 min; PBI Free pulls it 8 times a day — the price of staying 100% free and flexible.

## Known boundary: live station dropdown (future)

A dropdown that instantly re-queries the API on selection is a _live app_ pattern (DirectQuery/backend DB or a web app) — not achievable with PBI Free + public REST API. In this batch architecture, PBI slicers filter **collected history**. The `inputs.station` parameter + dispatch endpoint is the seed for a future enhancement: a form/Power Automate visual that fires the pipeline for a chosen station; the report then shows that station's accumulated history.

---

## Portfolio narrative

**Abstract (repo header / CV):**

> Serverless ELT pipeline + Power BI analytics on public transit data. A Python bridge harvests departures into a self-trimming ("rolling") CSV on a reliably scheduled, zero-cost trigger chain (external cron → GitHub Actions); Power BI models it into an interactive reliability dashboard — on-time %, rush-hour degradation, line rankings — with no cloud warehouse and no license cost.

**Talking points:**

- **Problem:** transit APIs are ephemeral; historical analysis normally requires paid warehousing/streaming infrastructure.
- **Solution:** serverless ELT (external cron → Actions → rolling flat file) + Import-mode semantic model with contextual DAX.
- **Reliability engineering:** diagnosed a `KeyError: 0` incident to transient API rate-limiting on shared runner IPs; added retries/backoff and payload validation; identified free-tier cron throttling and replaced the scheduler with an external trigger — documented as an incident log.
- **Engineering judgment:** a real-time streaming variant (Power BI push datasets) was prototyped, evaluated and archived on purpose — tradeoffs in `_archive/`.
- **Analytics:** contextual measures (vs city average), conditional formatting, slicer-driven storytelling.

**CV one-liner:**

> Built and hardened an end-to-end, zero-cost analytics pipeline (Python · GitHub Actions · external cron · Power BI) turning a live transit API into a historical reliability dashboard.

## Swap-in Sources (Alternative APIs)

Change only the `FETCH`/shape block in `update_transit.py`:

- **Italy (Trenord):** ViaggiaTreno API (`partenze/{station_id}/{timestamp}`)
- **Planes over your city:** OpenSky Network API (`states/all?lamin=...`)
- **Local Weather:** Open-Meteo API (free, no key)
- **Air Quality:** Sensor.Community API

---

## Appendix — v1 real-time streaming prototype (superseded)

Historical record in [\_archive/live-transit-pbi.md](_archive/live-transit-pbi.md) and [\_archive/pipeline.yml](_archive/pipeline.yml); bridge code in [scripts/push_vbb.py](scripts/push_vbb.py).
**Why replaced:** streaming datasets only drive dashboard tiles (no Desktop modeling/DAX), data is ephemeral, and the loop needs an always-on machine — not serverless.
