"""Очистка сырых данных соревнования от артефактов NDTP-телеметрии.

Каждая функция принимает DataFrame ровно как в CSV и возвращает
очищенный DataFrame. Опционально передаётся словарь `report`,
в который записывается счётчик исправлений по каждому правилу —
эти числа попадают в `data/processed/preprocessing_report.json`
и в отчёт README.
"""

from __future__ import annotations

import logging
import re

import pandas as pd

logger = logging.getLogger(__name__)

# Координаты московского полигона с запасом.
MOSCOW_LAT_RANGE = (54.0, 57.0)
MOSCOW_LON_RANGE = (35.0, 40.0)

# Физический предел скорости городского автобуса, км/ч.
SPEED_MAX_KMH = 120.0

# gps_time считается ненадёжным, если расходится с event_time сильнее, сек.
GPS_TRUST_WINDOW_S = 120.0

# Разумный диапазон высот для Москвы, м (0 — sentinel «нет данных»).
ALT_RANGE_M = (50.0, 400.0)

GEOM_PATTERN = re.compile(
    r"POINT\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)"
)


def _parse_geom(geom: pd.Series) -> pd.DataFrame:
    """Разбирает WKT-колонку `POINT (lon lat)` в числа."""
    parsed = geom.str.extract(GEOM_PATTERN)
    parsed.columns = ["stop_lon", "stop_lat"]
    return parsed.apply(pd.to_numeric, errors="coerce")


def preprocess_traffic(
    df: pd.DataFrame,
    report: dict | None = None,
) -> pd.DataFrame:
    """Чистит телеметрию NDTP до состояния, пригодного для фичей.

    Правила:
    1. packet_id нормализуется к строке (в CSV смешанный формат:
       int64 у live-пакетов и "<base>_<seq>" у historical-выгрузок);
       по этому же формату добавляется булева is_archive — режим источника
       виден из самого пакета в момент T, leakage нет.
    2. Точные дубликаты и ретрансляты (одинаковые tr_id+event_time)
       удаляются — иначе ломаются rolling-признаки.
    3. event_time > receive_time (перекос часов устройства) —
       receive_time подтягивается к event_time.
    4. gps_time с расхождением > GPS_TRUST_WINDOW_S обнуляется:
       у historical-пакетов часы устройства переписываются задом.
    5. Координаты (0,0) или вне московского bbox -> NaN; колонка
       coords_valid пересобирается по фактическим координатам,
       потому что location_valid в выгрузке противоречив.
    6. speed вне [0, SPEED_MAX_KMH] -> NaN.
    7. heading приводится по модулю 360 (значение 360 -> 0).
    8. alt вне ALT_RANGE_M (включая sentinel 0 и мусор 65505) -> NaN.
    9. Сортировка по (tr_id, event_time) — обязательна для временных фичей.
    """
    df = df.copy()
    counts: dict[str, int | float] = {"rows_in": len(df)}

    # 1. Смешанный dtype колонки пакетов + режим источника.
    #    packet_id "<base>_<seq>" — архивная выгрузка, int64 — live-приём.
    counts["packet_id_mixed_strings"] = int(
        df["packet_id"].astype(str).str.contains("_").sum()
    )
    df["is_archive"] = df["packet_id"].astype(str).str.contains("_")
    df["packet_id"] = df["packet_id"].astype(str)

    # 2. Дубликаты.
    exact_dupes = int(df.duplicated().sum())
    df = df.drop_duplicates()

    df["event_time"] = pd.to_datetime(df["event_time"], errors="coerce")
    df["receive_time"] = pd.to_datetime(df["receive_time"], errors="coerce")
    df["gps_time"] = pd.to_datetime(df["gps_time"], errors="coerce")

    sort_cols = ["tr_id", "event_time", "receive_time"]
    df = df.sort_values(sort_cols, kind="stable")
    retransmits = int(df.duplicated(["tr_id", "event_time"]).sum())
    df = df.drop_duplicates(["tr_id", "event_time"], keep="first")
    counts["dropped_exact_duplicates"] = exact_dupes
    counts["dropped_retransmit_duplicates"] = retransmits

    # 3. Перекос часов: событие не может быть получено раньше, чем случилось.
    clock_skew = int((df["event_time"] > df["receive_time"]).sum())
    df["receive_time"] = df[["event_time", "receive_time"]].max(axis=1)
    counts["fixed_event_after_receive_clock_skew"] = clock_skew

    # 4. Ненадёжный gps_time.
    gps_lag_s = (df["gps_time"] - df["event_time"]).dt.total_seconds().abs()
    bad_gps = int(((gps_lag_s > GPS_TRUST_WINDOW_S) & df["gps_time"].notna()).sum())
    df.loc[gps_lag_s > GPS_TRUST_WINDOW_S, "gps_time"] = pd.NaT
    counts["nulled_gps_time_outside_window"] = bad_gps

    # 5. Координаты.
    lat = df["lat"]
    lon = df["lon"]
    in_bbox = (
        lat.between(*MOSCOW_LAT_RANGE)
        & lon.between(*MOSCOW_LON_RANGE)
    )
    bad_coords = int(((lat.notna() | lon.notna()) & ~in_bbox.fillna(False)).sum())
    df.loc[~in_bbox, ["lat", "lon"]] = pd.NA
    df["coords_valid"] = df["lat"].notna() & df["lon"].notna()
    counts["nulled_out_of_bbox_coordinates"] = bad_coords
    counts["rows_missing_location"] = int((~df["coords_valid"]).sum())
    counts["location_flag_conflicts"] = int(
        (df["coords_valid"] != df["location_valid"]).sum()
    )

    # 6. Скорость.
    df["speed"] = pd.to_numeric(df["speed"], errors="coerce")
    bad_speed = int(
        ((df["speed"] > SPEED_MAX_KMH) | (df["speed"] < 0)).sum()
    )
    df.loc[(df["speed"] > SPEED_MAX_KMH) | (df["speed"] < 0), "speed"] = pd.NA
    counts["nulled_speed_out_of_range"] = bad_speed

    # 7. Направление: 360 -> 0, вне [0, 360) — артефакт, modulo чинит.
    raw_heading = pd.to_numeric(df["heading"], errors="coerce")
    counts["wrapped_heading_360"] = int((raw_heading == 360).sum())
    df["heading"] = raw_heading % 360

    # 8. Высота: 0 — датчик молчит, 65505 — переполнение uint16.
    df["alt"] = pd.to_numeric(df["alt"], errors="coerce")
    bad_alt = int(
        df["alt"].notna().sum()
        - df["alt"].between(*ALT_RANGE_M).sum()
    )
    df.loc[~df["alt"].between(*ALT_RANGE_M), "alt"] = pd.NA
    counts["nulled_altitude_out_of_range"] = bad_alt

    # device_event_id во всей выгрузке нулевой — признаков не даёт, удаляем.
    counts["device_event_id_dropped_as_constant"] = int(
        (df["device_event_id"] != 0).sum() == 0
    )
    df = df.drop(columns=["device_event_id"])

    df = df.reset_index(drop=True)
    counts["rows_out"] = len(df)

    counts["missing_after"] = {
        column: round(float(df[column].isna().mean()), 3)
        for column in ["lat", "lon", "speed", "gps_time"]
    }
    counts["archive_rows_after_clean"] = int(df["is_archive"].sum())
    counts["tr_id_count"] = int(df["tr_id"].nunique())
    counts["event_time_min"] = str(df["event_time"].min())
    counts["event_time_max"] = str(df["event_time"].max())

    if report is not None:
        report.update(counts)
    logger.info("Traffic cleaned: %s -> %s rows", counts["rows_in"], len(df))
    return df


def preprocess_schedule(
    df: pd.DataFrame,
    report: dict | None = None,
) -> pd.DataFrame:
    """Чистит расписание: WKT -> числа, datetime, фактическое отклонение.

    Правила:
    1. Дубликаты строк и повторные tt_action_item_id удаляются.
    2. geom разбирается в stop_lon/stop_lat.
    3. time_begin/time_fact_begin приводятся к datetime
       (в train-выгрузке наносекундный формат без разделителя).
    4. dev_s = time_fact_begin - time_begin (если факт есть) — целевая
       величина на уровне остановки, совпадает по смыслу с target_delay_s.
    5. manual_fill -> bool, building_address -> заполненный placeholder.
    """
    df = df.copy()
    counts: dict[str, int | float] = {"rows_in": len(df)}

    df = df.drop_duplicates()
    dup_ids = int(df.duplicated("tt_action_item_id").sum())
    df = df.drop_duplicates("tt_action_item_id", keep="first")
    counts["dropped_duplicate_action_items"] = dup_ids

    for column in ["time_begin", "time_fact_begin"]:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")

    geom = _parse_geom(df["geom"].astype(str))
    counts["unparsed_geom"] = int(geom["stop_lon"].isna().sum())
    df[["stop_lon", "stop_lat"]] = geom

    if "time_fact_begin" in df.columns:
        df["dev_s"] = (
            (df["time_fact_begin"] - df["time_begin"])
            .dt.total_seconds()
        )
        counts["schedule_dev_s_gt_30min"] = int(
            (df["dev_s"].abs() > 1800).sum()
        )
        # Стоп-факт дальше 30 минут от плана — это сдвиг рейса, а не опоздание.
        df.loc[df["dev_s"].abs() > 1800, "dev_s"] = pd.NA
    else:
        df["dev_s"] = pd.NA

    if "manual_fill" in df.columns:
        df["manual_fill"] = (
            df["manual_fill"].astype(str).str.lower().eq("true")
        )
    if "building_address" in df.columns:
        counts["missing_building_address"] = int(
            df["building_address"].isna().sum()
        )
        df["building_address"] = df["building_address"].fillna("")

    df = df.sort_values(["tr_id", "time_begin"], kind="stable")
    df = df.reset_index(drop=True)
    counts["rows_out"] = len(df)

    if report is not None:
        report.update(counts)
    return df


def preprocess_labels(
    df: pd.DataFrame,
    report: dict | None = None,
) -> pd.DataFrame:
    """Чистит метки и проверяет контракт горизонта (T+10; T+15] минут.

    Правила:
    1. Точные дубликаты и повторные sample_id удаляются.
    2. target_delay_s числовая; строки без target выбрасываются.
    3. Горизонт прогноза проверяется и пишется в report как нарушение
       контракта соревнования (исправлять нечем — только отбраковка).
    """
    df = df.copy()
    counts: dict[str, int | float] = {"rows_in": len(df)}

    df = df.drop_duplicates()
    dup_ids = int(df.duplicated("sample_id").sum())
    df = df.drop_duplicates("sample_id", keep="first")
    counts["dropped_duplicate_samples"] = dup_ids

    for column in ["T", "target_time_begin"]:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
    for column in ["cur_dev_s", "target_delay_s"]:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")

    counts["dropped_missing_target"] = int(df["target_delay_s"].isna().sum())
    df = df.dropna(subset=["target_delay_s"])

    horizon_min = (
        (df["target_time_begin"] - df["T"]).dt.total_seconds() / 60.0
    )
    counts["horizon_violations"] = int(
        ((horizon_min <= 10) | (horizon_min > 15)).sum()
    )

    counts["target_delay_min"] = float(df["target_delay_s"].min())
    counts["target_delay_max"] = float(df["target_delay_s"].max())
    counts["target"] = {
        "mean": round(float(df["target_delay_s"].mean()), 2),
        "median": float(df["target_delay_s"].median()),
        "std": round(float(df["target_delay_s"].std()), 2),
    }

    df = df.sort_values(["tr_id", "T"], kind="stable")
    df = df.reset_index(drop=True)
    counts["rows_out"] = len(df)

    if report is not None:
        report.update(counts)
    return df


def preprocess_points(
    df: pd.DataFrame,
    report: dict | None = None,
) -> pd.DataFrame:
    """Чистит validate-точки (схема как у labels, но без target_delay_s)."""
    df = df.copy()
    counts: dict[str, int | float] = {"rows_in": len(df)}

    df = df.drop_duplicates()
    dup_ids = int(df.duplicated("sample_id").sum())
    df = df.drop_duplicates("sample_id", keep="first")
    counts["dropped_duplicate_samples"] = dup_ids

    for column in ["T", "target_time_begin"]:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
    if "cur_dev_s" in df.columns:
        df["cur_dev_s"] = pd.to_numeric(df["cur_dev_s"], errors="coerce")

    df = df.sort_values(["tr_id", "T"], kind="stable")
    df = df.reset_index(drop=True)
    counts["rows_out"] = len(df)

    if report is not None:
        report.update(counts)
    return df
