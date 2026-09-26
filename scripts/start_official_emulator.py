"""Start the supplied NDTP emulator and verify packets reach Backend."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
IMAGE = "ndtp-telemetry-emulator:1.0"
CONTAINER = "ndtp-emu"


def docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args], check=check, capture_output=True, text=True, cwd=ROOT
    )


def ensure_image() -> None:
    if docker("image", "inspect", IMAGE, check=False).returncode == 0:
        return
    candidates = [ROOT / "ndtp-telemetry-emulator.tar", ROOT / "emulator" / "ndtp-telemetry-emulator.tar"]
    archive = next((path for path in candidates if path.is_file()), None)
    if archive is None:
        raise RuntimeError("NDTP image missing: place ndtp-telemetry-emulator.tar in the repo root or emulator/")
    result = docker("load", "-i", str(archive))
    print(result.stdout.strip())


def ensure_container(api_port: int) -> None:
    inspected = docker("inspect", CONTAINER, check=False)
    if inspected.returncode == 0:
        info = json.loads(inspected.stdout)[0]
        binding = info["HostConfig"]["PortBindings"].get("18080/tcp") or []
        if info["Config"]["Image"] != IMAGE or not any(
            item["HostPort"] == str(api_port) for item in binding
        ):
            raise RuntimeError(f"existing {CONTAINER} has a different image or API port; inspect it before restarting")
        if not info["State"]["Running"]:
            docker("start", CONTAINER)
        return
    result = docker(
        "run", "-d", "--rm", "-p", f"{api_port}:18080",
        "--add-host=host.docker.internal:host-gateway",
        "--name", CONTAINER, IMAGE,
    )
    print(f"Started {CONTAINER}: {result.stdout.strip()[:12]}")


def connect_to_compose_backend() -> str | None:
    """Attach the emulator to Backend's Compose network and return its DNS name."""
    backend = docker("compose", "ps", "-q", "backend", check=False).stdout.strip()
    if not backend:
        return None
    backend_info = json.loads(docker("inspect", backend).stdout)[0]
    networks = list(backend_info["NetworkSettings"]["Networks"])
    if not networks:
        return None
    network = networks[0]
    emulator_info = json.loads(docker("inspect", CONTAINER).stdout)[0]
    if network not in emulator_info["NetworkSettings"]["Networks"]:
        docker("network", "connect", network, CONTAINER)
    return "backend"


def read_json(url: str, token: str | None = None) -> object:
    request = Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    with urlopen(request, timeout=3) as response:
        return json.load(response)


def authenticate(backend_url: str, username: str, password: str) -> str:
    request = Request(
        f"{backend_url.rstrip('/')}/api/v1/auth/token",
        data=urlencode({"username": username, "password": password}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        payload = json.load(response)
    return payload["access_token"]


def wait_for_authentication(backend_url: str, username: str, password: str) -> str:
    """Wait until the freshly started Backend and its auth storage are ready."""
    last_error: Exception | None = None
    for _ in range(30):
        try:
            return authenticate(backend_url, username, password)
        except (OSError, URLError, KeyError, TypeError, ValueError) as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(
        f"Backend authentication did not become ready at {backend_url}: {last_error}"
    )


def wait_for_api(api_port: int) -> None:
    for _ in range(30):
        try:
            read_json(f"http://127.0.0.1:{api_port}/api/cells")
            return
        except (OSError, URLError):
            time.sleep(1)
    raise RuntimeError(f"NDTP emulator API did not become ready on port {api_port}")


def post_config(api_port: int, config: dict) -> None:
    request = Request(
        f"http://127.0.0.1:{api_port}/api/config",
        data=json.dumps(config).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=10) as response:
        response.read()


def wait_for_backend(
    unit_ids: set[int], backend_url: str, configured_at: datetime, token: str
) -> None:
    url = f"{backend_url.rstrip('/')}/api/v1/vehicles"
    seen: set[int] = set()
    last_error: Exception | None = None
    for _ in range(20):
        try:
            events = read_json(url, token)
            fresh = {
                event["unit_id"] for event in events
                if event["unit_id"] in unit_ids
                and datetime.fromisoformat(event["received_at"].replace("Z", "+00:00")) >= configured_at
            }
            seen.update(fresh)
            if fresh == unit_ids:
                print(f"Backend received fresh NDTP packets from {len(fresh)} unit(s): {sorted(fresh)}")
                return
        except (OSError, URLError, KeyError, TypeError, ValueError) as exc:
            last_error = exc
        time.sleep(1)
    missing = sorted(unit_ids - seen)
    detail = f"; last API error: {last_error}" if last_error else ""
    raise RuntimeError(
        f"Backend did not receive fresh NDTP packets from unit(s): {missing}{detail}"
    )


def wait_for_predictions(unit_ids: set[int], backend_url: str, token: str) -> None:
    url = f"{backend_url.rstrip('/')}/api/v1/predictions"
    for _ in range(30):
        predictions = read_json(url, token)
        ready = {item["unit_id"] for item in predictions if item["source"] == "demo"}
        if unit_ids <= ready:
            print(f"Synthetic demo forecasts ready for {sorted(unit_ids)}")
            return
        time.sleep(1)
    raise RuntimeError(
        "NDTP packets arrived, but synthetic demo predictions were not generated "
        f"for {sorted(unit_ids)}; inspect /api/v1/predictions/statuses"
    )


def wait_for_incidents(unit_ids: set[int], backend_url: str, token: str) -> None:
    url = f"{backend_url.rstrip('/')}/api/v1/incidents"
    for _ in range(30):
        incidents = read_json(url, token)
        ready = {item["unit_id"] for item in incidents if item["status"] == "active"}
        if unit_ids <= ready:
            print(f"Synthetic dispatcher incidents ready for {sorted(unit_ids)}")
            return
        time.sleep(1)
    raise RuntimeError(
        f"No active incidents for synthetic units {sorted(unit_ids)}; "
        "inspect /api/v1/predictions and /api/v1/incidents"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "emulator" / "official-demo-config.json")
    parser.add_argument("--api-port", type=int, default=int(os.getenv("EMU_API_PORT", "18080")))
    parser.add_argument("--target-host", default=os.getenv("TARGET_HOST"))
    parser.add_argument("--target-port", type=int, default=int(os.getenv("NDTP_TARGET_PORT", "9201")))
    parser.add_argument(
        "--backend-url",
        default=os.getenv(
            "BACKEND_URL", f"http://127.0.0.1:{os.getenv('FRONTEND_PORT', '8080')}"
        ),
    )
    parser.add_argument(
        "--backend-username",
        default=os.getenv("AUTH_BOOTSTRAP_USERNAME", "dispatcher"),
    )
    parser.add_argument(
        "--backend-password",
        default=os.getenv("AUTH_BOOTSTRAP_PASSWORD", "transport"),
    )
    args = parser.parse_args()

    config = json.loads(args.config.read_text(encoding="utf-8"))
    unit_ids = {unit["unitId"] for unit in config["units"]}
    if not unit_ids or len(unit_ids) != len(config["units"]):
        raise ValueError("config must contain unique, non-empty unit IDs")
    config["targetHost"] = args.target_host
    config["targetPort"] = args.target_port

    ensure_image()
    ensure_container(args.api_port)
    if args.target_host is None:
        args.target_host = connect_to_compose_backend() or "host.docker.internal"
        config["targetHost"] = args.target_host
    wait_for_api(args.api_port)
    token = wait_for_authentication(
        args.backend_url, args.backend_username, args.backend_password
    )
    configured_at = datetime.now(timezone.utc) - timedelta(seconds=2)
    post_config(args.api_port, config)
    print(f"Official NDTP emulator configured for {len(unit_ids)} unit(s) at {args.target_host}:{args.target_port}")
    wait_for_backend(unit_ids, args.backend_url, configured_at, token)
    wait_for_predictions(unit_ids, args.backend_url, token)
    wait_for_incidents(unit_ids, args.backend_url, token)


if __name__ == "__main__":
    main()
