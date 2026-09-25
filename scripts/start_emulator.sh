#!/usr/bin/env bash
# Запуск эмулятора NDTP: docker load образа + контейнер + загрузка конфига.
#
# Использование:
#   ./scripts/start_emulator.sh                 # конфиг из emulator/config.json
#   TARGET_HOST=backend ./scripts/start_emulator.sh   # если backend в той же Docker-сети
#
# Остановить: docker rm -f ndtp-emu

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EMULATOR_DIR="$SCRIPT_DIR/../emulator"
IMAGE="ndtp-telemetry-emulator:1.0"
TAR="$EMULATOR_DIR/ndtp-telemetry-emulator.tar"
CONTAINER="ndtp-emu"
API_PORT="${EMU_API_PORT:-18080}"
TARGET_HOST="${TARGET_HOST:-host.docker.internal}"
TARGET_PORT="${NDTP_TARGET_PORT:-9201}"
CONFIG_FILE="${CONFIG_FILE:-$EMULATOR_DIR/config.json}"

if [ ! -f "$TAR" ]; then
  echo "ERROR: нет архива образа: $TAR" >&2
  echo "Положите ndtp-telemetry-emulator.tar в emulator/ (он исключён из Git)." >&2
  exit 1
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "==> Загрузка образа $IMAGE"
  docker load -i "$TAR"
fi

if [ "$(docker ps -q -f name="^$CONTAINER$")" ]; then
  echo "==> Контейнер $CONTAINER уже запущен"
elif [ "$(docker ps -aq -f name="^$CONTAINER$")" ]; then
  echo "==> Удаляю остановленный контейнер $CONTAINER"
  docker rm -f "$CONTAINER" >/dev/null
  docker run -d --rm -p "$API_PORT:18080" \
    --add-host=host.docker.internal:host-gateway \
    --name "$CONTAINER" "$IMAGE" >/dev/null
else
  echo "==> Запуск контейнера $CONTAINER (API :$API_PORT)"
  docker run -d --rm -p "$API_PORT:18080" \
    --add-host=host.docker.internal:host-gateway \
    --name "$CONTAINER" "$IMAGE" >/dev/null
fi

echo "==> Ожидание API эмулятора"
for _ in $(seq 1 30); do
  if curl -sf "http://localhost:$API_PORT/api/cells" >/dev/null; then
    break
  fi
  sleep 1
done
curl -sf "http://localhost:$API_PORT/api/cells" >/dev/null \
  || { echo "ERROR: API эмулятора не отвечает на :$API_PORT" >&2; exit 1; }

if [ -s "$CONFIG_FILE" ]; then
  echo "==> Загрузка конфига $CONFIG_FILE -> $TARGET_HOST:$TARGET_PORT"
  TARGET_HOST="$TARGET_HOST" TARGET_PORT="$TARGET_PORT" python3 - "$CONFIG_FILE" "$API_PORT" <<'PY'
import json, os, sys, urllib.request

config = json.load(open(sys.argv[1]))
config["targetHost"] = os.environ["TARGET_HOST"]
config["targetPort"] = int(os.environ["TARGET_PORT"])
req = urllib.request.Request(
    f"http://localhost:{sys.argv[2]}/api/config",
    data=json.dumps(config).encode(),
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req, timeout=10) as resp:
    print(resp.read().decode() or "OK")
PY
else
  echo "==> $CONFIG_FILE пуст — конфиг не загружен. Настрой вручную:"
  echo "   curl -s -X POST http://localhost:$API_PORT/api/config -H 'Content-Type: application/json' -d @config.json"
  echo "   (см. emulator/README.md)"
fi

echo "Готово. Логи: docker logs -f $CONTAINER"
