"""Start a live NDTP replay after the Compose service becomes ready."""

import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_URL = os.getenv(
    "REPLAY_API_URL",
    f"http://localhost:{os.getenv('REPLAY_API_PORT', '18081')}",
).rstrip("/")
DATASET = os.getenv("REPLAY_DATASET", "validate")


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
    if valid:
        return [valid[0]]
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
                "time_mode": os.getenv("REPLAY_TIME_MODE", "shift_to_now"),
                "speed_multiplier": float(os.getenv("REPLAY_SPEED", "1")),
                "valid_locations_only": os.getenv("REPLAY_VALID_ONLY", "1") != "0",
            })
        except HTTPError as exc:
            if exc.code != 409:
                raise
        print(f"Started NDTP replay for {len(tr_ids)} vehicle(s) ({DATASET})")
    wait_for_connection()


if __name__ == "__main__":
    main()
