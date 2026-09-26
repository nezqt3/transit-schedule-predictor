<div align="center">

# Transport Delay Predictor

### Раннее предсказание задержек городского транспорта

**NDTP-телеметрия → ML-прогноз на 10–15 минут вперёд → предупреждение диспетчера**

Команда: Алексеенко Денис · Верещагин Илья · Урманов Артём

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
CatBoost / PyTorch
        ↓
Прогноз задержки на 10–15 минут
        ↓
Диспетчерский дашборд
```

## Стек

| Слой | Технологии |
| --- | --- |
| ML | CatBoost, LightGBM, PyTorch, pandas, NumPy |
| Backend | Python 3.12, FastAPI, Pydantic, async I/O |
| Telemetry | NDTP over TCP, realtime processing |
| Data | PostgreSQL, SQLAlchemy |
| Frontend | React 19, TypeScript, Vite, TanStack Query |
| Security | JWT, HttpOnly cookies, Argon2 |
| Infrastructure | Docker, Docker Compose, nginx |

## Быстрый запуск

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

Сырые данные соревнования (`data/raw/...`) в Git не коммитятся — их нужно
положить локально до запуска replay-сценариев.

## 📡 Как подать поток

```bash
make up-dataset-replay   # рекомендуемый демо-путь: реальный датасет → NDTP → backend
make up-ndtp             # официальный эмулятор организаторов (:18080)
```

Первая команда поднимает стек и сама запускает NDTP-поток по реальному рейсу
из `validate`. Управление потоком (выбор рейсов, скорость, пауза) —
<http://localhost:18081/docs>.

- Пошаговая инструкция для демо (поток, прогнозы, алерты, метрики):
  [ЗАПУСК.md](ЗАПУСК.md)
- Подробности эмуляторов, январской карты реальных проездов и восстановления
  маршрутов: [docs/Телеметрия-и-карты.md](docs/Телеметрия-и-карты.md)
- CLI-варианты подачи: `REPLAY_TR_ID=131672 make replay-start`,
  `REPLAY_ALL_VALID=1 REPLAY_SPEED=60 python scripts/start_dataset_replay.py`

## Документация

| Документ | Что внутри |
| --- | --- |
| [Инструкция для жюри](ЗАПУСК.md) | Как за 3 минуты подать поток и показать прогнозы, алерты и метрики |
| [`docs/public/api.html`](docs/public/api.html) | OpenAPI в Swagger UI — открывается прямо из clone, без запущенных сервисов |
| [`docs/public/pydoc/index.html`](docs/public/pydoc/index.html) | PyDoc (Sphinx): архитектура, авторизация, конфигурация, модули backend |
| [docs/ML-эксперименты.md](docs/ML-эксперименты.md) | Kaggle, метрики чемпиона, история ML-экспериментов |
| [docs/Телеметрия-и-карты.md](docs/Телеметрия-и-карты.md) | Эмуляторы NDTP, NDTP-карта и исторический прогон |
| [`docs/Emulator-and-Telematic-Packets-Specification.md`](docs/Emulator-and-Telematic-Packets-Specification.md) | Спецификация NDTP-пакетов от организаторов |
| [backend/README.md](backend/README.md) · [ml/README.md](ml/README.md) · [frontend/README.md](frontend/README.md) | Запуск и разработка отдельных контуров |

Собрать документацию заново после изменений в коде: `make docs`.
Живые Swagger и ReDoc — в запущенном backend: <http://localhost:8000/docs>,
<http://localhost:8000/redoc>.

## Структура

```text
backend/    FastAPI, NDTP-парсер, PostgreSQL, авторизация
ml/         признаки, preprocessing, обучение и inference service
frontend/   диспетчерский React-дашборд
emulator/   официальный эмулятор + dataset-replay (CSV → NDTP)
docs/       гайды и собранная документация
data/       raw-датасеты соревнования (не в Git)
scripts/    запуск эмуляторов, экспорт OpenAPI
```

<div align="center">

**Прогнозируем проблему раньше, чем она появится на табло.**

</div>
