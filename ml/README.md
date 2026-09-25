# ML-контур прогнозирования задержек

Этот каталог содержит полный жизненный цикл ML-модели: подготовку исходных данных, генерацию признаков, обучение CatBoost и PyTorch, ансамбль, инференс и HTTP-сервис для backend.

## Быстрая навигация

| Каталог | Назначение |
| --- | --- |
| `src/dataset.py` | чтение и проверка CSV из `data/raw` |
| `src/features.py` | бизнес- и временные признаки |
| `src/preprocessing.py` | единый fit/transform-пайплайн, без утечки target |
| `src/models/` | отдельные реализации CatBoost, PyTorch и ансамбля |
| `src/training/` | воспроизводимые точки запуска обучения |
| `src/inference/` | загрузка артефактов и предсказание |
| `service/` | FastAPI-контракт для backend |
| `notebooks/` | исследование данных и эксперименты |
| `artifacts/` | локальные веса и метаданные; бинарные файлы не коммитим |

## Локальный запуск

Из корня репозитория:

```bash
cd ml
python -m venv .venv && source .venv/bin/activate
pip install -e .
python -m src.training.train_catboost --data-dir ../data --output-dir artifacts
python -m src.training.train_torch --data-dir ../data --output-dir artifacts
uvicorn service.main:app --reload --port 8001
```

Проверка сервиса:

```bash
curl http://localhost:8001/health
curl -X POST http://localhost:8001/predict -H 'Content-Type: application/json' -d '{"tr_id":"122048","T":"2026-01-06 02:10:00","cur_dev_s":0,"speed":0,"lat":55.75,"lon":37.61}'
```

Для разработки зависимости ML можно установить отдельно: `pip install -e '.[dev,models]'`.

## Данные и схема

По умолчанию ожидается такая раскладка относительно корня проекта:

```text
data/raw/train/traffic.csv
data/raw/train/schedule.csv
data/raw/labels/labels_train.csv
data/raw/test/traffic.csv
data/raw/test/schedule.csv
```

`labels_train.csv` — единственный источник target. Признаки должны строиться только из доступного на момент `T` контекста. Это особенно важно для `target_delay_s`: его нельзя передавать в `features.py` при inference.

## Обучение и артефакты

Оба train-скрипта сохраняют модель, конфигурацию признаков и метрики в `ml/artifacts/`. Имена файлов фиксированы и подходят для загрузки сервисом. Папка оставлена в Git через `.gitkeep`; реальные веса следует хранить в Kaggle Dataset, object storage или Git LFS, а не в обычном Git.

Рекомендуемый порядок: `01_eda.ipynb` (качество данных и временной split), `02_catboost.ipynb` (табличный baseline), `03_pytorch.ipynb` (нейросетевая модель), затем оба train-скрипта, проверка `metrics.json` и запуск FastAPI.

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

`POST /predict` принимает JSON с контекстом рейса и возвращает `delay_seconds`, `delay_class` и `model_version`. `GET /health` используется Docker healthcheck. Если артефакт отсутствует, сервис отвечает понятной ошибкой конфигурации, а не использует случайные веса.

## Принципы воспроизводимости

- фиксируем `random_seed`;
- разделяем train/validation по времени, а не случайно;
- сохраняем список признаков и параметры preprocessing рядом с весами;
- не допускаем target leakage;
- версионируем данные и артефакты отдельно от исходного кода.
