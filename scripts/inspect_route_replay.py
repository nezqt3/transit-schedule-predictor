"""Inspect a validation route and replay one historical point through ML.

Only published plan, prediction-point inputs and telemetry available by T are read.
The script never reads actual stop times or target labels.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "validate"
POINT = re.compile(r"POINT\s*\(\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s*\)")


def coordinates(geom: str) -> tuple[float, float]:
    match = POINT.fullmatch(geom)
    if match is None:
        raise ValueError(f"invalid stop geometry: {geom}")
    return float(match.group(1)), float(match.group(2))


def optional_number(value: object) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    return float(number) if math.isfinite(number) else None


def plot_route(point: pd.Series, stops: pd.DataFrame, telemetry: pd.DataFrame,
               output: Path) -> None:
    import matplotlib.pyplot as plt

    route = stops.copy()
    route[["lon", "lat"]] = route["geom"].apply(
        lambda geom: pd.Series(coordinates(geom))
    )
    fig, ax = plt.subplots(figsize=(9, 6))
    ax.plot(telemetry["lon"], telemetry["lat"], color="#707980", alpha=0.65,
            linewidth=1.4, label="GPS before T")
    ax.scatter(telemetry["lon"], telemetry["lat"], color="#707980", s=5,
               alpha=0.35)
    ax.plot(route["lon"], route["lat"], "o--", color="#1965ab",
            linewidth=1.2, markersize=4, label="Planned stops (straight links)")
    for index, stop in enumerate(route.itertuples()):
        if index % 3 == 0 and stop.tt_action_item_id != point["target_stop_id"]:
            ax.annotate(stop.time_begin.strftime("%H:%M"), (stop.lon, stop.lat),
                        xytext=(4, 4), textcoords="offset points", fontsize=8)
    target = route.loc[route["tt_action_item_id"] == point["target_stop_id"]].iloc[0]
    ax.scatter([target.lon], [target.lat], marker="*", s=220,
               color="#db4d32", label="Target stop", zorder=5)
    last = telemetry.iloc[-1]
    ax.scatter([last.lon], [last.lat], marker="D", s=55,
               color="#151b1e", label="Last GPS by T", zorder=5)
    ax.set(xlabel="Longitude", ylabel="Latitude",
           title=f"Historical plan and GPS · tr_id={point['tr_id']} · T={point['T']:%Y-%m-%d %H:%M}")
    ax.grid(alpha=0.2)
    ax.legend(loc="best")
    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=160)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample-id", default="131672_1767670500")
    parser.add_argument("--plot", type=Path, help="Save a PNG route/GPS inspection plot")
    parser.add_argument("--predict", action="store_true",
                        help="Call the running ML service using historical data only")
    parser.add_argument("--ml-url", default="http://localhost:8001/predict")
    args = parser.parse_args()

    points = pd.read_csv(RAW / "points.csv")
    matches = points.loc[points["sample_id"] == args.sample_id]
    if len(matches) != 1:
        raise ValueError(f"expected one validation point for {args.sample_id}, got {len(matches)}")
    point = matches.iloc[0].copy()
    point["T"] = pd.Timestamp(point["T"])
    point["target_time_begin"] = pd.Timestamp(point["target_time_begin"])
    tr_id = int(point["tr_id"])
    t = point["T"]

    plan = pd.read_csv(RAW / "schedule_plan.csv",
                       usecols=["tr_id", "tt_action_item_id", "time_begin", "geom"])
    plan = plan.loc[plan["tr_id"] == tr_id].copy()
    plan["time_begin"] = pd.to_datetime(plan["time_begin"])
    plan = plan.sort_values("time_begin", kind="stable")
    target = plan.loc[plan["tt_action_item_id"] == point["target_stop_id"]]
    if len(target) != 1 or target.iloc[0]["time_begin"] != point["target_time_begin"]:
        raise ValueError("target stop/time does not match published plan")
    stop_lon, stop_lat = coordinates(target.iloc[0]["geom"])

    traffic = pd.read_csv(RAW / "traffic.csv", usecols=[
        "tr_id", "unit_id", "event_time", "receive_time", "location_valid",
        "lat", "lon", "speed", "heading",
    ])
    traffic = traffic.loc[traffic["tr_id"] == tr_id].copy()
    units = traffic["unit_id"].dropna().unique()
    if len(units) != 1:
        raise ValueError(f"expected one NDTP unit for tr_id={tr_id}, got {units}")
    traffic["event_time"] = pd.to_datetime(traffic["event_time"])
    traffic["receive_time"] = pd.to_datetime(traffic["receive_time"])
    past = traffic.loc[
        (traffic["event_time"] >= t - pd.Timedelta(minutes=30))
        & (traffic["event_time"] <= t)
        & (traffic["receive_time"] <= t)
        & traffic["location_valid"].fillna(False)
        & traffic["lat"].between(-90, 90)
        & traffic["lon"].between(-180, 180)
    ].sort_values("event_time").tail(150)
    if past.empty:
        raise ValueError("no usable telemetry available by T")

    near_stops = plan.loc[
        (plan["time_begin"] >= t - pd.Timedelta(minutes=15))
        & (plan["time_begin"] <= point["target_time_begin"] + pd.Timedelta(minutes=5))
    ]
    future_stops = plan.loc[
        (plan["time_begin"] > t)
        & (plan["time_begin"] <= point["target_time_begin"])
    ]
    print(f"Historical validation sample: {args.sample_id}")
    print(f"tr_id={tr_id}, unit_id={int(units[0])}, T={t}, cur_dev_s={point['cur_dev_s']}")
    print(f"Target stop={int(point['target_stop_id'])}, plan={point['target_time_begin']}, "
          f"lon={stop_lon:.6f}, lat={stop_lat:.6f}")
    print(f"Planned stops for vehicle={len(plan)}, between T and target={len(future_stops)}, "
          f"usable GPS by T (last 30m, capped at 150)={len(past)}")
    print("Stops between T and target:")
    for stop in future_stops.itertuples():
        lon, lat = coordinates(stop.geom)
        print(f"  {stop.time_begin:%H:%M}  {stop.tt_action_item_id}  ({lat:.6f}, {lon:.6f})")

    if args.plot:
        plot_route(point, near_stops, past, args.plot)
        print(f"Plot: {args.plot.resolve()}")

    if args.predict:
        payload = {
            "tr_id": tr_id,
            "T": t.isoformat(),
            "cur_dev_s": float(point["cur_dev_s"]),
            "target_stop_id": int(point["target_stop_id"]),
            "target_time_begin": point["target_time_begin"].isoformat(),
            "stop_lat": stop_lat,
            "stop_lon": stop_lon,
            "telemetry": [{
                "event_time": row.event_time.isoformat(),
                "receive_time": row.receive_time.isoformat(),
                "location_valid": True,
                "lat": float(row.lat),
                "lon": float(row.lon),
                "speed": optional_number(row.speed),
                "heading": optional_number(row.heading),
            } for row in past.itertuples()],
        }
        request = Request(args.ml_url, json.dumps(payload).encode(),
                          {"Content-Type": "application/json"})
        with urlopen(request, timeout=30) as response:
            prediction = json.load(response)
        print(f"ML prediction={prediction['prediction']:.2f} s; "
              f"cur_dev baseline={point['cur_dev_s']:.2f} s; "
              f"model={prediction['model_version']}")


if __name__ == "__main__":
    main()
