# Dataset-backed NDTP replay

Дополнительный эмулятор для расширенного end-to-end дебага. Он не заменяет и
не изменяет эмулятор организаторов: исходный образ, `emulator/config.json` и
`scripts/start_emulator.sh` продолжают работать как раньше.

Сервис читает выбранные рейсы из `data/raw/<dataset>/traffic.csv`, раскрывает
строки последовательно во времени и передаёт их Backend по настоящему NDTP/TCP:

```text
traffic.csv → replay clock → NDTP encoder → TCP :9201 → Backend
```

Labels, фактическое расписание и будущие строки сервис не читает.

## Запуск

```bash
docker compose --profile replay up -d --build backend dataset-replay
```

API и Swagger:

```text
http://localhost:18081/docs
```

Сначала найдите подходящий рейс:

```bash
curl 'http://localhost:18081/api/scenarios?dataset=validate&limit=10'
```

Запустите воспроизведение в исходном масштабе времени 1:1:

```bash
curl -X POST http://localhost:18081/api/replay/start \
  -H 'Content-Type: application/json' \
  -d '{
    "dataset": "validate",
    "tr_ids": [131672],
    "time_mode": "shift_to_now",
    "valid_locations_only": true
  }'
```

Управление:

```bash
curl http://localhost:18081/api/status
curl -X POST http://localhost:18081/api/replay/pause
curl -X POST http://localhost:18081/api/replay/resume
curl -X POST http://localhost:18081/api/replay/stop
```

После старта данные появляются в обычном Backend API:

```bash
curl http://localhost:8000/api/v1/vehicles
```

## Временные режимы

- `shift_to_now` — сохраняет интервалы исходной записи, но переносит timestamp
  первого пакета к моменту запуска. Это рекомендуемый режим для live dashboard.
- `original` — отправляет исходные timestamps из CSV. Полезен для точного
  исторического дебага.

События планируются по `max(event_time, receive_time)`, поэтому пакет никогда не
появляется раньше момента, когда он был доступен в исходной системе. NDTP
timestamp сохраняет именно `event_time` с выбранным временным сдвигом.

## Несколько машин и диапазон

`tr_ids` принимает до 100 рейсов. На каждый уникальный `unit_id` создаётся своё
TCP-соединение и выполняется отдельный NDTP handshake. Общий scheduler сохраняет
исходный порядок доступности и реальные интервалы между пакетами. Ускорение не
применяется: одна секунда записи всегда воспроизводится за одну секунду.

Можно ограничить сценарий ISO-датами `start_at` и `end_at`, включить `loop` или
переопределить `target_host`/`target_port` в запросе. По умолчанию пропускаются
строки с невалидными координатами; для протокольного дебага установите
`valid_locations_only: false`.


## Переменные окружения

Все параметры имеют префикс `REPLAY_`:

| Переменная | По умолчанию |
| --- | --- |
| `REPLAY_DATA_ROOT` | `/data` |
| `REPLAY_NDTP_TARGET_HOST` | `backend` |
| `REPLAY_NDTP_TARGET_PORT` | `9201` |
| `REPLAY_CONNECT_TIMEOUT_S` | `5` |
| `REPLAY_RECONNECT_DELAY_S` | `1` |
| `REPLAY_HANDSHAKE_DELAY_S` | `0.2` |
