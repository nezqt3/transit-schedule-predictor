FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY src ./src
COPY service ./service
COPY artifacts/lightgbm_plan_direct.txt artifacts/lightgbm_plan_residual.txt \
     artifacts/lightgbm_plan_metadata.json artifacts/risk_calibration.json \
     artifacts/release_manifest.json ./artifacts/

ENV ARTIFACTS_DIR=/app/artifacts

EXPOSE 8001

CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8001"]
