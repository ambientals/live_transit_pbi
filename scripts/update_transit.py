import csv, os, sys, time, requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NoReturn

# --- CONFIG ---
BASE = "https://v6.vbb.transport.rest"  # Change for Trenord etc.
STATION = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].strip() else "Alexanderplatz"
TIMEOUT = 15       # seconds per request
MAX_ATTEMPTS = 3   # retries per request
RETRY_DELAY = 2    # seconds between attempts

# Resolve paths relative to this script so it works regardless of the CWD.
BASE_DIR = Path(__file__).resolve().parent.parent  # project root
DATA_DIR = BASE_DIR / "data"
LOGS_DIR = BASE_DIR / "logs"
DATA_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
CSV_FILE = DATA_DIR / "transit_history.csv"   # payload: pure transit data
RUNS_FILE = LOGS_DIR / "runs.csv"             # receipt: one line per execution
FIELDS = ["Timestamp", "Line", "Direction", "DelaySec"]
RUN_FIELDS = ["Timestamp", "GitHubRunId", "Station", "Status", "Rows", "Note"]
SEP = ";"  # Semicolon separator: Direction values can contain commas.
MAX_ROWS = 15000  # Keeps the file around 1-2MB
HDRS = {"User-Agent": "pbi-transit-portfolio/1.0"}

# GitHub Actions injects these; empty when run locally.
GITHUB_RUN_ID = os.environ.get("GITHUB_RUN_ID", "")
STEP_SUMMARY = os.environ.get("GITHUB_STEP_SUMMARY", "")


def log_run(status, rows, note=""):
    """Append one receipt line to logs/runs.csv — called on every run (ok/skip).

    Idempotent and independent of the file's prior state: it writes the header
    if the file is missing or empty, and closes off a dangling last line (e.g. a
    committed header with no trailing newline) before appending the new row.
    """
    ts = datetime.now(timezone.utc).isoformat()
    row = [ts, GITHUB_RUN_ID, STATION, status, str(rows), note]
    size = 0
    needs_newline = False
    if RUNS_FILE.exists():
        with open(RUNS_FILE, "rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size > 0:
                f.seek(size - 1)
                needs_newline = f.read(1) != b"\n"

    with open(RUNS_FILE, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=SEP, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
        if size == 0:              # missing or empty -> write the header first
            w.writerow(RUN_FIELDS)
        elif needs_newline:        # dangling last line -> terminate it first
            f.write("\n")
        w.writerow(row)


def emit_summary(status, detail):
    """Render a short markdown block on the Actions run-summary page (no-op locally)."""
    if not STEP_SUMMARY:
        return
    with open(STEP_SUMMARY, "a", encoding="utf-8") as f:
        f.write("### Transit update\n")
        f.write(f"- **Status:** {status}\n")
        f.write(f"- **Station:** {STATION}\n")
        f.write(f"- **{detail}**\n\n")


def skip(reason: str, status: str = "skip") -> NoReturn:
    """End the run green, but leave a visible + persistent trace that no data arrived."""
    print(f"SKIP: {reason}")
    if status == "skip":
        print(f"::warning::{reason}")
    else:
        print(f"::notice::{reason}")
    log_run(status, 0, reason)
    emit_summary(status, reason)
    raise SystemExit(0)


def get_json(url: str, params: dict | None = None) -> Any:
    """GET with retries; returns parsed JSON or raises after MAX_ATTEMPTS."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT, headers=HDRS)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            print(f"  attempt {attempt}/{MAX_ATTEMPTS} failed: {e}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY)
            else:
                raise          # ← re-raise the current exception on the final try

# --- FETCH DATA (graceful on upstream downtime) ---
try:
    loc = get_json(f"{BASE}/locations", params={"query": STATION, "results": 1})
except requests.RequestException as e:
    skip(f"locations lookup failed ({e})")

if not isinstance(loc, list) or not loc:
    skip(f"locations lookup failed or empty for '{STATION}' (upstream down?)")

station_id = loc[0].get("id")
station_name = loc[0].get("name", STATION)
print(f"Station: {station_name} | ID: {station_id}")

try:
    data = get_json(f"{BASE}/stops/{station_id}/departures", params={"duration": 10, "results": 15})
except requests.RequestException as e:
    skip(f"departures lookup failed ({e})")

deps = data.get("departures", []) if isinstance(data, dict) else []
if not deps:
    skip("no departures returned (late night / quiet station)", status="empty")

now = datetime.now(timezone.utc).isoformat()
payload = [{
    "Timestamp": now,
    "Line": (d.get("line") or {}).get("name", "?"),
    "Direction": d.get("direction", "?"),
    "DelaySec": d.get("delay") or 0,
} for d in deps]

# --- ROLLING CSV LOGIC (idempotent: independent of the file's prior state) ---
header = None
data_rows = []
if CSV_FILE.exists():
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        for row in csv.reader(f, delimiter=SEP):
            if not row or all(cell == "" for cell in row):
                continue
            if header is None:
                header = row
            else:
                data_rows.append(row)

if header is None:
    header = FIELDS

new_rows = [[row["Timestamp"], row["Line"], row["Direction"], str(row["DelaySec"])] for row in payload]
kept_data = (data_rows + new_rows)[-MAX_ROWS:]

with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f, delimiter=SEP, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")
    w.writerow(header)
    w.writerows(kept_data)

print(f"Appended {len(payload)} rows. Total rows in CSV: {len(kept_data)}")
log_run("ok", len(payload), "")
emit_summary("ok", f"Appended {len(payload)} rows (total {len(kept_data)})")
