"""Leakage-safe tabular features for CatBoost training and inference."""

from __future__ import annotations

import numpy as np
import pandas as pd


FEATURE_COLUMNS = [
    "tr_id", "cur_dev_s", "time_to_target_s", "hour", "day_of_week",
    "target_lon", "target_lat", "last_lon", "last_lat", "last_speed",
    "last_heading", "telemetry_age_s", "speed_mean_1m", "speed_mean_3m",
    "speed_mean_5m", "speed_std_5m", "idle_ratio_5m", "location_count_5m",
    "distance_to_target_m", "movement_5m_m",
]
CAT_FEATURES = ["tr_id"]


def _distance_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate great-circle distance between two WGS84 coordinates."""
    coords = np.array([lon1, lat1, lon2, lat2], dtype=float)
    if not np.isfinite(coords).all():
        return np.nan
    x1, y1, x2, y2 = np.radians(coords)
    dy = y2 - y1
    dx = x2 - x1
    a = np.sin(dy / 2) ** 2 + np.cos(y1) * np.cos(y2) * np.sin(dx / 2) ** 2
    return float(2 * 6_371_000 * np.arcsin(np.sqrt(a)))


def build_features(
    points: pd.DataFrame,
    traffic: pd.DataFrame,
    schedule: pd.DataFrame,
) -> pd.DataFrame:
    """Build one feature row per prediction point using data available by its T.

    Args:
        points: Rows with tr_id, T, target_stop_id, target_time_begin and cur_dev_s.
        traffic: Telemetry with event_time, receive_time, location_valid and GPS fields.
        schedule: Planned stops; only tt_action_item_id, tr_id and geom are read.

    Returns:
        DataFrame aligned with points and containing FEATURE_COLUMNS only.
    """
    required_points = {"tr_id", "T", "target_stop_id", "target_time_begin", "cur_dev_s"}
    required_traffic = {"tr_id", "event_time", "receive_time", "location_valid", "lon", "lat", "speed", "heading"}
    required_schedule = {"tr_id", "tt_action_item_id", "geom"}
    for name, frame, required in (
        ("points", points, required_points),
        ("traffic", traffic, required_traffic),
        ("schedule", schedule, required_schedule),
    ):
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{name} missing columns: {sorted(missing)}")

    p = points.reset_index(drop=True).copy()
    p["T"] = pd.to_datetime(p["T"], format="mixed", errors="raise")
    p["target_time_begin"] = pd.to_datetime(p["target_time_begin"], format="mixed", errors="raise")
    p["tr_id"] = pd.to_numeric(p["tr_id"], errors="raise").astype("int64")

    # Actual stop times are deliberately excluded, including when supplied in schedule.csv.
    stops = schedule[["tr_id", "tt_action_item_id", "geom"]].drop_duplicates(["tr_id", "tt_action_item_id"])
    stops = stops.rename(columns={"tt_action_item_id": "target_stop_id"})
    geometry = stops["geom"].astype("string").str.extract(
        r"POINT\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)"
    )
    stops = stops.assign(
        target_lon=pd.to_numeric(geometry[0], errors="coerce").astype(float),
        target_lat=pd.to_numeric(geometry[1], errors="coerce").astype(float),
    ).drop(columns="geom")
    p = p.merge(stops, on=["tr_id", "target_stop_id"], how="left", sort=False, validate="many_to_one")

    t = traffic[list(required_traffic)].copy()
    t["event_time"] = pd.to_datetime(t["event_time"], format="mixed", errors="coerce")
    t["receive_time"] = pd.to_datetime(t["receive_time"], format="mixed", errors="coerce")
    t["receive_time"] = t["receive_time"].fillna(t["event_time"])
    t = t.dropna(subset=["event_time", "receive_time"])
    t = t[t["location_valid"].fillna(False).astype(bool)].copy()
    for column in ("lon", "lat", "speed", "heading"):
        t[column] = pd.to_numeric(t[column], errors="coerce")
    t = t[t["lon"].between(-180, 180) & t["lat"].between(-90, 90)]
    t.loc[~t["speed"].between(0, 120), "speed"] = np.nan
    t = t.sort_values(["tr_id", "event_time"])
    telemetry_by_vehicle = {
        int(vehicle): (group, group["event_time"].to_numpy(dtype="datetime64[ns]"))
        for vehicle, group in t.groupby("tr_id", sort=False)
    }

    rows: list[dict[str, float | str]] = []
    for point in p.itertuples(index=False):
        result: dict[str, float | str] = {
            "tr_id": str(point.tr_id),
            "cur_dev_s": float(point.cur_dev_s),
            "time_to_target_s": (point.target_time_begin - point.T).total_seconds(),
            "hour": point.T.hour,
            "day_of_week": point.T.dayofweek,
            "target_lon": point.target_lon,
            "target_lat": point.target_lat,
        }
        vehicle_data = telemetry_by_vehicle.get(point.tr_id)
        if vehicle_data is not None:
            telemetry, event_times = vehicle_data
            # Event time and arrival at our server must both be no later than T.
            start = np.searchsorted(event_times, np.datetime64(point.T - pd.Timedelta(minutes=30)), side="left")
            end = np.searchsorted(event_times, np.datetime64(point.T), side="right")
            recent = telemetry.iloc[start:end]
            recent = recent[recent["receive_time"] <= point.T]
            if not recent.empty:
                last = recent.iloc[-1]
                result.update(
                    last_lon=float(last.lon),
                    last_lat=float(last.lat),
                    last_speed=float(last.speed),
                    last_heading=float(last.heading),
                    telemetry_age_s=(point.T - last.event_time).total_seconds(),
                    distance_to_target_m=_distance_m(last.lon, last.lat, point.target_lon, point.target_lat),
                )
                window = recent[recent["event_time"] >= point.T - pd.Timedelta(minutes=5)]
                speeds = window["speed"].dropna()
                result["location_count_5m"] = len(window)
                result["speed_mean_5m"] = speeds.mean()
                result["speed_std_5m"] = speeds.std(ddof=0) if len(speeds) else np.nan
                result["idle_ratio_5m"] = (speeds < 3).mean() if len(speeds) else np.nan
                for minutes in (1, 3):
                    result[f"speed_mean_{minutes}m"] = window.loc[
                        window["event_time"] >= point.T - pd.Timedelta(minutes=minutes), "speed"
                    ].mean()
                if len(window) >= 2:
                    first = window.iloc[0]
                    result["movement_5m_m"] = _distance_m(first.lon, first.lat, last.lon, last.lat)
        rows.append(result)

    features = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
    features["tr_id"] = features["tr_id"].astype(str)
    for column in FEATURE_COLUMNS[1:]:
        features[column] = pd.to_numeric(features[column], errors="coerce").astype(float)
    return features
