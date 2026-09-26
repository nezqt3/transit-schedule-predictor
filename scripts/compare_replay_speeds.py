"""Compare one historical TCP replay point at 1x and accelerated send rates.

Start the stack with docker-compose.replay.yml before running this check.
The same source timestamps must produce the same runtime prediction.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
BACKEND = "http://127.0.0.1:8000"
REPLAY = "http://127.0.0.1:18081"
TR_ID = 130072
INTERVAL = {
    "dataset": "validate",
    "tr_ids": [TR_ID],
    "time_mode": "original",
    "valid_locations_only": True,
    "start_at": "2026-01-06T23:30:05",
    "end_at": "2026-01-06T23:30:20",
}
COMPARE = (
    "prediction_time", "input_event_time", "target_stop_id", "target_time",
    "current_delay_s", "current_delay_source", "predicted_delay_s", "p_late",
    "model_version", "model_artifact_sha256",
)


def restart_backend() -> None:
    subprocess.run([
        "docker", "compose", "-f", "docker-compose.yml",
        "-f", "docker-compose.replay.yml", "--profile", "replay",
        "restart", "backend",
    ], cwd=ROOT, check=True)


def one_run(client: httpx.Client, speed: float) -> dict:
    restart_backend()
    for _ in range(40):
        try:
            health = client.get(f"{BACKEND}/api/v1/health")
            if health.status_code == 200:
                break
        except httpx.RequestError:
            pass
        time.sleep(0.5)
    else:
        raise RuntimeError("backend failed to restart")
    login = client.post(f"{BACKEND}/api/v1/auth/token", data={
        "username": os.getenv("AUTH_BOOTSTRAP_USERNAME", "dispatcher"),
        "password": os.getenv("AUTH_BOOTSTRAP_PASSWORD", "transport"),
    })
    login.raise_for_status()
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    started = client.post(f"{REPLAY}/api/replay/start", json={
        **INTERVAL, "speed_multiplier": speed,
    })
    started.raise_for_status()
    for _ in range(100):
        status = client.get(f"{REPLAY}/api/status").json()
        if status["state"] == "completed":
            break
        if status["state"] == "failed":
            raise RuntimeError(status["error"])
        time.sleep(0.25)
    else:
        raise RuntimeError(f"replay {speed}x did not finish")
    response = client.get(
        f"{BACKEND}/api/v1/predictions/{TR_ID}/latest", headers=headers,
    )
    response.raise_for_status()
    return {"speed_multiplier": speed, "sent_packets": status["sent_packets"],
            "prediction": {key: response.json()[key] for key in COMPARE}}


def main() -> None:
    with httpx.Client(timeout=10, trust_env=False) as client:
        slow = one_run(client, 1)
        fast = one_run(client, 1800)
    report = {"tr_id": TR_ID, "interval": INTERVAL,
              "slow": slow, "fast": fast,
              "exact_match": slow["prediction"] == fast["prediction"]}
    path = ROOT / "data" / "processed" / "replay_speed_comparison.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["exact_match"] or slow["sent_packets"] != fast["sent_packets"]:
        raise SystemExit("replay speed changed the runtime prediction")


if __name__ == "__main__":
    main()
