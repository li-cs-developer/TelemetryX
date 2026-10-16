"""
Simulate a delivery van pinging telemetry every 3 seconds.

Usage:
    python scripts/simulate_van.py [VIN] [PORT] [API_KEY]
Example:
    python scripts/simulate_van.py 1HGCR2F83HA000000 8001 abc123...
"""
import os
import random
import sys
import time
from datetime import datetime, timezone

import requests

VIN = sys.argv[1] if len(sys.argv) > 1 else "1HGCR2F83HA000000"
PORT = sys.argv[2] if len(sys.argv) > 2 else "8001"
API_KEY = sys.argv[3] if len(sys.argv) > 3 else os.getenv("VAN_API_KEY", "")

URL = f"http://localhost:{PORT}/api/v1/telemetry/"

lat, lng = 37.7749, -122.4194


def main():
    global lat, lng
    if not API_KEY:
        print("ERROR: no API key. Pass as arg 3 or set VAN_API_KEY.")
        print("       Generate with: python manage.py generate_vehicle_keys")
        sys.exit(1)

    headers = {"X-Api-Key": API_KEY}
    print(f"Streaming telemetry for {VIN} → {URL}")

    while True:
        lat += random.uniform(-0.001, 0.001)
        lng += random.uniform(-0.001, 0.001)
        payload = {
            "vin": VIN,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "lat": lat,
            "lng": lng,
            "speed": random.uniform(20, 90),
            "engine_temp": random.uniform(85, 100),
            "fuel_pct": random.uniform(20, 90),
        }
        try:
            r = requests.post(URL, json=payload, headers=headers, timeout=5)
            if r.status_code >= 400:
                print(f"{r.status_code}  REJECTED  body={r.text}")
            else:
                print(f"{r.status_code}  speed={payload['speed']:.1f}")
        except requests.RequestException as exc:
            print(f"error: {exc}")
        time.sleep(3)


if __name__ == "__main__":
    main()