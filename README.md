<div align="center">

# Transport Delay Predictor

### Раннее предсказание задержек городского транспорта

**NDTP-телеметрия → ML-прогноз на 10–15 минут вперёд → предупреждение диспетчера**

</div>

---

## Смысл кейса

Диспетчер обычно видит задержку, когда транспорт уже выбился из расписания.
Наша система анализирует поток телеметрии и заранее предсказывает отклонение
от графика в секундах.

> 💡 Цель: дать диспетчеру время отреагировать **до** того, как задержка станет критической.

```text
NDTP-телеметрия
        ↓
Backend + история движения
        ↓
CatBoost / PyTorch / LightGBM
        ↓
⏱Прогноз задержки на 10–15 минут
        ↓
Диспетчерский дашборд
```

##  Стек

| Слой | Технологии |
| --- | --- |
| ML | CatBoost, LightGBM, PyTorch, pandas, NumPy |
| Backend | Python 3.12, FastAPI, Pydantic, async I/O |
| Telemetry | NDTP over TCP, realtime processing |
| Data | PostgreSQL, SQLAlchemy |
| Frontend | React 19, TypeScript, Vite, TanStack Query |
| Security | JWT, HttpOnly cookies, Argon2 |
| Infrastructure | Docker, Docker Compose, nginx |

##  Запуск

```bash
cp .env.example .env
docker compose up --build
```

| Сервис | Адрес |
| --- | --- |
| Дашборд | <http://localhost:8080> |
| Swagger API | <http://localhost:8000/docs> |
| Health check | <http://localhost:8000/api/v1/health> |

Демо-вход: `dispatcher` / `transport`. Перед деплоем замените пароль и `AUTH_JWT_SECRET` в `.env`.

## 📚 Документация

Собранные документы лежат в репозитории и открываются прямо из clone,
без запущенных сервисов:

| Файл | Что внутри |
| --- | --- |
| [`docs/public/pydoc/index.html`](docs/public/pydoc/index.html) | PyDoc (Sphinx): архитектура, авторизация, конфигурация, API backend, исходники модулей |
| [`docs/public/api.html`](docs/public/api.html) | OpenAPI-спецификация в Swagger UI: все эндпоинты, схемы, требования авторизации |
| [`docs/public/openapi.json`](docs/public/openapi.json) | Машиночитаемая схема — импорт в Postman или вставка в <https://redocly.github.io/redoc/> |

Пересобрать после изменений в коде или `.rst`-доках:

```bash
make docs
```

Живой Swagger и ReDoc — в запущенном backend: <http://localhost:8000/docs>,
<http://localhost:8000/redoc>.

## Структура

```text
backend/    FastAPI, NDTP, PostgreSQL, авторизация
ml/         признаки, обучение и inference service
frontend/   диспетчерский React-дашборд
emulator/   эмулятор NDTP-телеметрии
docs/       спецификация NDTP + собранные PyDoc и OpenAPI
```

<div align="center">

**Прогнозируем проблему раньше, чем она появится на табло.**

</div>
