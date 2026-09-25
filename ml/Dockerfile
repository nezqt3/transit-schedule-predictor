FROM python:3.11-slim
WORKDIR /app/ml
COPY pyproject.toml .
COPY src ./src
COPY service ./service
COPY artifacts ./.artifacts
RUN pip install --no-cache-dir .
ENV ARTIFACTS_DIR=/app/ml/.artifacts
EXPOSE 8001
CMD ["uvicorn", "service.main:app", "--host", "0.0.0.0", "--port", "8001"]
