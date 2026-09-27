# Предиктор отклонений городского транспорта

NDTP-пакет поступает в backend по TCP. Backend сопоставляет терминал с рейсом,
выбирает первую плановую остановку в интервале **(T + 10 минут, T + 15 минут]**,
запрашивает ML-прогноз отклонения в секундах и отправляет событие диспетчеру.

## Запуск с нуля

Нужны Git и Docker Compose. Выполняйте команды из корня проекта.

1. Проверьте наличие входных файлов:

```bash
test -f data/raw/validate/traffic.csv
test -f data/raw/validate/schedule_plan.csv
test -f ml/artifacts/release_manifest.json
```

2. Создайте локальную конфигурацию и запустите сервисы:

```bash
cp .env.example .env
docker compose up -d --build
```

3. Проверьте запуск:

```bash
docker compose ps
curl http://localhost:8000/api/v1/health
curl http://localhost:8001/health
```

4. Откройте дашборд: <http://localhost:8080>. Вход: `dispatcher` / `transport`.
Swagger: <http://localhost:8000/docs>.

5. Выберите источник NDTP-телеметрии:

| Команда | Источник | Назначение |
|---|---|---|
| `make up-ndtp` | Официальный Docker-эмулятор | Проверка настоящего NDTP TCP-протокола на синтетических координатах |
| `make up-dataset-replay` | CSV из `data/raw/` | Воспроизведение исторических рейсов и прогнозов на дашборде |

Для `make up-ndtp` положите переданный организаторами файл строго по пути:

```text
emulator/ndtp-telemetry-emulator.tar
```

Затем запустите нужный режим:

```bash
make up-ndtp             # официальный эмулятор
make up-dataset-replay
```

Если архив находится в другом месте:

```bash
make up-ndtp NDTP_EMULATOR_ARCHIVE=/полный/путь/ndtp-telemetry-emulator.tar
```

Полезные команды:

```bash
docker compose logs -f   # посмотреть логи
docker compose down      # остановить проект
```

Подробные режимы запуска описаны в [`ЗАПУСК.md`](ЗАПУСК.md), результаты приёмки — в
[`ПРОТОКОЛ-приёмки.md`](docs/ПРОТОКОЛ-приёмки.md).

## Конкурсный результат

Выбранный кандидат — LightGBM plan, `lightgbm-plan-2026-09-26`. Локальная MAE
на 353 размеченных test-точках: **58,6033 с** против **93,3598 с** у baseline
`cur_dev_s`. По сообщению команды, результат LightGBM на платформе —
**score 1 = 1 (максимум)**; скрин или ссылка на конкретную отправку пока не
приложены, поэтому связь с хешем текущего CSV документально не проверена.
Файл `data/submissions/final_submission.csv` имеет 151 строку и формат
`sample_id;prediction`. Проверка: `python scripts/verify_submission.py`.
Паритет офлайн-прогноза и ML API: `python scripts/verify_model_parity.py`.

## Состав

| Компонент | Назначение |
|---|---|
| `backend/` | FastAPI, авторизация, NDTP TCP, состояние транспорта, прогнозы и инциденты |
| `ml/` | Общие признаки офлайн/сервис, LightGBM, калибровка вероятности |
| `frontend/` | Карта, список транспорта, риск и карточка инцидента |
| `emulator/` | Историческая NDTP-подача и интеграция с эмулятором организаторов |
| `docs/` | [ТЗ](docs/ТЗ-доработки-системы.md), [эксперименты](docs/ML-эксперименты.md), [NDTP](docs/Телеметрия-и-карты.md), [OpenAPI](docs/public/api.html) и [Sphinx](docs/public/pydoc/index.html) |

Прогнозы и история инцидентов сохраняются в PostgreSQL и восстанавливаются после
перезапуска backend. При временной недоступности БД сервис продолжает работать в
памяти. Map matching использует HMM/Viterbi и направленный граф маршрута; по
умолчанию граф строится из плана. Для точной дорожной геометрии положите GeoJSON
в `data/raw/road_network.geojson` (LineString с `properties.tr_id`) и задайте в
`.env`: `RUNTIME_ROUTE_GRAPH_PATH=/app/data/raw/road_network.geojson`.

What-if учитывает загрузку дорог, пассажиров и вместимость резерва, пересадку,
остаток рейса и оборот ТС перед следующим рейсом. Исторический табличный экран
остаётся ретроспективной диагностикой; будущие факты до их логического времени
не выдаются.
