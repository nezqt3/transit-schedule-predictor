# ML-контур прогнозирования задержек

Этот каталог содержит полный жизненный цикл ML-модели: подготовку исходных данных, генерацию признаков, обучение CatBoost и PyTorch, ансамбль, инференс и HTTP-сервис для backend.

## Быстрая навигация

| Каталог | Назначение |
| --- | --- |
| `src/offline/dataset_builder.py` | чтение CSV и временное соединение точек с телеметрией |
| `src/features.py` | единое ядро признаков для offline и online |
| `src/offline/` | сборка Parquet, обучение residual CatBoost, сабмит |
| `src/preprocessing.py` | очистка исходных таблиц для исследовательских экспериментов |
| `src/models/` | отдельные реализации CatBoost, PyTorch и ансамбля |
| `src/training/` | воспроизводимые точки запуска обучения |
| `src/inference/` | загрузка артефактов и предсказание |
| `service/` | FastAPI-контракт для backend |
| `notebooks/` | исследование данных и эксперименты |
| `artifacts/` | локальные веса и метаданные; бинарные файлы не коммитим |

## Локальный запуск

Из корня репозитория:

```bash
python -m pip install -r ml/requirements.txt
make features
make train
make submit
docker compose up --build
```

Без `make` используйте из каталога `ml`: `python -m src.offline.dataset_builder
--split all`, затем `python -m src.offline.train` и
`python -m src.offline.predict_submission`. На Windows команды также можно
запускать напрямую в PowerShell. Для локального API:
`cd ml && python -m uvicorn service.main:app --port 8001`.

Обучение создаёт `ml/artifacts/catboost_residual_mae.cbm` и метаданные `.json`.
Они не входят в Git: перед `docker compose up --build` нужен обученный артефакт.
Если его нет, ML-сервис явно завершится с ошибкой. Метрика test сохраняется в
метаданных; для нормированного score организаторов передайте опубликованное
`MAE_TARGET` через переменную окружения или `--mae-target`. Без него поле score
остаётся `null`, чтобы не выдумывать константу.

Проверка сервиса:

```bash
curl http://localhost:8001/health
curl -X POST http://localhost:8001/predict -H 'Content-Type: application/json' -d '{"tr_id":122048,"T":"2026-01-06T02:10:00","cur_dev_s":0,"target_stop_id":53699018679,"target_time_begin":"2026-01-06T02:22:00","stop_lat":55.61389253,"stop_lon":37.74851317,"telemetry":[]}'
```

PyTorch для отдельных последовательных экспериментов ставится отдельно:
`python -m pip install -e './ml[models]'` из корня проекта. Runtime Docker
использует CatBoost на CPU.

Текущий конкурсный CatBoost-ансамбль и экспериментальный PyTorch blend на
обработанных CSV воспроизводятся из корня проекта так:

```bash
python scripts/exp_simple_target_mode.py --write-candidate
python scripts/exp_torch_blend.py
python scripts/exp_torch_blend.py --export-experimental-weight 0.05
```

Последняя команда создаёт `data/submissions/catboost_torch_5pct_experimental_submission.csv`.
PyTorch-модель и параметры нормализации сохраняются в `ml/artifacts/torch_tabular.pt`.
Вес PyTorch подбирается на временных срезах train; если лучший вес равен нулю,
обычный запуск не создаёт новый сабмит. Экспериментальный CSV с явно заданным
весом полезен для отдельной проверки, но не заменяет модель с лучшей локальной
валидацией автоматически.

Для сравнения новых моделей по отдельности:

```bash
python scripts/exp_plan_routes.py
python scripts/exp_torch_seeds.py
python scripts/exp_lightgbm_plan.py
```

Признаки планового маршрута строятся только из `tr_id`, `tt_action_item_id`,
`time_begin` и `geom` расписания. Поля фактического прибытия и отклонения
(`time_fact_begin`, `dev_s`) в этих экспериментах не читаются.

## Данные и схема

По умолчанию ожидается такая раскладка относительно корня проекта:

```text
data/raw/train/traffic.csv
data/raw/train/schedule.csv
data/raw/labels/labels_train.csv
data/raw/test/traffic.csv
data/raw/test/schedule.csv
```

Метки train и test используются отдельно. Для каждого `(tr_id, T)` окно
телеметрии равно `[T−15 минут, T]`; используются только пакеты с
`location_valid=True`, `event_time<=T` и, если есть, `receive_time<=T`.
Модель учится на `target_delay_s−cur_dev_s`, а сервис возвращает сумму
`cur_dev_s+predicted_delta`. `submission.csv` имеет две колонки
`sample_id;prediction`, UTF-8 и ограничение прогнозов `[-300, 700]`.

## Обучение и артефакты

Команда `make train` сохраняет модель, список признаков и метрики в `ml/artifacts/`.

Исследовательские notebooks и старые эксперименты остаются отдельно от
канонического контура `src/offline/`.

## Kaggle: эксперименты и хранение результата

Kaggle удобно использовать как удалённую среду с GPU, ноутбуками, версиями Dataset и сохранением output после обучения:

- [Kaggle Notebooks](https://www.kaggle.com/code) — запуск ноутбуков из `ml/notebooks`;
- [Kaggle Datasets](https://www.kaggle.com/datasets) — хранение очищенных данных, feature-наборов и артефактов;
- [Kaggle Models](https://www.kaggle.com/models) — публикация версионируемых моделей.

Основной командный notebook: [transit-delay team notebook](https://www.kaggle.com/code/nezqt52/notebook34755737a1/edit). Его нужно расшарить на всех трёх участников с правом `Can edit`.

Пошаговые настройки для команды и шаблон участников находятся в [`kaggle/README.md`](kaggle/README.md). Не добавляйте `kaggle.json` или API token в репозиторий.

Ссылку на конкретный Kaggle Dataset или Competition нужно вписать в переменную `KAGGLE_DATASET_URL` в `.env`/CI после создания приватного или публичного набора. В коде не зашиваем несуществующую ссылку: команда сможет заменить источник без изменения пайплайна.

После обучения в Kaggle артефакты находятся в `/kaggle/working/artifacts`; сохраните их через `Save Version` с включённым output или загрузите в Dataset. Для API скачайте ту же версию в `ml/artifacts`:

```bash
pip install kaggle
kaggle datasets download -d <owner>/<dataset-slug> -p ml/artifacts --unzip
```

`artifact_manifest.json` должен содержать версию датасета, commit проекта, seed и дату обучения.

## Контракт сервиса

`POST /predict` принимает `tr_id`, `T`, `cur_dev_s`, идентификатор и
координаты целевой остановки, её плановое время и список нормализованных
точек NDTP. Ответ: `prediction` в секундах, `model` и `model_version`.
`GET /health` используется Docker healthcheck.

## Принципы воспроизводимости

- фиксируем `random_seed`;
- разделяем train/validation по времени, а не случайно;
- сохраняем список признаков и параметры preprocessing рядом с весами;
- не допускаем target leakage;
- версионируем данные и артефакты отдельно от исходного кода.
