import math
import random
import threading
import time
from datetime import datetime, timezone
from typing import Any

from .extensions import db
from .models import Reading

ALLOWED_SENSORS = [
    "imu_ax",
    "imu_ay",
    "imu_az",
    "imu_gx",
    "imu_gy",
    "imu_gz",
    "emg_ch1",
    "emg_ch2",
    "emg_ch3",
    "emg_ch4",
    "pressure_kpa",
    "hr_bpm",
]

MAX_RUNTIME_SECONDS = 10 * 60
MAX_INSERTED = 500
MIN_INTERVAL_MS = 500
MAX_INTERVAL_MS = 5000
DEFAULT_INTERVAL_MS = 1000

DEMO_STREAMS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def clamp_interval_ms(raw: Any) -> int:
    try:
        n = int(raw)
    except Exception:
        n = DEFAULT_INTERVAL_MS
    return max(MIN_INTERVAL_MS, min(n, MAX_INTERVAL_MS))


def sensor_value(sensor: str, t: float) -> float:
    if sensor.startswith("imu_g"):
        base = 30.0
        if sensor == "imu_gx":
            return base * math.sin(t * 1.1)
        if sensor == "imu_gy":
            return base * math.cos(t * 0.9)
        return base * math.sin(t * 0.7 + 1.2)
    if sensor.startswith("imu_a"):
        base = 2.5
        if sensor == "imu_ax":
            return base * math.sin(t * 1.2)
        if sensor == "imu_ay":
            return base * math.cos(t * 0.8)
        return base * math.sin(t * 0.6 + 0.9)
    if sensor.startswith("emg_"):
        noise = random.uniform(0.0, 0.12)
        spike = random.uniform(0.2, 0.6) if random.random() < 0.08 else 0.0
        return min(1.0, noise + spike)
    if sensor == "pressure_kpa":
        return 101.0 + (0.6 * math.sin(t * 0.05)) + random.uniform(-0.15, 0.15)
    if sensor == "hr_bpm":
        wave = 15.0 * math.sin(t * 0.07) + 5.0 * math.sin(t * 0.23)
        return 85.0 + wave + random.uniform(-1.5, 1.5)
    return random.uniform(0.0, 1.0)


def _cleanup_stream(device_id: str, current_thread: threading.Thread) -> None:
    with _LOCK:
        state = DEMO_STREAMS.get(device_id)
        if state and state.get("thread") is current_thread:
            DEMO_STREAMS.pop(device_id, None)


def _run_stream(app, device_id: str, session_id: str, interval_ms: int, sensor: str | None, stop_event: threading.Event) -> None:
    inserted = 0
    loops = 0
    started_at = datetime.now(timezone.utc)
    sensors = [sensor] if sensor else ALLOWED_SENSORS
    reason = "stopped"

    with app.app_context():
        try:
            while not stop_event.is_set():
                elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
                if elapsed >= MAX_RUNTIME_SECONDS:
                    reason = "max_runtime"
                    break
                if inserted >= MAX_INSERTED:
                    reason = "max_inserted"
                    break

                now = datetime.now(timezone.utc)
                t = time.time()
                loop_inserted = 0
                for s in sensors:
                    if inserted >= MAX_INSERTED:
                        reason = "max_inserted"
                        break
                    db.session.add(
                        Reading(
                            device_id=device_id,
                            sensor=s,
                            ts=now,
                            value=sensor_value(s, t),
                            session_id=session_id,
                        )
                    )
                    inserted += 1
                    loop_inserted += 1

                if loop_inserted > 0:
                    db.session.commit()

                loops += 1
                with _LOCK:
                    state = DEMO_STREAMS.get(device_id)
                    if state and state.get("thread") is threading.current_thread():
                        state["inserted"] = inserted

                if loops % 10 == 0:
                    print(f"[demo-stream] device={device_id} session={session_id} inserted={inserted}")

                if stop_event.wait(interval_ms / 1000.0):
                    reason = "stopped"
                    break
        finally:
            db.session.remove()
            _cleanup_stream(device_id, threading.current_thread())
            print(f"[demo-stream] stop device={device_id} session={session_id} reason={reason} inserted={inserted}")


def start_stream(app, device_id: str, session_id: str, interval_ms: int, sensor: str | None = None) -> dict[str, Any]:
    interval_ms = clamp_interval_ms(interval_ms)

    with _LOCK:
        existing = DEMO_STREAMS.get(device_id)
        if existing and existing["thread"].is_alive():
            return existing

        stop_event = threading.Event()
        thread = threading.Thread(
            target=_run_stream,
            args=(app, device_id, session_id, interval_ms, sensor, stop_event),
            daemon=True,
            name=f"demo-stream-{device_id}",
        )
        state = {
            "thread": thread,
            "stop_event": stop_event,
            "session_id": session_id,
            "started_at": datetime.now(timezone.utc),
            "inserted": 0,
            "interval_ms": interval_ms,
            "sensor": sensor,
        }
        DEMO_STREAMS[device_id] = state
        thread.start()

    print(f"[demo-stream] start device={device_id} session={session_id} interval_ms={interval_ms}")
    return state


def stop_stream(device_id: str) -> bool:
    with _LOCK:
        state = DEMO_STREAMS.get(device_id)
        if not state:
            return False
        state["stop_event"].set()
        thread = state["thread"]

    thread.join(timeout=2.0)
    _cleanup_stream(device_id, thread)
    print(f"[demo-stream] stop requested device={device_id}")
    return True
