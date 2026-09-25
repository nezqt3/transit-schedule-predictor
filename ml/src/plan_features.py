"""Features from the published stop plan; actual arrival times are never read."""

from __future__ import annotations

import numpy as np
import pandas as pd

EARTH_RADIUS_M = 6_371_000.0
PLAN_FEATURE_COLUMNS = [
    "planned_stops_to_target", "planned_stops_next_5m", "next_stop_plan_s",
    "last_stop_plan_age_s", "plan_route_distance_m", "required_route_speed_kmh",
    "route_to_straight_ratio",
]


def _distance_m(lon1: np.ndarray, lat1: np.ndarray,
                lon2: np.ndarray, lat2: np.ndarray) -> np.ndarray:
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + (
        np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(np.clip(a, 0, 1)))


def build_plan_features(
    points: pd.DataFrame, base_features: pd.DataFrame, schedule: pd.DataFrame,
) -> pd.DataFrame:
    """Describe planned stops between T and the target using schedule plan only.

    Args:
        points: Prediction rows in the same order as base_features.
        base_features: Point-in-time telemetry features with the last GPS position.
        schedule: Planned stop rows; only ID, vehicle, time_begin and geom are used.

    Returns:
        One numeric feature row per point, aligned with points.
    """
    if len(points) != len(base_features):
        raise ValueError("points and base_features must be row aligned")
    plan = schedule[["tr_id", "tt_action_item_id", "time_begin", "geom"]].copy()
    plan["time_begin"] = pd.to_datetime(plan["time_begin"], format="mixed")
    geometry = plan["geom"].astype("string").str.extract(
        r"POINT\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)"
    )
    plan["lon"] = pd.to_numeric(geometry[0], errors="coerce")
    plan["lat"] = pd.to_numeric(geometry[1], errors="coerce")
    by_vehicle = {}
    for tr_id, group in plan.groupby("tr_id", sort=False):
        group = group.sort_values("time_begin", kind="stable")
        if group["tt_action_item_id"].duplicated().any():
            raise ValueError(f"Duplicate planned stop ID for vehicle {tr_id}")
        lon = group["lon"].to_numpy(float)
        lat = group["lat"].to_numpy(float)
        between = _distance_m(lon[:-1], lat[:-1], lon[1:], lat[1:])
        distance = np.r_[0.0, np.cumsum(np.where(np.isfinite(between), between, 0.0))]
        by_vehicle[int(tr_id)] = (
            group["time_begin"].to_numpy(dtype="datetime64[ns]"), lon, lat, distance,
            {int(stop): index for index, stop in enumerate(group["tt_action_item_id"])},
        )

    rows = []
    for point, base in zip(points.itertuples(index=False), base_features.itertuples(index=False)):
        result: dict[str, float] = {}
        data = by_vehicle.get(int(point.tr_id))
        if data is not None:
            times, lon, lat, cumulative, stop_indices = data
            t = np.datetime64(pd.Timestamp(point.T), "ns")
            target_index = stop_indices.get(int(point.target_stop_id))
            next_index = int(np.searchsorted(times, t, side="right"))
            if target_index is not None and next_index <= target_index:
                target_time = np.datetime64(pd.Timestamp(point.target_time_begin), "ns")
                count = target_index - next_index + 1
                result["planned_stops_to_target"] = float(count)
                result["planned_stops_next_5m"] = float(
                    np.searchsorted(times, t + np.timedelta64(5, "m"), side="right") - next_index
                )
                result["next_stop_plan_s"] = float((times[next_index] - t) / np.timedelta64(1, "s"))
                if next_index > 0:
                    result["last_stop_plan_age_s"] = float(
                        (t - times[next_index - 1]) / np.timedelta64(1, "s")
                    )
                if np.isfinite(base.last_lon) and np.isfinite(base.last_lat):
                    first_leg = float(_distance_m(
                        np.asarray(base.last_lon), np.asarray(base.last_lat),
                        np.asarray(lon[next_index]), np.asarray(lat[next_index]),
                    ))
                    route_distance = first_leg + cumulative[target_index] - cumulative[next_index]
                    result["plan_route_distance_m"] = route_distance
                    remaining_s = max(float((target_time - t) / np.timedelta64(1, "s")), 1.0)
                    result["required_route_speed_kmh"] = route_distance / remaining_s * 3.6
                    if np.isfinite(base.distance_to_target_m) and base.distance_to_target_m > 1:
                        result["route_to_straight_ratio"] = route_distance / base.distance_to_target_m
        rows.append(result)
    return pd.DataFrame(rows, columns=PLAN_FEATURE_COLUMNS, dtype=float)
