# Backend API

Backend является центральным слоем системы и связывает:

```text
NDTP Emulator
      │
      │ TCP
      ▼
   Backend
      │
      ├──────────────► Database
      │
      ├──────────────► ML Service
      │
      └──────────────► Frontend
```

Backend отвечает за:

* приём realtime NDTP-телеметрии;
* хранение текущего состояния транспортных средств;
* подготовку данных для ML-модуля;
* вызов ML inference;
* хранение последних прогнозов;
* формирование инцидентов;
* предоставление REST API для Dashboard;
* отправку realtime-обновлений Dashboard через WebSocket.

Backend **не обучает ML-модели**. Обучение выполняется отдельно. Backend работает только с готовым ML inference service.

---

# 1. Модули Backend

```text
backend/app/

├── api/
│   ├── router.py
│   ├── health.py
│   ├── vehicles.py
│   ├── predictions.py
│   ├── incidents.py
│   └── routes.py
│
├── ntdp/
│   ├── server.py
│   ├── parser.py
│   └── schemas.py
│
├── services/
│   ├── telemetry_service.py
│   ├── prediction_service.py
│   ├── incident_service.py
│   └── ml_client.py
│
├── schemas/
│   ├── vehicle.py
│   ├── prediction.py
│   └── incident.py
│
├── repositories/
│   ├── vehicle_repository.py
│   ├── prediction_repository.py
│   └── incident_repository.py
│
├── core/
│   └── config.py
│
└── main.py
```

## `ntdp`

Отвечает исключительно за получение и декодирование NDTP.

```text
NDTP packet
     ↓
TCP :9201
     ↓
ntdp/server.py
     ↓
ntdp/parser.py
     ↓
TelemetryEvent
```

Пример внутреннего объекта:

```json
{
  "unit_id": 1166336,
  "event_time": "2026-09-25T12:30:00",
  "lat": 55.7558,
  "lon": 37.6173,
  "speed": 18,
  "heading": 145,
  "location_valid": true
}
```

NDTP является TCP-протоколом, поэтому для него **не создаётся REST endpoint**.

Эмулятор подключается непосредственно к TCP-серверу Backend.

---

# 2. Telemetry Service

`telemetry_service.py` получает нормализованную телеметрию после NDTP parser.

```text
NDTP Parser
     ↓
TelemetryService
     ├── update current vehicle state
     ├── save telemetry
     └── trigger prediction
```

Этот слой не должен знать детали бинарного протокола NDTP.

---

# 3. ML Client

Backend не загружает CatBoost/PyTorch самостоятельно.

Он обращается к отдельному ML Service:

```text
Backend
   │
   │ HTTP
   ▼
ML Service
```

Основной внутренний endpoint:

```http
POST /predict
```

Пример запроса:

```json
{
  "tr_id": 131672,
  "T": "2026-09-25T12:30:00",
  "target_stop_id": 81231,
  "target_time_begin": "2026-09-25T12:42:00",
  "cur_dev_s": 76,
  "telemetry": [
    {
      "event_time": "2026-09-25T12:29:30",
      "lat": 55.7558,
      "lon": 37.6173,
      "speed": 18
    }
  ]
}
```

ML Service самостоятельно применяет тот же feature pipeline, который использовался при обучении модели.

Ответ:

```json
{
  "prediction": 143.5,
  "model": "catboost",
  "model_version": "1.2"
}
```

`prediction` — прогнозируемая задержка на целевой остановке в секундах.

---

# 4. Health API

## `GET /api/v1/health`

Проверка Backend.

Response:

```json
{
  "status": "ok",
  "service": "backend"
}
```

Используется Docker healthcheck и для быстрой проверки работоспособности.

---

# 5. Vehicles API

## `GET /api/v1/vehicles`

Возвращает текущее состояние всех активных ТС.

Используется картой Dashboard.

Response:

```json
{
  "vehicles": [
    {
      "tr_id": 131672,
      "lat": 55.7558,
      "lon": 37.6173,
      "speed": 18,
      "heading": 145,
      "current_delay_s": 76,
      "last_update": "2026-09-25T12:30:00"
    }
  ]
}
```

---

## `GET /api/v1/vehicles/{tr_id}`

Подробная информация об одном ТС.

Response:

```json
{
  "tr_id": 131672,
  "lat": 55.7558,
  "lon": 37.6173,
  "speed": 18,
  "heading": 145,
  "current_delay_s": 76,
  "last_update": "2026-09-25T12:30:00",
  "prediction": {
    "target_stop_id": 81231,
    "predicted_delay_s": 143.5,
    "risk": "medium"
  }
}
```

---

## `GET /api/v1/vehicles/{tr_id}/history`

Последняя история движения ТС.

Query:

```text
?minutes=15
```

Пример:

```http
GET /api/v1/vehicles/131672/history?minutes=15
```

Response:

```json
{
  "tr_id": 131672,
  "telemetry": [
    {
      "event_time": "2026-09-25T12:29:00",
      "lat": 55.7551,
      "lon": 37.6168,
      "speed": 23
    },
    {
      "event_time": "2026-09-25T12:30:00",
      "lat": 55.7558,
      "lon": 37.6173,
      "speed": 18
    }
  ]
}
```

Нужно для графиков/карточки ТС.

---

# 6. Predictions API

## `GET /api/v1/predictions`

Возвращает последние прогнозы.

Можно фильтровать:

```text
/api/v1/predictions?risk=high
/api/v1/predictions?tr_id=131672
```

Response:

```json
{
  "predictions": [
    {
      "tr_id": 131672,
      "prediction_time": "2026-09-25T12:30:00",
      "target_stop_id": 81231,
      "target_time": "2026-09-25T12:42:00",
      "current_delay_s": 76,
      "predicted_delay_s": 143.5,
      "risk": "medium"
    }
  ]
}
```

---

## `GET /api/v1/predictions/{tr_id}/latest`

Последний прогноз конкретного ТС.

Response:

```json
{
  "tr_id": 131672,
  "prediction_time": "2026-09-25T12:30:00",
  "target_stop_id": 81231,
  "target_time": "2026-09-25T12:42:00",
  "current_delay_s": 76,
  "predicted_delay_s": 143.5,
  "risk": "medium"
}
```

---

# 7. Incidents API

Инцидент — это прогноз, который требует внимания диспетчера.

Например:

```text
prediction < 120 sec
        ↓
     normal

prediction 120–300 sec
        ↓
     medium

prediction > 300 sec
        ↓
      high
        ↓
     INCIDENT
```

Конкретные пороги должны быть вынесены в конфигурацию.

---

## `GET /api/v1/incidents`

Список текущих проблем.

Response:

```json
{
  "incidents": [
    {
      "id": "inc_1821",
      "tr_id": 131672,
      "severity": "high",
      "predicted_delay_s": 340,
      "current_delay_s": 110,
      "target_stop_id": 81231,
      "created_at": "2026-09-25T12:30:00",
      "status": "active"
    }
  ]
}
```

Dashboard использует этот endpoint для списка алертов.

---

## `GET /api/v1/incidents/{incident_id}`

Карточка конкретного инцидента.

Response:

```json
{
  "id": "inc_1821",
  "tr_id": 131672,
  "severity": "high",
  "current_delay_s": 110,
  "predicted_delay_s": 340,
  "target_stop_id": 81231,
  "target_time": "2026-09-25T12:42:00",
  "status": "active",
  "reason": "segment_slowdown",
  "recommendation": "Проверить движение на участке перед целевой остановкой"
}
```

`reason` и `recommendation` добавляются только если соответствующая логика реализована.

---

# 8. Routes API

Для первого MVP этот модуль делаем минимальным.

## `GET /api/v1/routes`

Список маршрутов/рейсов, известных системе.

Используется для фильтров Dashboard.

---

## `GET /api/v1/routes/{route_id}`

Информация о конкретном маршруте, если необходимые данные доступны в используемом датасете.

---

# 9. Realtime WebSocket

REST нужен для загрузки начального состояния Dashboard.

Для realtime обновлений используем WebSocket:

```text
WS /api/v1/ws
```

После подключения frontend получает события.

### Vehicle update

```json
{
  "type": "vehicle_update",
  "data": {
    "tr_id": 131672,
    "lat": 55.7558,
    "lon": 37.6173,
    "speed": 18
  }
}
```

### Prediction update

```json
{
  "type": "prediction_update",
  "data": {
    "tr_id": 131672,
    "predicted_delay_s": 143.5,
    "risk": "medium"
  }
}
```

### Incident

```json
{
  "type": "incident",
  "data": {
    "id": "inc_1821",
    "tr_id": 131672,
    "severity": "high",
    "predicted_delay_s": 340
  }
}
```

Таким образом frontend не должен постоянно выполнять polling REST API.

---

# 10. Общая схема взаимодействия

```text
               NDTP Emulator
                     │
                     │ TCP :9201
                     ▼
              ┌──────────────┐
              │ NDTP Server  │
              └──────┬───────┘
                     ▼
              ┌──────────────┐
              │ NDTP Parser  │
              └──────┬───────┘
                     ▼
            ┌─────────────────┐
            │TelemetryService │
            └───┬─────────┬───┘
                │         │
                ▼         ▼
             Database   PredictionService
                              │
                              ▼
                         ML Client
                              │
                              │ POST /predict
                              ▼
                       ┌────────────┐
                       │ ML Service │
                       │            │
                       │ CatBoost   │
                       │ PyTorch    │
                       └─────┬──────┘
                             │
                        prediction
                             │
                             ▼
                     PredictionService
                             │
                   ┌─────────┴─────────┐
                   ▼                   ▼
             IncidentService       Database
                   │
                   └─────────┬─────────┘
                             ▼
                         WebSocket
                             │
                             ▼
                         Dashboard
```

---

# 11. MVP endpoints

Чтобы не тратить время, обязательными для первой рабочей версии считаем:

```text
GET  /api/v1/health

GET  /api/v1/vehicles
GET  /api/v1/vehicles/{tr_id}

GET  /api/v1/predictions
GET  /api/v1/predictions/{tr_id}/latest

GET  /api/v1/incidents
GET  /api/v1/incidents/{incident_id}

WS   /api/v1/ws
```

Внутренний ML API:

```text
GET  /health
POST /predict
```

Остальные endpoints добавляются только при необходимости Dashboard.

---

# 12. Swagger / OpenAPI

После запуска Backend документация API автоматически доступна:

```text
/docs
/redoc
/openapi.json
```

Все Pydantic schemas должны содержать описания основных полей, чтобы Swagger одновременно являлся документацией контракта Backend ↔ Frontend.

---

# 13. Главный принцип архитектуры

Каждый слой имеет одну ответственность:

```text
NDTP
 │
 ▼
parser          → только декодирование
 │
 ▼
service         → бизнес-логика
 │
 ▼
repository      → работа с хранилищем
 │
 ▼
ML client       → связь с ML
 │
 ▼
API/WebSocket   → связь с frontend
```

ML-модель ничего не должна знать про NDTP, WebSocket или Dashboard.

Frontend ничего не должен знать про NDTP или CatBoost.

Backend связывает эти части между собой.
