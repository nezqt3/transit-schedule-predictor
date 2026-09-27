"""Directed route graph and HMM/Viterbi map matching for NDTP telemetry."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from pathlib import Path

from app.ndtp.schemas import TelemetryEvent

EARTH_RADIUS_M = 6_371_000.0
logger = logging.getLogger(__name__)


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance between two WGS84 points."""
    a1, a2 = math.radians(lat1), math.radians(lat2)
    da, do = a2 - a1, math.radians(lon2 - lon1)
    h = math.sin(da / 2) ** 2 + math.cos(a1) * math.cos(a2) * math.sin(do / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.atan2(math.sqrt(h), math.sqrt(max(0.0, 1 - h)))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return initial bearing in degrees."""
    latitude1, latitude2 = math.radians(lat1), math.radians(lat2)
    longitude_delta = math.radians(lon2 - lon1)
    east = math.sin(longitude_delta) * math.cos(latitude2)
    north = (math.cos(latitude1) * math.sin(latitude2)
             - math.sin(latitude1) * math.cos(latitude2) * math.cos(longitude_delta))
    return math.degrees(math.atan2(east, north)) % 360


def angular_difference(left: float, right: float) -> float:
    return abs((left - right + 180) % 360 - 180)


@dataclass(frozen=True)
class RouteSegment:
    index: int
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float
    start_chainage_m: float
    length_m: float
    heading: float
    planned_start_epoch_s: float | None = None
    planned_end_epoch_s: float | None = None


@dataclass(frozen=True)
class RouteGraph:
    tr_id: int
    segments: tuple[RouteSegment, ...]
    stop_chainages: tuple[float, ...]
    source: str


@dataclass(frozen=True)
class MapMatchResult:
    event: TelemetryEvent
    segment_index: int
    chainage_m: float
    latitude: float
    longitude: float
    distance_m: float
    confidence: float
    heading_error_deg: float | None
    graph_source: str


@dataclass(frozen=True)
class _Candidate:
    segment: RouteSegment
    chainage_m: float
    latitude: float
    longitude: float
    distance_m: float
    heading_error_deg: float | None
    emission: float


def _project(lat: float, lon: float, segment: RouteSegment) -> tuple[float, float, float, float]:
    """Project a WGS84 point to a short segment in a local metric plane."""
    ref_lat = math.radians((segment.start_lat + segment.end_lat + lat) / 3)
    scale_x = EARTH_RADIUS_M * math.cos(ref_lat) * math.pi / 180
    scale_y = EARTH_RADIUS_M * math.pi / 180
    ax, ay = segment.start_lon * scale_x, segment.start_lat * scale_y
    bx, by = segment.end_lon * scale_x, segment.end_lat * scale_y
    px, py = lon * scale_x, lat * scale_y
    dx, dy = bx - ax, by - ay
    denominator = dx * dx + dy * dy
    fraction = 0.0 if denominator <= 1e-9 else max(
        0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / denominator)
    )
    projected_lon = segment.start_lon + fraction * (segment.end_lon - segment.start_lon)
    projected_lat = segment.start_lat + fraction * (segment.end_lat - segment.start_lat)
    return fraction, projected_lat, projected_lon, distance_m(
        lat, lon, projected_lat, projected_lon,
    )


class RouteGraphRegistry:
    """Build route graphs from schedule stops or route polylines in GeoJSON."""

    def __init__(self, plans: dict[int, list[dict]], geojson_path: str | None = None) -> None:
        polylines = self._load_geojson(geojson_path)
        self.graphs: dict[int, RouteGraph] = {}
        for tr_id, stops in plans.items():
            coordinates = polylines.get(tr_id)
            source = "geojson" if coordinates else "schedule"
            if not coordinates:
                coordinates = [(stop["stop_lon"], stop["stop_lat"]) for stop in stops]
            graph = self._build(tr_id, coordinates, stops, source)
            if graph is not None:
                self.graphs[tr_id] = graph

    @staticmethod
    def _load_geojson(path: str | None) -> dict[int, list[tuple[float, float]]]:
        if not path or not Path(path).is_file():
            return {}
        try:
            document = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            logger.exception("route graph GeoJSON is invalid; schedule graph will be used")
            return {}
        result: dict[int, list[tuple[float, float]]] = {}
        for feature in document.get("features", []):
            properties = feature.get("properties") or {}
            tr_id = properties.get("tr_id")
            geometry = feature.get("geometry") or {}
            coordinates = geometry.get("coordinates")
            if tr_id is None or not coordinates:
                continue
            if geometry.get("type") == "MultiLineString":
                coordinates = [point for line in coordinates for point in line]
            if geometry.get("type") not in {"LineString", "MultiLineString"}:
                continue
            result[int(tr_id)] = [(float(point[0]), float(point[1])) for point in coordinates]
        return result

    @staticmethod
    def _build(tr_id: int, coordinates: list[tuple[float, float]], stops: list[dict],
               source: str) -> RouteGraph | None:
        clean = [coordinates[0]] if coordinates else []
        for point in coordinates[1:]:
            if point != clean[-1]:
                clean.append(point)
        if len(clean) < 2:
            return None
        segments = []
        chainage = 0.0
        for index, ((start_lon, start_lat), (end_lon, end_lat)) in enumerate(
            zip(clean, clean[1:])
        ):
            length = distance_m(start_lat, start_lon, end_lat, end_lon)
            if length < 0.5:
                continue
            segments.append(RouteSegment(
                index=len(segments), start_lat=start_lat, start_lon=start_lon,
                end_lat=end_lat, end_lon=end_lon, start_chainage_m=chainage,
                length_m=length, heading=bearing(start_lat, start_lon, end_lat, end_lon),
                planned_start_epoch_s=(
                    stops[index]["target_time_begin"].timestamp()
                    if source == "schedule" and index < len(stops) - 1 else None
                ),
                planned_end_epoch_s=(
                    stops[index + 1]["target_time_begin"].timestamp()
                    if source == "schedule" and index < len(stops) - 1 else None
                ),
            ))
            chainage += length
        if not segments:
            return None
        stop_chainages = []
        for stop in stops:
            candidates = []
            for segment in segments:
                fraction, _, _, distance = _project(
                    stop["stop_lat"], stop["stop_lon"], segment,
                )
                candidates.append((
                    distance,
                    segment.start_chainage_m + fraction * segment.length_m,
                ))
            stop_chainages.append(min(candidates)[1])
        return RouteGraph(tr_id, tuple(segments), tuple(stop_chainages), source)

    def rebuild(self, tr_id: int, stops: list[dict]) -> None:
        coordinates = [(stop["stop_lon"], stop["stop_lat"]) for stop in stops]
        graph = self._build(tr_id, coordinates, stops, "schedule")
        if graph is not None:
            self.graphs[tr_id] = graph


class HmmMapMatcher:
    """Match a causal NDTP observation window to a directed route using Viterbi."""

    def __init__(self, registry: RouteGraphRegistry, max_distance_m: float = 250,
                 candidates_per_point: int = 6) -> None:
        self.registry = registry
        self.max_distance_m = max_distance_m
        self.candidates_per_point = candidates_per_point

    def _candidates(self, graph: RouteGraph, event: TelemetryEvent) -> list[_Candidate]:
        nav = event.nav
        if nav is None or not nav.coordinates_valid:
            return []
        candidates = []
        accuracy_sigma = 18.0 if (nav.satellites or 0) >= 6 else 32.0
        for segment in graph.segments:
            fraction, latitude, longitude, offset = _project(
                nav.latitude, nav.longitude, segment,
            )
            if offset > self.max_distance_m:
                continue
            heading_error = None
            heading_score = 0.0
            time_score = 0.0
            if nav.course is not None and (nav.speed_avg or 0) >= 3:
                heading_error = angular_difference(float(nav.course), segment.heading)
                if heading_error > 110:
                    continue
                heading_score = -0.5 * (heading_error / 40.0) ** 2
            if (segment.planned_start_epoch_s is not None
                    and segment.planned_end_epoch_s is not None):
                expected_epoch = (
                    segment.planned_start_epoch_s
                    + fraction * (segment.planned_end_epoch_s - segment.planned_start_epoch_s)
                )
                time_error_s = abs(event.event_time.timestamp() - expected_epoch)
                # A soft prior separates repeated loops of the same vehicle,
                # while still allowing substantial real schedule deviation.
                time_score = -min(time_error_s, 7200.0) / 900.0
            candidates.append(_Candidate(
                segment=segment,
                chainage_m=segment.start_chainage_m + fraction * segment.length_m,
                latitude=latitude, longitude=longitude, distance_m=offset,
                heading_error_deg=heading_error,
                emission=-0.5 * (offset / accuracy_sigma) ** 2 + heading_score + time_score,
            ))
        return sorted(candidates, key=lambda item: item.emission, reverse=True)[
            :self.candidates_per_point
        ]

    @staticmethod
    def _transition(previous: _Candidate, current: _Candidate,
                    previous_event: TelemetryEvent, current_event: TelemetryEvent) -> float:
        elapsed = max(0.1, (current_event.event_time - previous_event.event_time).total_seconds())
        observed = distance_m(
            previous_event.nav.latitude, previous_event.nav.longitude,
            current_event.nav.latitude, current_event.nav.longitude,
        )
        route_delta = current.chainage_m - previous.chainage_m
        # Directed routes allow a little GPS jitter backwards, never a large teleport.
        if route_delta < -60:
            return -1e9
        maximum = max(120.0, elapsed * 45.0)  # 162 km/h hard physical envelope
        if route_delta > maximum:
            return -1e9
        mismatch = abs(max(0.0, route_delta) - observed)
        score = -mismatch / max(25.0, observed * 0.5 + 15.0)
        if current.segment.index + 1 < previous.segment.index:
            score -= 12.0
        return score

    def match_sequence(self, tr_id: int,
                       events: list[TelemetryEvent]) -> list[MapMatchResult]:
        graph = self.registry.graphs.get(tr_id)
        ordered = sorted(events, key=lambda event: event.event_time)[-12:]
        if graph is None or not ordered:
            return []
        layers: list[list[_Candidate]] = []
        kept_events: list[TelemetryEvent] = []
        for event in ordered:
            candidates = self._candidates(graph, event)
            if candidates:
                layers.append(candidates)
                kept_events.append(event)
        if not layers:
            return []
        scores = [candidate.emission for candidate in layers[0]]
        backpointers: list[list[int]] = []
        for layer_index in range(1, len(layers)):
            new_scores = []
            pointers = []
            for current in layers[layer_index]:
                options = [
                    score + self._transition(
                        previous, current, kept_events[layer_index - 1], kept_events[layer_index],
                    )
                    for score, previous in zip(scores, layers[layer_index - 1])
                ]
                best = max(range(len(options)), key=options.__getitem__)
                pointers.append(best)
                new_scores.append(options[best] + current.emission)
            backpointers.append(pointers)
            scores = new_scores
        state = max(range(len(scores)), key=scores.__getitem__)
        states = [state]
        for pointers in reversed(backpointers):
            state = pointers[state]
            states.append(state)
        states.reverse()
        margin = (sorted(scores, reverse=True)[0] - sorted(scores, reverse=True)[1]
                  if len(scores) > 1 else 3.0)
        path_confidence = 1.0 / (1.0 + math.exp(-margin))
        results = []
        for event, candidates, selected in zip(kept_events, layers, states):
            candidate = candidates[selected]
            spatial = math.exp(-candidate.distance_m / 80.0)
            results.append(MapMatchResult(
                event=event, segment_index=candidate.segment.index,
                chainage_m=candidate.chainage_m, latitude=candidate.latitude,
                longitude=candidate.longitude, distance_m=candidate.distance_m,
                confidence=round(max(0.0, min(1.0, spatial * path_confidence)), 4),
                heading_error_deg=candidate.heading_error_deg,
                graph_source=graph.source,
            ))
        return results

    def match(self, tr_id: int, events: list[TelemetryEvent]) -> MapMatchResult | None:
        matches = self.match_sequence(tr_id, events)
        return matches[-1] if matches else None
