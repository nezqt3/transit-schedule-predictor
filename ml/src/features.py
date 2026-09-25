"""Построение ML-признаков из очищенной телеметрии и расписания.

Единая реализация для train и inference: признаки считаются только по
пакетам с `event_time <= T`, данные после точки прогноза не читаются.

Вход — таблицы после `ml/src/preprocessing.py`:
traffic (с колонками event_time/speed/lat/lon/heading/is_archive),
labels (tr_id, T, target_stop_id, target_time_begin, cur_dev_s),
stops (tt_action_item_id -> stop_lat/stop_lon).
"""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd

SPEED_WINDOWS_S = (60, 180, 300)

EARTH_RADIUS_M = 6_371_000.0

# Сетка сегментов ~500 м (по широте) для окружения ТС.
CELL_LAT_DEG = 0.0045
CELL_LON_DEG = 0.0065
CELL_NONE = np.int64(-1 << 62)

# Минимальный знаменатель для speed-ratio признаков (км/ч).
SPEED_EPS = 3.0


def haversine_m(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Расстояние между точками, метры; NaN если координат нет."""
    if np.isnan([lat1, lon1, lat2, lon2]).any():
        return float("nan")
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    dp = p2 - p1
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return float(2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a)))


def _vehicle_arrays(group: pd.DataFrame) -> dict[str, np.ndarray]:
    """Сортированные по времени массивы одного ТС с cumsum для окон."""
    group = group.sort_values("event_time", kind="stable")
    times = group["event_time"].values.astype("datetime64[s]").astype(np.int64)
    speed = pd.to_numeric(group["speed"], errors="coerce").to_numpy(float)
    valid = ~np.isnan(speed)
    speed_filled = np.where(valid, speed, 0.0)
    lat = pd.to_numeric(group["lat"], errors="coerce").to_numpy(float)
    lon = pd.to_numeric(group["lon"], errors="coerce").to_numpy(float)
    return {
        "times": times,
        "speed": speed,
        "lat": lat,
        "lon": lon,
        "heading": pd.to_numeric(group["heading"], errors="coerce").to_numpy(float),
        "is_archive": group["is_archive"].astype(int).to_numpy(),
        "cells": group["_cell"].to_numpy(np.int64),
        "sum_speed": np.concatenate([[0.0], np.cumsum(speed_filled)]),
        "sum_speed2": np.concatenate([[0.0], np.cumsum(speed_filled**2)]),
        "sum_archive": np.concatenate(
            [[0.0], np.cumsum(group["is_archive"].astype(float).to_numpy())]
        ),
        "sum_valid": np.concatenate([[0.0], np.cumsum(valid.astype(float))]),
        "sum_stopped": np.concatenate(
            [[0.0], np.cumsum((valid & (speed <= 1.0)).astype(float))]
        ),
        # Накопленная траекторная дистанция: пары без валидных координат дают 0.
        "cum_dist": np.concatenate(
            [[0.0], np.cumsum(_pair_distances_m(lat, lon))]
        ),
        # Ускорение в км/ч/мин по соседним пакетам; мусор/пропуски -> NaN.
        "accel": _acceleration_kmh_min(times, speed),
    }


def _acceleration_kmh_min(times: np.ndarray, speed: np.ndarray) -> np.ndarray:
    dt = np.diff(times).astype(float)
    ds = np.diff(speed)
    with np.errstate(divide="ignore", invalid="ignore"):
        acc = np.where(dt > 0, ds / dt * 60.0, np.nan)
    return acc


def _pair_distances_m(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Векторный haversine между последовательными точками трека."""
    if len(lat) < 2:
        return np.zeros(0)
    p = np.radians(lat)
    lam = np.radians(lon)
    dphi = np.diff(p)
    dlam = np.diff(lam)
    a = (
        np.sin(dphi / 2) ** 2
        + np.cos(p[:-1]) * np.cos(p[1:]) * np.sin(dlam / 2) ** 2
    )
    dist = 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0, 1)))
    both_valid = ~(
        np.isnan(lat[:-1]) | np.isnan(lat[1:]) | np.isnan(lon[:-1]) | np.isnan(lon[1:])
    )
    return np.where(both_valid, dist, 0.0)


def _window_stats(arr: dict, lo: int, hi: int) -> tuple[float, float, int]:
    """(mean, std, n_valid) скорости на полуинтервале [lo, hi)."""
    n_valid = arr["sum_valid"][hi] - arr["sum_valid"][lo]
    if n_valid == 0:
        return float("nan"), float("nan"), 0
    mean = (arr["sum_speed"][hi] - arr["sum_speed"][lo]) / n_valid
    mean2 = (arr["sum_speed2"][hi] - arr["sum_speed2"][lo]) / n_valid
    var = max(mean2 - mean**2, 0.0)
    return mean, float(np.sqrt(var)), int(n_valid)


def _cell_ids(lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """Код ячейки сетки для каждой точки; без координат — sentinel."""
    with np.errstate(invalid="ignore"):
        ix = np.floor(np.where(np.isnan(lat), -1e9, lat) / CELL_LAT_DEG)
        iy = np.floor(np.where(np.isnan(lon), -1e9, lon) / CELL_LON_DEG)
    valid = ~np.isnan(lat) & ~np.isnan(lon)
    cells = np.where(
        valid,
        ix.astype(np.int64) * 100_000 + iy.astype(np.int64),
        CELL_NONE,
    )
    return cells


def _segment_index(traffic: pd.DataFrame) -> dict[int, dict]:
    """Накапливает по каждой ячейке сетки сортированные по времени массивы ТС-окружения."""
    frames: dict[int, dict] = {}
    subset = traffic[traffic["_cell"] != CELL_NONE]
    for cell, group in subset.groupby("_cell", sort=False):
        group = group.sort_values("event_time", kind="stable")
        times = group["event_time"].values.astype("datetime64[s]").astype(np.int64)
        speed = pd.to_numeric(group["speed"], errors="coerce").to_numpy(float)
        valid = ~np.isnan(speed)
        frames[int(cell)] = {
            "times": times,
            "speed": speed,
            "unit": group["unit_id"].to_numpy(),
            "sum_speed": np.concatenate([[0.0], np.cumsum(np.where(valid, speed, 0.0))]),
            "sum_valid": np.concatenate([[0.0], np.cumsum(valid.astype(float))]),
        }
    return frames


def _segment_features(
    arr: dict,
    last: int,
    t_s: int,
    segments: dict[int, dict],
) -> dict:
    """Статистика по ячейке сетки, где сейчас ТС: только пакеты с event_time <= T."""
    cell = int(arr["cells"][last])
    seg = segments.get(cell)
    if seg is None:
        return {}

    hi = int(np.searchsorted(seg["times"], t_s, side="right"))
    lo = int(np.searchsorted(seg["times"], t_s - 300, side="left"))
    out: dict[str, float] = {}

    speeds = seg["speed"][lo:hi]
    valid = ~np.isnan(speeds)
    if valid.any():
        out["segment_speed_mean_5m"] = float(speeds[valid].mean())
        out["segment_speed_median_5m"] = float(np.median(speeds[valid]))
        out["segment_stopped_ratio_5m"] = float((speeds[valid] <= 1.0).mean())
    out["segment_vehicle_count_5m"] = float(len(np.unique(seg["unit"][lo:hi])))

    n_hist = seg["sum_valid"][hi]
    if n_hist > 0:
        out["historical_segment_speed"] = float(seg["sum_speed"][hi] / n_hist)
    return out


def _slope_kmh_min(times: np.ndarray, speed: np.ndarray) -> float:
    """Наклон скорости (км/ч за минуту) по методу наименьших квадратов."""
    mask = ~np.isnan(speed)
    if mask.sum() < 3:
        return float("nan")
    t = (times[mask].astype(float) - times[mask][0]) / 60.0
    var_t = float(np.var(t))
    if var_t == 0.0:
        return float("nan")
    return float(np.cov(t, speed[mask], bias=True)[0, 1] / var_t)


def _network_arrays(traffic: pd.DataFrame) -> dict:
    """Отсортированные по времени массивы всей сети для forward-сигналов."""
    sub = traffic.sort_values("event_time", kind="stable")
    return {
        "times": sub["event_time"].values.astype("datetime64[s]").astype(np.int64),
        "lat": pd.to_numeric(sub["lat"], errors="coerce").to_numpy(float),
        "lon": pd.to_numeric(sub["lon"], errors="coerce").to_numpy(float),
        "speed": pd.to_numeric(sub["speed"], errors="coerce").to_numpy(float),
        "unit": sub["unit_id"].to_numpy(),
    }


def _ahead_features(
    lat0: float,
    lon0: float,
    lat_b: float,
    lon_b: float,
    t_s: int,
    net: dict,
    window_s: int = 300,
    corridor_m: float = 250.0,
    slow_kmh: float = 5.0,
) -> dict:
    """Что происходит в коридоре «наше ТС -> целевая остановка» по чужим ТС.

    Чужие точки за последние window_s секунд (event_time <= T) проецируются на
    отрезок A->B; в коридор берутся точки строго впереди (0 < t <= 1) не дальше
    corridor_m от линии. Трети отрезка = сегменты next/next2/next3.
    """
    if np.isnan([lat0, lon0, lat_b, lon_b]).any():
        return {}

    hi = int(np.searchsorted(net["times"], t_s, side="right"))
    lo = int(np.searchsorted(net["times"], t_s - window_s, side="left"))
    if hi - lo == 0:
        return {}

    mx = 111_320.0 * np.cos(np.radians(lat0))
    my = 110_540.0
    vx, vy = (lon_b - lon0) * mx, (lat_b - lat0) * my
    length2 = vx * vx + vy * vy
    if length2 < 1.0:
        return {}
    length = np.sqrt(length2)

    px = (net["lon"][lo:hi] - lon0) * mx
    py = (net["lat"][lo:hi] - lat0) * my
    proj = (px * vx + py * vy) / length2
    lateral = np.abs(px * vy - py * vx) / length
    speed = net["speed"][lo:hi]

    ahead = (
        (proj > 0.0)
        & (proj <= 1.0)
        & (lateral <= corridor_m)
        & ~np.isnan(speed)
    )
    if not ahead.any():
        return {
            "vehicles_ahead_count": 0.0,
            "distance_to_slow_traffic_m": float("nan"),
        }

    out: dict[str, float] = {}
    p, s = proj[ahead], speed[ahead]
    units = net["unit"][lo:hi][ahead]

    out["vehicles_ahead_count"] = float(len(np.unique(units)))
    out["vehicles_ahead_mean_speed"] = float(s.mean())
    out["vehicles_ahead_min_speed"] = float(s.min())
    out["vehicles_ahead_stopped_ratio"] = float((s <= 1.0).mean())

    for name, (a, b) in {
        "next_segment": (0.0, 1 / 3),
        "next_2_segments": (0.0, 2 / 3),
        "next_3_segments": (0.0, 1.0),
    }.items():
        m = (p > a) & (p <= b)
        out[f"{name}_speed_mean"] = float(s[m].mean()) if m.any() else float("nan")
    m1 = (p > 0.0) & (p <= 1 / 3)
    out["next_segment_stopped_ratio"] = (
        float((s[m1] <= 1.0).mean()) if m1.any() else float("nan")
    )
    out["next_segment_congestion_ratio"] = (
        float((s[m1] < slow_kmh).mean()) if m1.any() else float("nan")
    )

    slow = (s < slow_kmh) & (p > 0.0)
    if slow.any():
        d_slow = np.sqrt(px[ahead][slow] ** 2 + py[ahead][slow] ** 2).min()
        out["distance_to_slow_traffic_m"] = float(d_slow)
    else:
        out["distance_to_slow_traffic_m"] = float("nan")
    return out


def build_features(
    traffic: pd.DataFrame,
    labels: pd.DataFrame,
    stops: pd.DataFrame,
) -> pd.DataFrame:
    """Собирает по строке признаков на каждый sample из labels.

    Все окна берутся по `event_time <= T`. Скоростные окна — 1/3/5 минут.
    """
    traffic = traffic.copy()
    traffic["event_time"] = pd.to_datetime(traffic["event_time"])
    traffic["_cell"] = _cell_ids(
        pd.to_numeric(traffic["lat"], errors="coerce").to_numpy(float),
        pd.to_numeric(traffic["lon"], errors="coerce").to_numpy(float),
    )

    by_vehicle = {
        tr_id: _vehicle_arrays(group)
        for tr_id, group in traffic.groupby("tr_id", sort=False)
    }
    segments = _segment_index(traffic)
    net = _network_arrays(traffic)

    rows: list[dict] = []

    for sample in labels.itertuples(index=False):
        arr = by_vehicle.get(sample.tr_id)
        row: dict = {
            "sample_id": sample.sample_id,
            "tr_id": str(sample.tr_id),
            "T": sample.T,
            "cur_dev_s": sample.cur_dev_s,
        }
        if "target_delay_s" in labels.columns:
            row["target_delay_s"] = sample.target_delay_s

        ttts_s = (sample.target_time_begin - sample.T).total_seconds()
        row["time_to_stop_s"] = ttts_s
        row["hour_of_day"] = sample.T.hour + sample.T.minute / 60

        t_s = int(np.datetime64(sample.T, "s").astype(np.int64))

        if arr is None:
            rows.append(row)
            continue

        hi = int(np.searchsorted(arr["times"], t_s, side="right"))
        last = hi - 1

        if last >= 0:
            row["current_speed"] = arr["speed"][last]
            row["last_heading"] = arr["heading"][last]
            row["gap_since_last_pkt_s"] = (t_s - arr["times"][last]) / 1.0
            row["is_archive_last"] = arr["is_archive"][last]
            row["dist_to_stop_m"] = haversine_m(
                arr["lat"][last],
                arr["lon"][last],
                stops.at[sample.target_stop_id, "stop_lat"],
                stops.at[sample.target_stop_id, "stop_lon"],
            )
            # «успевает ли ТС физически»: нужная средняя скорость до остановки
            # и запас/недобор относительно текущей.
            required_kmh = (
                row["dist_to_stop_m"] / max(ttts_s, 1.0) * 3.6
                if not np.isnan(row["dist_to_stop_m"])
                else float("nan")
            )
            row["required_speed_kmh"] = required_kmh
            cur = row["current_speed"]
            row["speed_vs_required_kmh"] = (
                cur - required_kmh if not np.isnan(cur) else float("nan")
            )
            row.update(_segment_features(arr, last, t_s, segments))
            row.update(
                _ahead_features(
                    arr["lat"][last],
                    arr["lon"][last],
                    stops.at[sample.target_stop_id, "stop_lat"],
                    stops.at[sample.target_stop_id, "stop_lon"],
                    t_s,
                    net,
                )
            )

        row["cur_dev_per_time_to_stop"] = sample.cur_dev_s / max(ttts_s, 1.0)

        window_means: dict[int, float] = {}
        for window in SPEED_WINDOWS_S:
            lo = int(np.searchsorted(arr["times"], t_s - window, side="left"))
            suffix = window // 60
            mean, std, n_valid = _window_stats(arr, lo, hi)
            window_means[window] = mean
            row[f"speed_mean_{suffix}m"] = mean
            row[f"speed_std_{suffix}m"] = std
            row[f"speed_n_{suffix}m"] = n_valid
            row[f"packets_{suffix}m"] = hi - lo

            # Дельта = средняя за вторую половину окна минус первая половина.
            mid = int(np.searchsorted(arr["times"], t_s - window / 2, side="left"))
            first, _, n_first = _window_stats(arr, lo, mid)
            second, _, n_second = _window_stats(arr, mid, hi)
            row[f"speed_delta_{suffix}m"] = second - first

            if n_valid > 0:
                stopped = arr["sum_stopped"][hi] - arr["sum_stopped"][lo]
                row[f"stopped_ratio_{suffix}m"] = stopped / n_valid
            else:
                row[f"stopped_ratio_{suffix}m"] = float("nan")

            # Пройденная дистанция: суммы парных шагов [lo, hi).
            d_hi = arr["cum_dist"][max(hi - 1, lo)]
            d_lo = arr["cum_dist"][lo]
            row[f"distance_travelled_{suffix}m"] = (
                d_hi - d_lo if hi - lo >= 2 else float("nan")
            )

        m1, m5 = window_means[60], window_means[300]
        if not (np.isnan(m1) or np.isnan(m5)):
            row["speed_trend_1m_5m"] = m1 - m5

        # Precursor-динамика: короткие окна + наклон + ускорения.
        m3 = window_means[180]
        lo30 = int(np.searchsorted(arr["times"], t_s - 30, side="left"))
        m30, _, n30 = _window_stats(arr, lo30, hi)
        row["speed_mean_30s"] = m30
        if not np.isnan(m5):
            if not np.isnan(m30):
                row["speed_ratio_30s_5m"] = m30 / max(m5, SPEED_EPS)
                row["speed_drop_30s"] = m5 - m30
            if not np.isnan(m1):
                row["speed_ratio_1m_5m"] = m1 / max(m5, SPEED_EPS)
                row["speed_drop_1m"] = m5 - m1
            if not np.isnan(m3):
                row["speed_drop_3m"] = m5 - m3

        for suffix, window in (("1m", 60), ("3m", 180)):
            lo_w = int(np.searchsorted(arr["times"], t_s - window, side="left"))
            row[f"speed_trend_{suffix}"] = _slope_kmh_min(
                arr["times"][lo_w:hi], arr["speed"][lo_w:hi]
            )
            # accel[i] — между пакетами i и i+1; окно [lo_w, hi) -> индексы lo_w..hi-2.
            acc = arr["accel"][lo_w : hi - 1]
            acc = acc[~np.isnan(acc)]
            if len(acc) > 0:
                row[f"acceleration_mean_{suffix}"] = float(acc.mean())
                if suffix == "1m":
                    row["acceleration_min_1m"] = float(acc.min())

        seg5 = row.get("segment_speed_mean_5m", float("nan"))
        hist = row.get("historical_segment_speed", float("nan"))
        cur = row.get("current_speed", float("nan"))
        req = row.get("required_speed_kmh", float("nan"))

        if not np.isnan(cur) and not np.isnan(seg5):
            row["vehicle_vs_segment_5m"] = cur / max(seg5, SPEED_EPS)
        if not np.isnan(m1) and not np.isnan(seg5):
            row["speed_deficit_mean_1m"] = m1 - req if not np.isnan(req) else float("nan")
            row["speed_deficit_mean_3m"] = m3 - req if not np.isnan(m3) and not np.isnan(req) else float("nan")
            row["segment_vs_historical_5m"] = (
                seg5 / max(hist, SPEED_EPS) if not np.isnan(hist) else float("nan")
            )
        if not np.isnan(req) and not np.isnan(seg5):
            # «успевает ли»: нужна скорость против фактической скорости участка.
            row["schedule_pressure"] = req / max(seg5, SPEED_EPS)
        if not np.isnan(req) and not np.isnan(hist):
            row["required_vs_historical"] = req / max(hist, SPEED_EPS)

        n_pkt_5m = max(hi - lo, 1)
        row["archive_frac_5m"] = (
            (arr["sum_archive"][hi] - arr["sum_archive"][lo]) / n_pkt_5m
        )

        rows.append(row)

    return pd.DataFrame(rows)


def make_stops_lookup(*schedule_frames: pd.DataFrame) -> pd.DataFrame:
    """Индекс остановок tt_action_item_id -> stop_lat/stop_lon по расписаниям."""
    stops = pd.concat(schedule_frames)[
        ["tt_action_item_id", "stop_lat", "stop_lon"]
    ].drop_duplicates("tt_action_item_id")
    return stops.set_index("tt_action_item_id")


# This compact feature contract is shared by the offline builder and the
# real-time inference service. Existing experimental build_features remains
# available for the notebooks and comparison runs.
POINT_FEATURE_COLUMNS = [
    "cur_dev_s", "dist_to_target_m", "time_to_target_plan_s",
    "required_speed_kmh", "speed_last_kmh", "speed_mean_1m",
    "speed_mean_3m", "speed_mean_5m", "speed_p90_5m",
    "speed_std_5m", "idle_ratio_5m", "speed_to_required_ratio",
    "speed_mean_to_required_ratio", "hour_of_day", "day_of_week",
    "hour_sin", "hour_cos", "last_lat", "last_lon", "last_heading",
    "telemetry_age_s", "points_5m", "points_15m",
]


def extract_features_for_point(
    telemetry_df_or_points: pd.DataFrame | list[dict],
    target_stop_info: dict,
    cur_dev_s: float,
    T: str | pd.Timestamp,
) -> dict[str, float]:
    """Extract a causal, 15-minute telemetry window for one prediction point.

    Args:
        telemetry_df_or_points: One vehicle's telemetry, with event_time and
            location_valid. If receive_time exists, it must also be at or before T.
        target_stop_info: stop_lat, stop_lon, and target_time_begin.
        cur_dev_s: Current schedule deviation in seconds.
        T: Prediction timestamp.

    Returns:
        A fixed numeric feature mapping suitable for training and inference.
    """
    t = pd.Timestamp(T)
    target_time = pd.Timestamp(target_stop_info["target_time_begin"])
    if t.tzinfo is not None:
        t = t.tz_convert("UTC").tz_localize(None)
    if target_time.tzinfo is not None:
        target_time = target_time.tz_convert("UTC").tz_localize(None)
    horizon_s = float((target_time - t).total_seconds())
    hour = t.hour + t.minute / 60 + t.second / 3600
    out = {name: float("nan") for name in POINT_FEATURE_COLUMNS}
    out.update(
        cur_dev_s=float(cur_dev_s),
        time_to_target_plan_s=horizon_s,
        hour_of_day=hour,
        day_of_week=float(t.dayofweek),
        hour_sin=float(np.sin(2 * np.pi * hour / 24)),
        hour_cos=float(np.cos(2 * np.pi * hour / 24)),
        points_5m=0.0,
        points_15m=0.0,
    )

    if isinstance(telemetry_df_or_points, pd.DataFrame):
        columns = set(telemetry_df_or_points.columns)
        records = telemetry_df_or_points.to_dict("records")
    else:
        records = telemetry_df_or_points
        columns = set().union(*(record.keys() for record in records)) if records else set()
    if not records:
        return out
    required = {"event_time", "location_valid", "lat", "lon"}
    missing = required - columns
    if missing:
        raise ValueError(f"telemetry missing columns: {sorted(missing)}")

    def event_datetime(value) -> datetime | None:
        if value is None or pd.isna(value):
            return None
        dt = value if isinstance(value, datetime) else pd.Timestamp(value).to_pydatetime()
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt

    def numeric(value) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float("nan")

    t_naive = t.to_pydatetime()
    start = (t - pd.Timedelta(minutes=15)).to_pydatetime()
    has_receive_time = "receive_time" in columns
    window: list[tuple[datetime, float, float, float, float]] = []
    for record in records:
        valid = str(record.get("location_valid", False)).lower() in ("true", "1")
        if not valid:
            continue
        event_time = event_datetime(record.get("event_time"))
        if event_time is None or not start <= event_time <= t_naive:
            continue
        if has_receive_time:
            received = event_datetime(record.get("receive_time"))
            if received is None or received > t_naive:
                continue
        lat = numeric(record.get("lat"))
        lon = numeric(record.get("lon"))
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
            continue
        speed = numeric(record.get("speed"))
        if not 0 <= speed <= 120:
            speed = float("nan")
        window.append((event_time, lat, lon, speed, numeric(record.get("heading"))))
    if not window:
        return out
    window.sort(key=lambda point: point[0])
    last = window[-1]
    stop_lat = float(target_stop_info["stop_lat"])
    stop_lon = float(target_stop_info["stop_lon"])
    distance = haversine_m(last[1], last[2], stop_lat, stop_lon)
    required_kmh = distance / horizon_s * 3.6 if horizon_s > 0 else float("nan")
    out.update(
        dist_to_target_m=distance,
        required_speed_kmh=required_kmh,
        speed_last_kmh=last[3],
        last_lat=last[1],
        last_lon=last[2],
        last_heading=last[4],
        telemetry_age_s=float((t_naive - last[0]).total_seconds()),
        points_15m=float(len(window)),
    )
    for minutes in (1, 3, 5):
        cutoff = (t - pd.Timedelta(minutes=minutes)).to_pydatetime()
        recent = [point for point in window if point[0] >= cutoff]
        speeds = np.array([point[3] for point in recent if np.isfinite(point[3])])
        out[f"speed_mean_{minutes}m"] = float(speeds.mean()) if len(speeds) else float("nan")
        if minutes == 5:
            out["points_5m"] = float(len(recent))
            if len(speeds):
                out["speed_p90_5m"] = float(np.quantile(speeds, 0.9))
                out["speed_std_5m"] = float(speeds.std(ddof=0))
                out["idle_ratio_5m"] = float((speeds < 3).mean())
    if np.isfinite(required_kmh):
        denominator = max(required_kmh, 1.0)
        out["speed_to_required_ratio"] = out["speed_last_kmh"] / denominator
        out["speed_mean_to_required_ratio"] = out["speed_mean_5m"] / denominator
    return out
