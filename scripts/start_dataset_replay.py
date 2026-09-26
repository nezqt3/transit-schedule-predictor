"""Start a live NDTP replay after the Compose service becomes ready."""

import json
import os
import time
import csv
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = os.getenv(
    "REPLAY_API_URL",
    f"http://localhost:{os.getenv('REPLAY_API_PORT', '18081')}",
).rstrip("/")
DATASET = os.getenv("REPLAY_DATASET", "validate")
TIME_MODE = os.getenv("REPLAY_TIME_MODE", "original")
ROOT = Path(__file__).resolve().parents[1]


def api_request(path: str, payload: dict | None = None) -> dict | list:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        API_URL + path,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
    )
    with urlopen(request, timeout=5) as response:
        return json.load(response)


def wait_for_api() -> None:
    for _ in range(30):
        try:
            api_request("/health")
            return
        except (OSError, URLError):
            time.sleep(1)
    raise RuntimeError(f"replay API did not become ready at {API_URL}")


def choose_trips() -> list[int]:
    configured_many = os.getenv("REPLAY_TR_IDS")
    if configured_many:
        return [int(value.strip()) for value in configured_many.split(",") if value.strip()]
    configured = os.getenv("REPLAY_TR_ID")
    if configured:
        return [int(configured)]
    query = urlencode({"dataset": DATASET, "limit": 100})
    scenarios = api_request(f"/api/scenarios?{query}")
    if os.getenv("REPLAY_ALL") == "1" and scenarios:
        return [scenario["tr_id"] for scenario in scenarios]
    valid = [scenario["tr_id"] for scenario in scenarios if scenario["valid_packets"]]
    if os.getenv("REPLAY_ALL_VALID") == "1" and valid:
        return valid
    schedule_name = "schedule_plan.csv" if DATASET == "validate" else "schedule.csv"
    schedule_path = ROOT / "data" / "raw" / DATASET / schedule_name
    if schedule_path.is_file():
        with schedule_path.open(encoding="utf-8", newline="") as handle:
            scheduled = {int(row["tr_id"]) for row in csv.DictReader(handle)}
        valid = [tr_id for tr_id in valid if tr_id in scheduled]
    if valid:
        return valid[:2]
    raise RuntimeError(f"no valid NDTP packets in dataset {DATASET!r}")


def wait_for_connection() -> None:
    for _ in range(20):
        status = api_request("/api/status")
        if any(unit["connected"] and unit["sent_packets"] for unit in status["units"]):
            print(
                f"NDTP connected to backend: {status['sent_packets']} packet(s) sent; "
                f"status: {API_URL}/api/status"
            )
            return
        if status["state"] == "failed":
            raise RuntimeError(f"NDTP replay failed: {status['error']}")
        time.sleep(0.5)
    raise RuntimeError(f"NDTP did not connect; inspect {API_URL}/api/status")


def main() -> None:
    if TIME_MODE != "original":
        raise RuntimeError(
            "forecast replay requires REPLAY_TIME_MODE=original so NDTP timestamps "
            "and the mounted stop plan share one logical clock"
        )
    wait_for_api()
    status = api_request("/api/status")
    if status["state"] == "paused":
        api_request("/api/replay/resume", {})
    elif status["state"] != "running":
        tr_ids = choose_trips()
        try:
            api_request("/api/replay/start", {
                "dataset": DATASET,
                "tr_ids": tr_ids,
                "time_mode": TIME_MODE,
                "speed_multiplier": float(os.getenv("REPLAY_SPEED", "1800")),
                "valid_locations_only": os.getenv("REPLAY_VALID_ONLY", "1") != "0",
            })
        except HTTPError as exc:
            if exc.code != 409:
                raise
        print(f"Started NDTP replay for {len(tr_ids)} vehicle(s) ({DATASET})")
    wait_for_connection()


if __name__ == "__main__":
    main()
