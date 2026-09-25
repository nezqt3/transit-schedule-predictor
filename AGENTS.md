# AGENTS.md

## Project Overview

This repository contains a hackathon solution for early prediction of public transport schedule deviations.

The system processes realtime NDTP telemetry, combines it with schedule information, predicts vehicle delay **10–15 minutes ahead**, and exposes the result to a dispatcher dashboard.

The competition ML target is:

```text
target_delay_s
```

It represents the predicted schedule deviation in **seconds** at the target stop.

The primary competition metric is **MAE**.

The project must support:

* Python 3.12+
* CatBoost
* PyTorch
* Docker
* realtime NDTP telemetry processing
* Backend API
* ML inference service
* dispatcher dashboard

---

# 1. Main Priority

This is a hackathon project with a strict deadline.

Prioritize:

1. Working end-to-end functionality.
2. ML score.
3. Correct realtime NDTP processing.
4. Stable Backend ↔ ML integration.
5. Dispatcher dashboard.
6. Dockerized startup.
7. Swagger/OpenAPI documentation.
8. Minimal Sphinx documentation.

Do NOT spend significant time on:

* excessive unit tests;
* complex CI/CD;
* Kubernetes;
* Kafka;
* microservice overengineering;
* unnecessary design patterns;
* premature optimization;
* large abstraction layers;
* perfect code coverage.

Prefer simple, readable, working code.

---

# 2. Repository Structure

Expected repository structure:

```text
.
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── core/
│   │   ├── ntdp/
│   │   ├── repositories/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   ├── docs/
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── ml/
│   ├── src/
│   │   ├── models/
│   │   ├── training/
│   │   ├── inference/
│   │   ├── dataset.py
│   │   ├── features.py
│   │   └── preprocessing.py
│   ├── service/
│   ├── notebooks/
│   ├── artifacts/
│   ├── Dockerfile
│   └── requirements.txt
│
├── frontend/
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── submissions/
│
├── emulator/
│
├── infra/
│
├── scripts/
│
├── docker-compose.yml
├── .env.example
├── .gitignore
├── Makefile
├── README.md
└── AGENTS.md
```

Do not create new top-level directories unless there is a clear need.

---

# 3. Architecture

The main runtime data flow is:

```text
NDTP Emulator
      │
      │ TCP
      ▼
Backend NDTP Server
      │
      ▼
NDTP Parser
      │
      ▼
Telemetry Service
      │
      ├──────────────► Storage
      │
      ▼
Prediction Service
      │
      ▼
ML Service
      │
      ▼
Prediction
      │
      ▼
Incident Service
      │
      ▼
REST / WebSocket
      │
      ▼
Dashboard
```

Training is a separate offline process:

```text
CSV Dataset
     │
     ▼
Feature Engineering
     │
     ├────────► CatBoost
     │
     └────────► PyTorch
                    │
                    ▼
              Model Artifacts
                    │
                    ▼
                ML Service
```

Training may run on Kaggle GPU.

Kaggle is NOT part of the production/runtime architecture.

---

# 4. Backend Responsibilities

Backend is responsible for:

* receiving NDTP telemetry;
* decoding NDTP packets;
* maintaining vehicle state;
* storing/retrieving telemetry when required;
* calling ML inference;
* creating dispatcher incidents;
* exposing REST API;
* exposing WebSocket realtime updates;
* orchestration between system components.

Backend must NOT:

* train ML models;
* contain CatBoost/PyTorch training logic;
* duplicate ML feature engineering unnecessarily;
* contain frontend business logic.

---

# 5. Backend API

API prefix:

```text
/api/v1
```

Minimum API:

```text
GET /api/v1/health

GET /api/v1/vehicles
GET /api/v1/vehicles/{tr_id}

GET /api/v1/predictions
GET /api/v1/predictions/{tr_id}/latest

GET /api/v1/incidents
GET /api/v1/incidents/{incident_id}

WS  /api/v1/ws
```

Do not add endpoints unless they are required by the frontend, realtime pipeline, or hackathon functionality.

FastAPI automatically exposes:

```text
/docs
/redoc
/openapi.json
```

Swagger/OpenAPI schemas should be generated from Pydantic models.

---

# 6. ML Service API

ML is an independent service.

Minimum endpoints:

```text
GET /health
POST /predict
```

Example response:

```json
{
  "prediction": 143.5,
  "model": "catboost",
  "model_version": "1.0"
}
```

`prediction` represents predicted delay in seconds.

Backend may convert this value into dispatcher-oriented information such as:

```text
risk
severity
incident
recommendation
```

Do not mix those concepts into the competition model target.

---

# 7. ML Target

The main target is regression:

```text
target_delay_s
```

Do NOT convert the primary task into simple delay/no-delay classification.

The model predicts schedule deviation in seconds.

Positive value:

```text
vehicle is late
```

Negative value:

```text
vehicle is ahead of schedule
```

The main metric is:

```text
MAE
```

Lower is better.

---

# 8. Prediction Horizon

For prediction point `T`, the target stop is the first stop whose planned arrival is inside:

```text
(T + 10 minutes, T + 15 minutes]
```

Only information available at or before `T` may be used.

This rule is critical.

Never use telemetry where:

```text
event_time > T
```

during training feature generation or inference.

This would cause target leakage.

---

# 9. Feature Engineering

Feature engineering must be reusable between training and inference.

Do NOT maintain two unrelated implementations such as:

```text
Kaggle feature code
```

and

```text
Production feature code
```

Shared feature logic belongs in:

```text
ml/src/features.py
ml/src/preprocessing.py
```

Typical features may include:

```text
cur_dev_s

current_speed

speed_mean_1m
speed_mean_3m
speed_mean_5m

speed_std

acceleration

distance_to_target_stop

time_to_target_stop

vehicle movement history

coordinates

heading

time features

vehicle / route / stop identifiers
```

Features must only use information available at prediction time `T`.

---

# 10. ML Models

Development order:

```text
1. Baseline
2. CatBoost
3. PyTorch sequence model
4. Ensemble if useful
```

Do not start by implementing a large Transformer.

CatBoost is the primary baseline model.

Possible PyTorch models:

```text
GRU
LSTM
TCN
small Transformer
```

Prefer GRU/TCN before introducing unnecessary model complexity.

GPU should primarily be used for training.

Production inference should work on CPU whenever practical.

---

# 11. Baseline

A known simple baseline is:

```python
prediction = cur_dev_s
```

New models should be evaluated against this baseline.

Do not assume a more complex model is better without validation.

---

# 12. Validation

Training and validation must respect time.

Avoid random row-level splitting when it can leak temporal information.

Preferred structure:

```text
older data
    ↓
TRAIN

newer data
    ↓
VALIDATION / TEST
```

The provided test labels should be used for local model comparison where appropriate.

Never use validate ground truth because it is unavailable.

---

# 13. NDTP

Realtime telemetry arrives through TCP.

The emulator is NOT a REST telemetry producer.

Flow:

```text
NDTP Emulator
      │
      │ TCP
      ▼
Backend
```

Backend should expose a TCP server, for example:

```text
:9201
```

NDTP responsibilities must stay inside:

```text
backend/app/ntdp/
```

Recommended separation:

```text
server.py
    ↓
receives bytes

parser.py
    ↓
decodes NDTP

schemas.py
    ↓
normalized telemetry objects
```

Business services should work with normalized telemetry objects and should not depend directly on binary NDTP structures.

---

# 14. Realtime Processing

Expected realtime flow:

```text
packet
  ↓
parse
  ↓
normalize
  ↓
update vehicle state
  ↓
build/update features
  ↓
ML inference
  ↓
prediction
  ↓
incident evaluation
  ↓
WebSocket event
```

Do not call ML for every packet if doing so creates unnecessary load.

Prediction frequency may be throttled/configured independently from telemetry frequency.

---

# 15. WebSocket

Use WebSocket for realtime dashboard updates.

Main event types:

```text
vehicle_update
prediction_update
incident
```

Example:

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

REST should provide initial/current state.

WebSocket should provide subsequent realtime updates.

---

# 16. Docker

The complete application should be startable using:

```bash
docker compose up --build
```

Expected services may include:

```text
backend
ml
frontend
postgres
```

Do not introduce additional infrastructure unless required.

Backend and ML must have separate Docker images.

Python version:

```text
3.12+
```

---

# 17. Configuration

Configuration must come from environment variables.

Do not hardcode service addresses.

Example:

```env
BACKEND_PORT=8000

ML_SERVICE_URL=http://ml:8001

ML_SERVICE_PORT=8001

NDTP_HOST=0.0.0.0
NDTP_PORT=9201

POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=transport
POSTGRES_USER=transport
POSTGRES_PASSWORD=transport
```

Secrets must not be committed.

Keep `.env.example` in Git.

Keep `.env` ignored.

---

# 18. Data

Large datasets must not be committed to Git.

Expected local structure:

```text
data/raw/train/
data/raw/test/
data/raw/validate/
data/raw/labels/
```

Generated feature tables belong in:

```text
data/processed/
```

Submission files belong in:

```text
data/submissions/
```

Do not overwrite raw competition data.

---

# 19. Model Artifacts

Trained models belong in:

```text
ml/artifacts/
```

Examples:

```text
catboost.cbm
torch.pt
feature_config.json
metadata.json
```

Large model artifacts should normally not be committed directly to Git.

The inference service must fail with a clear error if the configured model artifact cannot be loaded.

---

# 20. Code Style

Prefer:

* small functions;
* explicit names;
* type hints;
* Pydantic schemas at API boundaries;
* async I/O where appropriate;
* simple dependency flow;
* readable code over clever code.

Avoid:

* unnecessary classes;
* deep inheritance;
* excessive interfaces;
* premature generic abstractions;
* global mutable state when avoidable.

Use comments primarily to explain non-obvious decisions.

Do not comment obvious Python syntax.

---

# 21. Documentation

Public/backend-facing functions should have concise docstrings where useful.

Use Google-style docstrings compatible with Sphinx Napoleon.

Example:

```python
def calculate_delay(
    planned_time: float,
    actual_time: float,
) -> float:
    """
    Calculate schedule deviation.

    Args:
        planned_time: Planned arrival time.
        actual_time: Actual arrival time.

    Returns:
        Schedule deviation in seconds.
    """
```

Do not spend significant time documenting trivial internal helpers.

---

# 22. Testing

Testing is intentionally minimal because of the hackathon deadline.

Required test:

```text
backend/tests/test_health.py
```

It should verify:

```text
GET /api/v1/health
```

returns HTTP `200` and service status `ok`.

Do not create extensive test suites unless a test is necessary to debug or protect critical functionality.

Critical parsing logic may receive targeted tests if bugs appear during development.

---

# 23. Error Handling

External boundaries must fail gracefully.

Especially:

```text
NDTP connection failure
ML service unavailable
invalid NDTP packet
database unavailable
model artifact unavailable
```

The entire Backend should not crash because one telemetry packet is malformed.

Log the error and continue processing when safe.

If ML is temporarily unavailable, Backend should remain alive.

---

# 24. Logging

Use standard Python `logging`.

Important events:

```text
service startup
service shutdown

NDTP client connected/disconnected

invalid NDTP packet

ML request failure

prediction generated

incident created
```

Do not log every normal operation at ERROR level.

Avoid excessive packet-by-packet logs in normal production/demo mode.

---

# 25. Git Workflow

Main branches:

```text
main
dev
```

Feature branches:

```text
feature/backend
feature/ml-model
feature/data-pipeline
feature/dashboard
```

Prefer:

```text
feature branch
      ↓
     dev
      ↓
integration check
      ↓
     main
```

Do not perform unrelated large refactors while implementing a feature.

---

# 26. Rules for AI Coding Agents

Before modifying code:

1. Inspect the relevant existing files.
2. Preserve the current architecture unless a change is necessary.
3. Prefer modifying existing modules over creating duplicate functionality.
4. Keep changes scoped to the requested task.
5. Do not introduce new frameworks without a clear requirement.
6. Do not rewrite working components solely for stylistic reasons.
7. Do not add extensive tests unless explicitly requested.
8. Do not introduce infrastructure that is unnecessary for the hackathon.
9. Maintain Python 3.12 compatibility.
10. Maintain Docker compatibility.

When implementing an API endpoint:

1. Add/update the Pydantic schema.
2. Add the endpoint to the appropriate router.
3. Put business logic in a service rather than directly in the router when non-trivial.
4. Keep the OpenAPI contract clear.
5. Avoid unnecessary repository abstractions for trivial temporary state.

When implementing ML:

1. Prevent future-data leakage.
2. Reuse preprocessing/feature code.
3. Compare against the baseline.
4. Measure MAE.
5. Save model metadata.
6. Keep training separate from inference.

When implementing NDTP:

1. Keep binary parsing isolated.
2. Validate packet boundaries before reading fields.
3. Do not let malformed packets crash the server.
4. Convert decoded packets into normalized internal schemas.
5. Keep protocol-specific code out of business services.

---

# 27. Definition of Done

For hackathon features, "done" means:

```text
feature works
      +
integrates with existing system
      +
runs in Docker where applicable
      +
does not break main flow
      +
is understandable enough for another teammate
```

It does NOT require:

```text
100% test coverage
perfect architecture
production-grade observability
enterprise CI/CD
complete abstraction of every component
```

The goal is a reliable, demonstrable hackathon solution.
