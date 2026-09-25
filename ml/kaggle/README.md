# Kaggle-команда из трёх человек

## Ресурсы команды

| Ресурс | Ссылка/место | Кто владеет |
| --- | --- | --- |
| Главный Notebook | [notebook34755737a1](https://www.kaggle.com/code/nezqt52/notebook34755737a1/edit) | владелец Kaggle-аккаунта `nezqt52` |
| Общий Dataset | создать и вписать URL в `.env` | команда |
| Модели и output | версия общего Dataset | команда |

## Настройка доступа

1. Владелец открывает Notebook → `Share`/`Sharing` → добавляет двух других Kaggle-пользователей с правом `Can edit`.
2. Владелец создаёт приватный Dataset, например `transit-delay-team-artifacts`.
3. Владелец открывает Dataset → `Settings` → `Sharing` и добавляет тех же двух пользователей с правом `Can edit`.
4. В Notebook через `Add Input` подключается именно этот Dataset. Все трое работают с одной версией входных данных и артефактов.
5. После обучения один участник сохраняет Notebook через `Save Version`, а артефакты — новой версией Dataset. В комментарии к версии указываются commit, seed и метрики.

Важно: права Notebook и Dataset независимы. Если открыть только Notebook, участник всё равно может не увидеть приватные входные данные.

## Участники

Заполните реальными Kaggle usernames до приглашения:

```yaml
owner: nezqt52
members:
  - username: <kaggle-username-2>
    role: modeling
  - username: <kaggle-username-3>
    role: data-and-evaluation
```

Не коммитьте сюда email, пароли, `kaggle.json` или API-токены. Для трёх человек достаточно совместного Notebook и Dataset; Kaggle Group можно создать дополнительно, если планируется несколько общих ресурсов.

## Единый workflow

```text
Git: код и notebooks
        ↓
Kaggle Notebook: запуск EDA/обучения на GPU
        ↓
Kaggle Dataset: входные данные + artifact_manifest.json + веса
        ↓
локальный ML service: скачивание выбранной версии и inference
```

Версию Dataset фиксируйте в `.env`:

```bash
KAGGLE_NOTEBOOK_URL=https://www.kaggle.com/code/nezqt52/notebook34755737a1/edit
KAGGLE_DATASET_URL=https://www.kaggle.com/datasets/<owner>/<dataset-slug>
KAGGLE_DATASET_SLUG=<owner>/<dataset-slug>
KAGGLE_ARTIFACT_VERSION=<version-number>
```

Скачивание выбранного набора:

```bash
pip install kaggle
kaggle datasets download -d "$KAGGLE_DATASET_SLUG" \
  -p ml/artifacts --unzip
```

Ключи Kaggle настраиваются локально в `~/.kaggle/kaggle.json` или через переменные CI. На Kaggle Notebook API-токены обычно не нужны для подключённого Dataset.

## Правила работы втроём

- не редактируем один и тот же notebook одновременно без договорённости;
- перед изменением создаём новую Kaggle Notebook version;
- данные не перезаписываем — публикуем новую Dataset version;
- имена версий: `eda-v1`, `catboost-v1`, `torch-v1`, `ensemble-v1`;
- в `artifact_manifest.json` записываем commit, Dataset version, seed, feature list и метрики;
- лучший артефакт выбираем только по зафиксированному validation split.

Подробнее: [Kaggle Notebook collaboration](https://www.kaggle.com/docs/notebooks), [Kaggle Dataset collaboration](https://www.kaggle.com/docs/datasets), [Kaggle Groups](https://www.kaggle.com/docs/groups).
