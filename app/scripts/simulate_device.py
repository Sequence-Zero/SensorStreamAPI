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
import math
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from dotenv import load_dotenv
load_dotenv()

# Must match app/routes/ingest.py ALLOWED_SENSORS
SENSORS = ["hr_bpm", "pressure_kpa", "imu_gx", "imu_gy", "imu_gz", "emg_ch1", "emg_ch2"]


def sensor_value(sensor: str, t: float) -> float:
    if sensor.startswith("imu_g"):
        base = 30.0
        if sensor == "imu_gx":
            return base * math.sin(t * 1.1)
        if sensor == "imu_gy":
            return base * math.cos(t * 0.9)
        return base * math.sin(t * 0.7 + 1.2)
    if sensor.startswith("emg_"):
        noise = random.uniform(0.0, 0.12)
        spike = 0.0
        if random.random() < 0.08:
            spike = random.uniform(0.2, 0.6)
        return min(1.0, noise + spike)
    if sensor == "pressure_kpa":
        drift = 0.6 * math.sin(t * 0.05)
        noise = random.uniform(-0.15, 0.15)
        return 101.0 + drift + noise
    if sensor == "hr_bpm":
        wave = 15.0 * math.sin(t * 0.07) + 5.0 * math.sin(t * 0.23)
        noise = random.uniform(-1.5, 1.5)
        return 85.0 + wave + noise
    return random.uniform(0.0, 1.0)


def build_batch(session_id: str) -> dict:
    t = time.time()
    readings = []
    for s in SENSORS:
        readings.append({
            "sensor": s,
            "ts": datetime.now(timezone.utc).isoformat(),
            "value": sensor_value(s, t)
        })
    return {"session_id": session_id, "readings": readings}


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


def get_json(url: str, headers: dict | None = None) -> tuple[int, dict]:
    req = Request(url, method="GET")
    for k, v in (headers or {}).items():
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

    session_id = None

    if seed_mode:
        device_id, api_key = seed_device_locally()
        print("Seeded a local device in the DB:")
        print(f"  DEVICE_ID = {device_id}")
        print(f"  API_KEY   = {api_key}")
        print("You can reuse these by setting environment variables next run.")
        print("----")
    else:
        creds_url = os.getenv("DEMO_CREDENTIALS_URL", "http://127.0.0.1:5000/api/demo/credentials?rotate=0")
        status, resp = get_json(creds_url)
        if status == 0 or status >= 400:
            print(f"Failed to fetch demo credentials from {creds_url}: {resp}")
            raise SystemExit(2)

        device_id = (resp.get("device_id") or "").strip()
        api_key = (resp.get("api_key") or "").strip()
        session_id = (resp.get("session_id") or "").strip()
        if not device_id or not api_key or not session_id:
            print(f"Demo credentials response missing required fields: {resp}")
            raise SystemExit(2)

        print("Using /api/demo/credentials response.")
        print(f"  DEVICE_ID  = {device_id}")
        print(f"  API_KEY    = {api_key}")
        print(f"  SESSION_ID = {session_id}")
        print("----")

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
    print(f"session_id={session_id}")
    print(f"batch_size={batch_size}, interval_ms={interval_ms}, loops={loops}")
    print("----")

    for i in range(1, loops + 1):
        payload = build_batch(session_id=session_id)
        status, resp = post_json(ingest_url, payload, headers)
        print(f"ingest accepted={resp.get('accepted')} session={session_id}")

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
