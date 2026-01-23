#!/usr/bin/env python3
"""
Simulate a device sending batched sensor readings to SensorStream-API.

Two modes:

A) Normal: Use existing credentials (DEVICE_ID + API_KEY)
   PowerShell:
     $env:BASE_URL="http://127.0.0.1:5000"
     $env:DEVICE_ID="your-device-uuid"
     $env:API_KEY="your-device-api-key"
     python .\scripts\simulate_device.py

B) Seed + send: Create a device row locally (no API needed), then ingest
   IMPORTANT: This requires the Flask app package to be importable (run from repo root).
   PowerShell:
     $env:SEED_DEVICE="1"
     $env:DEVICE_NAME="SimDevice-001"
     python .\scripts\simulate_device.py

Optional tuning:
  $env:BATCH_SIZE="25"
  $env:INTERVAL_MS="250"
  $env:LOOPS="20"
"""

import os
import time
import json
import uuid
import secrets
import random
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# Must match app/routes/ingest.py ALLOWED_SENSORS
SENSORS = [
    "imu_ax", "imu_ay", "imu_az",
    "imu_gx", "imu_gy", "imu_gz",
    "emg_ch1", "emg_ch2", "emg_ch3", "emg_ch4",
    "pressure_kpa", "hr_bpm"
]


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sensor_value(sensor: str) -> float:
    if sensor.startswith("imu_a"):
        return random.uniform(-2.0, 2.0)
    if sensor.startswith("imu_g"):
        return random.uniform(-250.0, 250.0)
    if sensor.startswith("emg_"):
        return random.uniform(0.0, 1.0)
    if sensor == "pressure_kpa":
        return random.uniform(90.0, 110.0)
    if sensor == "hr_bpm":
        return random.uniform(55.0, 165.0)
    return random.uniform(0.0, 1.0)


def build_batch(batch_size: int) -> dict:
    readings = []
    for _ in range(batch_size):
        s = random.choice(SENSORS)
        readings.append({
            "sensor": s,
            "ts": iso_utc_now(),
            "value": sensor_value(s)
        })
    return {"readings": readings}


def post_json(url: str, payload: dict, headers: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in headers.items():
        req.add_header(k, v)

    try:
        with urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8") if resp else ""
            return resp.status, json.loads(body) if body else {}
    except HTTPError as e:
        body = e.read().decode("utf-8") if e.fp else ""
        try:
            return e.code, json.loads(body) if body else {"error": "http_error"}
        except Exception:
            return e.code, {"error": "http_error", "raw": body}
    except URLError as e:
        return 0, {"error": "url_error", "detail": str(e)}


def seed_device_locally() -> tuple[str, str]:
    """
    Creates a Device row directly in your DB using the app context.
    Returns (device_id, api_key_plaintext).

    This avoids needing /api/devices while you’re still wiring things.
    """
    # Import inside function so normal mode doesn't require Flask app imports.
    from app import create_app
    from app.extensions import db
    from app.models import Device

    app = create_app()
    device_id = str(uuid.uuid4())
    api_key = secrets.token_urlsafe(32)
    name = os.getenv("DEVICE_NAME", "SimDevice-Local")

    with app.app_context():
        d = Device(id=device_id, name=name, api_key_hash="")
        d.set_api_key(api_key)
        db.session.add(d)
        db.session.commit()

    return device_id, api_key


def main():
    base_url = os.getenv("BASE_URL", "http://127.0.0.1:5000").rstrip("/")

    seed_mode = os.getenv("SEED_DEVICE", "").strip() in ("1", "true", "TRUE", "yes", "YES")

    if seed_mode:
        device_id, api_key = seed_device_locally()
        print("Seeded a local device in the DB:")
        print(f"  DEVICE_ID = {device_id}")
        print(f"  API_KEY   = {api_key}")
        print("You can reuse these by setting environment variables next run.")
        print("----")
    else:
        device_id = os.getenv("DEVICE_ID", "").strip()
        api_key = os.getenv("API_KEY", "").strip()

        # Demo-mode fallback (for hosted one-click demos or quick local runs)
        demo_mode = os.getenv("DEMO_MODE", "").strip() in ("1", "true", "TRUE", "yes", "YES")
        if (not device_id or not api_key) and demo_mode:
            demo_device_id = os.getenv("DEMO_DEVICE_ID", "").strip()
            demo_api_key = os.getenv("DEMO_API_KEY", "").strip()
            if demo_device_id and demo_api_key:
                device_id, api_key = demo_device_id, demo_api_key
                print("Using DEMO_DEVICE_ID/DEMO_API_KEY credentials (DEMO_MODE=1).")
                print(f"  DEVICE_ID = {device_id}")
                print(f"  API_KEY   = {api_key}")
                print("----")

        if not device_id or not api_key:
            print("Missing DEVICE_ID and/or API_KEY environment variables.")
            print("Either set them, or set SEED_DEVICE=1 to auto-create a device locally,")
            print("or set DEMO_MODE=1 with DEMO_DEVICE_ID and DEMO_API_KEY.")
            raise SystemExit(2)

    batch_size = int(os.getenv("BATCH_SIZE", "25"))
    interval_ms = int(os.getenv("INTERVAL_MS", "250"))
    loops = int(os.getenv("LOOPS", "20"))

    ingest_url = f"{base_url}/api/ingest"

    # These match your app/auth.py exactly:
    headers = {
        "X-Device-Id": device_id,
        "X-API-Key": api_key
    }

    print(f"POST {ingest_url}")
    print(f"device_id={device_id}")
    print(f"batch_size={batch_size}, interval_ms={interval_ms}, loops={loops}")
    print("----")

    for i in range(1, loops + 1):
        payload = build_batch(batch_size)
        status, resp = post_json(ingest_url, payload, headers)

        if status == 0:
            print(f"[{i}/{loops}] NETWORK ERROR: {resp}")
            break

        if status >= 400:
            print(f"[{i}/{loops}] HTTP {status}: {resp}")
            if status in (401, 403):
                break
        else:
            print(f"[{i}/{loops}] HTTP {status}: accepted={resp.get('accepted')} rejected={resp.get('rejected')}")

        time.sleep(interval_ms / 1000.0)

    print("Done.")


if __name__ == "__main__":
    main()
