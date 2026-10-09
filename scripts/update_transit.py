import os, requests
from datetime import datetime, timezone
from pathlib import Path

# --- CONFIG ---
BASE = "https://v6.vbb.transport.rest" # Change for Trenord

# Resolve paths relative to this script so it works regardless of the CWD.
BASE_DIR = Path(__file__).resolve().parent.parent  # project root
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
CSV_FILE = DATA_DIR / "transit_history.csv"
FIELDS = ["Timestamp", "Line", "Direction", "DelaySec"]
SEP = ";"  # Semicolon separator: Direction values can contain commas.
MAX_ROWS = 15000 # Keeps the file around 1-2MB forever
HDRS = {"User-Agent": "pbi-transit-portfolio/1.0"}

# --- FETCH DATA ---
# (Using Berlin Alexanderplatz as example)
loc = requests.get(f"{BASE}/locations", params={"query": "Alexanderplatz", "results": 1}, timeout=10, headers=HDRS).json()
station_id = loc[0]["id"]

r_deps = requests.get(f"{BASE}/stops/{station_id}/departures", params={"duration": 10, "results": 15}, timeout=10, headers=HDRS)
data = r_deps.json()
deps = data.get("departures", []) if isinstance(data, dict) else data

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

# Format new rows
new_lines = [f"{row['Timestamp']}{SEP}{row['Line']}{SEP}{row['Direction']}{SEP}{row['DelaySec']}\n" for row in payload]
all_data = data_lines + new_lines

# Keep only the newest MAX_ROWS
kept_data = all_data[-MAX_ROWS:]

with open(CSV_FILE, "w", encoding="utf-8") as f:
    f.write(header)
    f.writelines(kept_data)

print(f"Appended {len(payload)} rows. Total rows in CSV: {len(kept_data)}")