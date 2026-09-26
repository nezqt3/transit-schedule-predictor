# ML-контур

Выбранная конкурсная и демонстрационная модель — пара LightGBM (прямой и
остаточный регрессоры), версия `lightgbm-plan-2026-09-26`. Выход `prediction`
означает `target_delay_s` в секундах. Дополнительно сервис возвращает
калиброванную вероятность `p_late` для `target_delay_s >= 120 с`. На 353
размеченных test-точках локальная MAE выбранной модели **58,6033 с**, baseline
`cur_dev_s` — **93,3598 с**. По сообщению команды score 1 на платформе для
LightGBM равен **1 (максимум)**; подтверждающий скрин/ссылка конкретной
отправки пока не приложены.

`service.main` предоставляет `GET /health` и `POST /predict`. При старте
проверяются хеши весов, метаданных, калибровки и планового расписания из
`artifacts/release_manifest.json`. Отсутствующий/повреждённый артефакт
останавливает загрузку; baseline выбирается только явно через
`MODEL_NAME=baseline`.

## Обучение и воспроизведение релиза

Из корня репозитория:

```bash
python scripts/exp_lightgbm_plan.py --release
python scripts/train_risk_calibration.py
python scripts/freeze_release.py
python scripts/verify_submission.py
python scripts/verify_model_parity.py
python scripts/evaluate_risk_policy.py
```

`--release` обучает выбранную пару и генерирует чистый LightGBM CSV без
Torch-артефакта. `freeze_release.py` пересчитывает SHA-256 и проверяет, что
калибровка обучена для текущих весов; при новом релизе прежний официальный
балл сбрасывается. Остальные CatBoost/PyTorch файлы и скрипты в репозитории —
отдельные эксперименты и не входят в текущий inference Docker.

`src.features_simple` и `src.plan_features` используются и офлайн, и в
сервисе. Читаются только плановые поля расписания. В окне телеметрии
разрешены лишь `event_time <= T` и `receive_time <= T`, если время получения
известно. Naive timestamp CSV интерпретируется как `SOURCE_TIMEZONE`.
Тестовые метки нужны только для локальной оценки, а не для работающего ML API.

Локальные тесты: `cd ml && python -m pytest -q`. Инструкция по запуску всего
стека: [`ЗАПУСК.md`](../ЗАПУСК.md).
