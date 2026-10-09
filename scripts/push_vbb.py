# v1 real-time streaming prototype (superseded by the rolling-CSV pipeline).
# See the README Appendix for the full description.

import os, time, requests
from datetime import datetime, timezone
from pathlib import Path

# Load .env from the project root (dependency-free: no python-dotenv required).
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())

# Endpoint selection: `or` returns ENDPOINT_01 whenever it is set, and only falls
# back to ENDPOINT_02 if ENDPOINT_01 is missing or empty.
# -> With both variables present in .env, data is pushed to ENDPOINT_01 ONLY.
# To target ENDPOINT_02 instead, swap the two variables here (or keep only
# ENDPOINT_02 in .env).
PBI_PUSH_URL = os.getenv("ENDPOINT_01") or os.getenv("ENDPOINT_02")
if not PBI_PUSH_URL:
    raise SystemExit("No PBI endpoint configured. Set ENDPOINT_01 or ENDPOINT_02 in .env")

BASE = "https://v6.vbb.transport.rest"
HDRS = {"User-Agent": "pbi-transit-bridge/0.1 (hobby project)"} # Polite header

# 1. Get station ID (from your working code)
r_loc = requests.get(BASE + "/locations",
                     params={"query": "Alexanderplatz", "results": 1}, 
                     timeout=10, headers=HDRS).json()
station_id = r_loc[0]["id"]
print("Station:", r_loc[0]["name"], "| ID:", station_id)

while True:
    # 2. Fetch departures for the station
    r_deps = requests.get(f"{BASE}/stops/{station_id}/departures",
                          params={"duration": 5, "results": 5}, 
                          timeout=10, headers=HDRS)
    
    # 3. Extract the departures list from the JSON response
    data = r_deps.json()
    deps = data.get("departures", []) if isinstance(data, dict) else data

    now = datetime.now(timezone.utc).isoformat()
    
    payload = [{
        "Timestamp": now,
        "Line":      (d.get("line") or {}).get("name", "?"),
        "Direction": d.get("direction", "?"),
        "DelaySec":  d.get("delay") or 0,
    } for d in deps]

    print(f"\n--- Pushing {len(payload)} departures ---")
    for train in payload:
        print(f"  {train['Line']} -> {train['Direction']} (Delay: {train['DelaySec']}s)")
    
    status = requests.post(PBI_PUSH_URL, json=payload, timeout=10).status_code
    print("Status:", status) # Want 200

    time.sleep(60)