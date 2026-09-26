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


def choose_trip() -> int:
    configured = os.getenv("REPLAY_TR_ID")
    if configured:
        return int(configured)
    query = urlencode({"dataset": DATASET, "limit": 100})
    scenarios = api_request(f"/api/scenarios?{query}")
    for scenario in scenarios:
        if scenario["valid_packets"]:
            return scenario["tr_id"]
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
        tr_id = choose_trip()
        try:
            api_request("/api/replay/start", {
                "dataset": DATASET,
                "tr_ids": [tr_id],
                "time_mode": "shift_to_now",
                "valid_locations_only": True,
            })
        except HTTPError as exc:
            if exc.code != 409:
                raise
        print(f"Started NDTP replay for tr_id={tr_id} ({DATASET})")
    wait_for_connection()


if __name__ == "__main__":
    main()
