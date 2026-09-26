# Артефакты выбранной модели

`release_manifest.json` фиксирует версию, локальные MAE, команду обучения,
хеш конкурсного CSV и SHA-256 всех входов inference. Для выбранного
`lightgbm_plan` нужны `lightgbm_plan_direct.txt`,
`lightgbm_plan_residual.txt`, `lightgbm_plan_metadata.json`,
`risk_calibration.json` и `data/raw/validate/schedule_plan.csv`.

ML-контейнер копирует только перечисленные файлы весов и проверяет их при
старте. Веса небольшой выбранной модели включены в этот checkout; большие
экспериментальные артефакты остаются вне Git. Официальный результат скрытого
validate находится в `official_platform_score`. Значение `1.0` сообщено
командой как максимальный `score 1` для LightGBM; до приложения ссылки или
скрина отправки связь результата с конкретным хешем CSV не подтверждена.

Повторная фиксация после обучения из корня проекта:

```bash
python scripts/exp_lightgbm_plan.py --release
python scripts/train_risk_calibration.py
python scripts/freeze_release.py
python scripts/verify_submission.py
python scripts/verify_model_parity.py
```

`--release` генерирует чистый LightGBM CSV без обязательного Torch-артефакта.
`freeze_release.py` откажется фиксировать калибровку от другой версии весов и
сбрасывает прежний официальный балл, если формируется новый релиз.
