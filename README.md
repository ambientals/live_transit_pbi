# Transit Analytics Power BI Dashboard

Date: 20261010

**Goal:**
Build an interactive Power BI report using real-world public transit data (BVG/VBB in Berlin or Trenord in Italy).
The focus is on data modeling and dataviz, powered by a lightweight and free automated pipeline.

## Architecture

Due to Power BI's paywalls on real-time architecture, the approach taken is a "near-real-time" analytics dashboard.

A "rolling CSV" pattern is used to keep GitHub storage light, while giving Power BI a robust and flexible dataset.

```text
Public API (VBB, Trenord, etc)
        │  [fetch]
        ▼
Python Bridge (GitHub Actions cron)
        │  [write/trim CSV]
        ▼
GitHub Repo (Rolling History)
        │  [exposes CSV]
        ▼
Power BI Desktop / Service
```

An earlier _real-time streaming_ prototype (live push into a Power BI streaming dataset) is documented in the Appendix at the end of this file.

---

## Prerequisites

- Power BI Desktop & Power BI Service account
- Python 3 (for pipeline local testing)
- GitHub account (Public repo = free unlimited GitHub Actions minutes)

---

## Phase 1 — The Python Bridge (Rolling CSV)

The [**update_transit.py**](scripts/update_transit.py) script fetches the latest departures and appends them to a GitHub CSV.
It trims the oldest data so the repo never hits file-size limits or bloats Git history.

---

## Phase 2 — GitHub Actions Automation

GitHub runs the script every 15 minutes and commits the updated CSV to the repository.

1. Create a public GitHub repo and upload `scripts/update_transit.py`.
2. Create the folder `.github/workflows/` and add [**main.yml**](.github/workflows/main.yml):

---

## Phase 3 — Power BI Desktop project

1. Open Power BI Desktop -> **Get Data -> Web**.
2. Paste the raw GitHub URL of your CSV:
   `https://raw.githubusercontent.com/<your-username>/<your-repo>/main/data/transit_history.csv`
3. **Transform Data (Power Query):**
   - Change `Timestamp` to Date/Time type.
   - Change `DelaySec` to Whole Number.
   - _Pro-tip:_ Add a custom column for `DelayMinutes = [DelaySec] / 60`.
   - Add a `Time of Day` or `Hour` column for time-series analysis.
4. **Build your Visuals:**
   - **KPI Cards:** Total departures tracked, Average Delay, Worst Delay.
   - **Line Chart:** Average delay by Hour of Day (shows rush hour pain).
   - **Bar Chart:** Top 5 most delayed Lines.
   - **Slicers:** Date picker, Line selector, Direction.
5. Demonstrate basic **DAX** skills:
   ```dax
   OnTime % =
   CALCULATE(
       COUNTROWS(transit_history),
       transit_history[DelaySec] <= 0
   ) / COUNTROWS(transit_history)
   ```

---

## Phase 4 — Publish & Schedule

1. Click **Publish** in Power BI Desktop to send it to your Free Service Workspace.
2. Go to app.powerbi.com, find your dataset settings.
3. Under **Scheduled Refresh**, turn it ON.
   - _Free tier limit:_ You can schedule up to 8 refreshes a day (e.g., every 3 hours).
   - _Note:_ The GitHub CSV updates every 15 mins, but PBI Free will only pull it 8 times a day. This is the accepted tradeoff for keeping the project 100% free and flexible!

---

## Portfolio Presentation Tips

When you add this to your portfolio/GitHub Readme, frame it like a Data Engineer / BI Developer:

- **The Problem:** Public transit APIs are ephemeral and difficult to analyze historically without enterprise data warehousing.
- **The Solution:** Built a lightweight, serverless ELT pipeline using GitHub Actions to capture and roll transit data into a cloud-hosted flat file.
- **The Value:** Enabled historical trend analysis (rush hour delays, line reliability) using Power BI DAX, completely bypassing enterprise cloud-warehouse costs.

---

## Swap-in Sources (Alternative APIs)

To track something else, just change the `FETCH` block in `update_transit.py`:

- **Italy (Trenord):** Use the ViaggiaTreno API (`partenze/{station_id}/{timestamp}`).
- **Planes over your city:** OpenSky Network API (`states/all?lamin=...`).
- **Local Weather:** Open-Meteo API (Free, no key required).
- **Air Quality:** Sensor.Community API.

---

## Appendix — Historical: v1 real-time streaming prototype (`push_vbb.py`)

> **Status:** superseded by the rolling-CSV pipeline above. Kept here as a historical record of the first architecture attempt.

### What it did

Before the rolling-CSV pipeline, the first prototype pushed live departures **directly into a Power BI "streaming dataset"**, where dashboard tiles could display them in near-real-time — no CSV file, no GitHub Actions, no history.

### Terminology

- **URL** — the full address string (e.g. `https://api.powerbi.com/beta/.../rows?...`).
- **Endpoint** — one specific operation's address _within_ an API. Each `.env` value (`ENDPOINT_01`, `ENDPOINT_02`) is a _different endpoint_: they differ in `datasetId` (path) and `key`, so each targets a different streaming dataset.
- **API** — the whole service. The "Power BI REST API" is the collection of _all_ its endpoints; the "push rows" endpoint is one of them. VBB is a separate API (`/locations`, `/stops/{id}/departures`).

### How the data flows

Your PC is not talking "directly to" a dashboard. There are **three separate hops**, and everything lives in Microsoft's cloud except the script itself.

```text
[your PC]                         [Microsoft cloud — Power BI service]
   │                                        │
   │ 1. GET  (read)                         │
   ├──────────► VBB API (Berlin transit)    │
   │  ◄────────── departures JSON           │
   │                                        │
   │ 2. POST (write)  ─────────────────────►│  streaming dataset
   │    rows → api.powerbi.com/.../rows     │     │
   │    (authenticated by `key=`)           │     │ (rolling buffer)
   │                                        │     ▼
   │                                        │  dashboard tiles (read it live)
```

1. **Your script READS from VBB.** `requests.get(...)` pulls the latest departures _into_ your Python process — a normal "pull": data comes **from** VBB **to** your PC.

2. **Your script WRITES to Power BI.** `requests.post(PBI_PUSH_URL, json=payload)` sends an HTTPS request **up to Microsoft's cloud** — the same mechanics as submitting a form to a website. The `key=` in the URL is the credential that authorizes the write; the `datasetId` tells Power BI _which_ dataset to append the rows to.

3. **The streaming dataset stores it.** A **streaming dataset** (aka "push dataset") is a passive Power BI object whose whole job is to _receive_ rows pushed at it via its push URL and hold them in a **rolling buffer** (most recent N rows). It doesn't query any data source itself — it just waits for your POSTs.

4. **The dashboard displays it.** A **dashboard** is a set of **tiles**. Some tiles are pinned _from_ a streaming dataset; those tiles continuously read the dataset's buffer and refresh in near-real-time — that's why the dashboard updates with no manual refresh.

### Pipeline (what does what)

1. **Load config** — reads `.env` and picks the target push endpoint.
2. **Resolve station** — calls the VBB API to turn "Alexanderplatz" into a station ID.
3. **Infinite loop** (every 60 s):
   - fetch the next departures from VBB;
   - map each departure to `Timestamp / Line / Direction / DelaySec`;
   - `POST` the rows to the Power BI push endpoint;
   - sleep 60 s and repeat.

### Endpoint selection

The script pushes to **one** endpoint, chosen as:

> `ENDPOINT_01` if set, otherwise `ENDPOINT_02`.

With both variables present in `.env`, data goes to `ENDPOINT_01` (`transit_streaming`) only. To target `transit_streaming_02`, swap the two variables in `push_vbb.py`, or keep only `ENDPOINT_02` in `.env`.

### Running it

```bash
python scripts/push_vbb.py
```

It runs until interrupted — press **Ctrl+C** to stop.

### Why it was replaced

- Streaming datasets only drive **dashboard tiles**; they don't support the full Power BI Desktop modeling/DAX experience.
- Data is ephemeral (no durable history without extra setup).
- It needs a machine keeping the loop alive — not serverless like GitHub Actions.
- Hence the rolling-CSV approach (`update_transit.py` + `main.yml`) that this README documents as the current pipeline.
