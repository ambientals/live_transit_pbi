import os, sys, time, requests
from datetime import datetime, timezone
from pathlib import Path

# --- CONFIG ---
BASE = "https://v6.vbb.transport.rest"  # Change for Trenord etc.
STATION = sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1].strip() else "Alexanderplatz"
TIMEOUT = 15       # seconds per request
MAX_ATTEMPTS = 3   # retries per request
RETRY_DELAY = 2    # seconds between attempts

# Resolve paths relative to this script so it works regardless of the CWD.
BASE_DIR = Path(__file__).resolve().parent.parent  # project root
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CSV_FILE = DATA_DIR / "transit_history.csv"
FIELDS = ["Timestamp", "Line", "Direction", "DelaySec"]
SEP = ";"  # Semicolon separator: Direction values can contain commas.
MAX_ROWS = 15000  # Keeps the file around 1-2MB
HDRS = {"User-Agent": "pbi-transit-portfolio/1.0"}


def get_json(url, params=None):
    """GET with retries; returns parsed JSON or raises after MAX_ATTEMPTS."""
    last = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT, headers=HDRS)
            r.raise_for_status()
            return r.json()
        except requests.RequestException as e:
            last = e
            print(f"  attempt {attempt}/{MAX_ATTEMPTS} failed: {e}")
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY)
    raise last


# --- FETCH DATA ---
loc = get_json(f"{BASE}/locations", params={"query": STATION, "results": 1})
if not isinstance(loc, list) or not loc:
    raise SystemExit(f"No location found for '{STATION}' (unexpected response: {loc!r})")
station_id = loc[0].get("id")
station_name = loc[0].get("name", STATION)
print(f"Station: {station_name} | ID: {station_id}")

data = get_json(f"{BASE}/stops/{station_id}/departures", params={"duration": 10, "results": 15})
deps = data.get("departures", []) if isinstance(data, dict) else []
if not deps:
    print("No departures returned (late night / quiet station); nothing to append.")

now = datetime.now(timezone.utc).isoformat()
payload = [{
    "Timestamp": now,
    "Line": (d.get("line") or {}).get("name", "?"),
    "Direction": d.get("direction", "?"),
    "DelaySec": d.get("delay") or 0,
} for d in deps]

# --- ROLLING CSV LOGIC ---
lines = []
if os.path.exists(CSV_FILE):
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()

header = lines[0] if lines else SEP.join(FIELDS) + "\n"
data_lines = lines[1:] if lines else []

new_lines = [f"{row['Timestamp']}{SEP}{row['Line']}{SEP}{row['Direction']}{SEP}{row['DelaySec']}\n" for row in payload]
all_data = data_lines + new_lines
kept_data = all_data[-MAX_ROWS:]

with open(CSV_FILE, "w", encoding="utf-8") as f:
    f.write(header)
    f.writelines(kept_data)

print(f"Appended {len(payload)} rows. Total rows in CSV: {len(kept_data)}")
