"""Пргон preprocessing над всеми сырыми данными соревнования.

Читает `data/raw`, пишет очищенные таблицы в `data/processed`
и счётчики исправлений в `data/processed/preprocessing_report.json`.

Запуск из корня репозитория:

    python scripts/preprocess_data.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ml"))

from src.preprocessing import (  # noqa: E402
    preprocess_labels,
    preprocess_points,
    preprocess_schedule,
    preprocess_traffic,
)

RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"


def run() -> None:
    """Обрабатывает все датасеты и сохраняет результат + отчёт."""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    report: dict[str, dict] = {}

    jobs = [
        ("train_traffic", RAW / "train" / "traffic.csv", preprocess_traffic),
        ("test_traffic", RAW / "test" / "traffic.csv", preprocess_traffic),
        ("train_schedule", RAW / "train" / "schedule.csv", preprocess_schedule),
        ("test_schedule", RAW / "test" / "schedule.csv", preprocess_schedule),
        ("validate_schedule_plan", RAW / "validate" / "schedule_plan.csv", preprocess_schedule),
        ("labels_train", RAW / "labels" / "labels_train.csv", preprocess_labels),
        ("labels_test", RAW / "labels" / "labels_test.csv", preprocess_labels),
        ("validate_points", RAW / "validate" / "points.csv", preprocess_points),
    ]

    for name, path, handler in jobs:
        df = pd.read_csv(path, low_memory=False)
        cleaned_report: dict = {}
        cleaned = handler(df, report=cleaned_report)
        cleaned.to_csv(PROCESSED / f"{name}.csv", index=False)
        report[name] = cleaned_report
        print(
            f"{name}: {cleaned_report['rows_in']} -> {len(cleaned)} строк"
        )

    # validate/traffic.csv побайтово равен test/traffic.csv —
    # отдельный файл не пишем, чтобы не плодить копию.
    report["notes"] = {
        "validate_traffic_equals_test_traffic": True,
        "gps_time_asymmetry": (
            "Расхождение gps_time > 120 с существует только в архивных "
            "пакетах train (packet_id вида '<base>_<seq>', 181 904 строк, "
            "часы устройства переписаны при выгрузке, максимум ±2042 с). "
            "В live-пакетах gps_time совпадает с event_time посекундно, "
            "а в test архивных пакетов нет — поэтому в test зануление "
            "gps_time не срабатывает ни разу."
        ),
    }

    out = PROCESSED / "preprocessing_report.json"
    out.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\nОтчёт: {out}")


if __name__ == "__main__":
    run()
