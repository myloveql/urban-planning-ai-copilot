from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pyproj import Transformer

from app.core.config import get_settings

SOURCE_CRS = "EPSG:32649"
TARGET_CRS = "EPSG:4326"


@dataclass
class LandUseDataset:
    geojson: dict[str, Any]
    meta: dict[str, Any]


_TRANSFORMER = Transformer.from_crs(SOURCE_CRS, TARGET_CRS, always_xy=True)
_CACHE: dict[str, Any] = {"path": None, "mtime": None, "dataset": None}


def _out_of_china(lng: float, lat: float) -> bool:
    return not (72.004 <= lng <= 137.8347 and 0.8293 <= lat <= 55.8271)


def _transform_lat(x: float, y: float) -> float:
    value = (
        -100.0
        + 2.0 * x
        + 3.0 * y
        + 0.2 * y * y
        + 0.1 * x * y
        + 0.2 * abs(x) ** 0.5
    )
    value += (20.0 * _sin(6.0 * x) + 20.0 * _sin(2.0 * x)) * 2.0 / 3.0
    value += (20.0 * _sin(y) + 40.0 * _sin(y / 3.0)) * 2.0 / 3.0
    value += (160.0 * _sin(y / 12.0) + 320.0 * _sin(y / 30.0)) * 2.0 / 3.0
    return value


def _transform_lng(x: float, y: float) -> float:
    value = (
        300.0
        + x
        + 2.0 * y
        + 0.1 * x * x
        + 0.1 * x * y
        + 0.1 * abs(x) ** 0.5
    )
    value += (20.0 * _sin(6.0 * x) + 20.0 * _sin(2.0 * x)) * 2.0 / 3.0
    value += (20.0 * _sin(x) + 40.0 * _sin(x / 3.0)) * 2.0 / 3.0
    value += (150.0 * _sin(x / 12.0) + 300.0 * _sin(x / 30.0)) * 2.0 / 3.0
    return value


def _sin(value: float) -> float:
    from math import sin, pi

    return sin(value * pi)


def wgs84_to_gcj02(lng: float, lat: float) -> tuple[float, float]:
    if _out_of_china(lng, lat):
        return lng, lat

    from math import cos, sin, sqrt, pi

    a = 6378245.0
    ee = 0.00669342162296594323
    delta_lat = _transform_lat(lng - 105.0, lat - 35.0)
    delta_lng = _transform_lng(lng - 105.0, lat - 35.0)
    rad_lat = lat / 180.0 * pi
    magic = sin(rad_lat)
    magic = 1 - ee * magic * magic
    sqrt_magic = sqrt(magic)
    delta_lat = (delta_lat * 180.0) / ((a * (1 - ee)) / (magic * sqrt_magic) * pi)
    delta_lng = (delta_lng * 180.0) / (a / sqrt_magic * cos(rad_lat) * pi)
    return lng + delta_lng, lat + delta_lat


def _transform_ring(ring: list[list[float]]) -> list[list[float]]:
    transformed: list[list[float]] = []
    for point in ring:
        if len(point) < 2:
            continue
        x, y = float(point[0]), float(point[1])
        lng, lat = _TRANSFORMER.transform(x, y)
        gcj_lng, gcj_lat = wgs84_to_gcj02(lng, lat)
        transformed.append([round(gcj_lng, 8), round(gcj_lat, 8)])
    if transformed and transformed[0] != transformed[-1]:
        transformed.append(transformed[0])
    return transformed


def _normalize_ring_without_projection(ring: list[list[float]]) -> list[list[float]]:
    normalized: list[list[float]] = []
    for point in ring:
        if len(point) < 2:
            continue
        lng = round(float(point[0]), 8)
        lat = round(float(point[1]), 8)
        normalized.append([lng, lat])
    if normalized and normalized[0] != normalized[-1]:
        normalized.append(normalized[0])
    return normalized


def _iter_all_points(features: list[dict[str, Any]]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for feature in features:
        geometry = feature.get("geometry") or {}
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates") or []
        if geometry_type == "Polygon":
            polygons = [coordinates]
        elif geometry_type == "MultiPolygon":
            polygons = coordinates
        else:
            continue
        for polygon in polygons:
            for ring in polygon:
                for point in ring:
                    if len(point) >= 2:
                        points.append((float(point[0]), float(point[1])))
    return points


def _infer_coordinate_mode(raw_features: list[dict[str, Any]]) -> str:
    points = _iter_all_points(raw_features)
    if not points:
        return "projected"
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    if all(-180.0 <= x <= 180.0 for x in xs) and all(-90.0 <= y <= 90.0 for y in ys):
        return "geographic"
    return "projected"


def _normalize_polygon_rings(polygon: list[list[list[float]]], coordinate_mode: str) -> list[list[list[float]]]:
    if coordinate_mode == "geographic":
        rings = [_normalize_ring_without_projection(ring) for ring in polygon if isinstance(ring, list) and ring]
    else:
        rings = [_transform_ring(ring) for ring in polygon if isinstance(ring, list) and ring]
    return [ring for ring in rings if len(ring) >= 4]


def _normalize_feature(feature: dict[str, Any], feature_id: int, coordinate_mode: str) -> dict[str, Any] | None:
    geometry = feature.get("geometry") or {}
    geometry_type = geometry.get("type")
    if geometry_type not in {"Polygon", "MultiPolygon"}:
        return None
    coordinates = geometry.get("coordinates") or []
    polygons = [coordinates] if geometry_type == "Polygon" else coordinates
    transformed_polygons = [
        _normalize_polygon_rings(polygon, coordinate_mode)
        for polygon in polygons
        if isinstance(polygon, list) and polygon
    ]
    transformed_polygons = [polygon for polygon in transformed_polygons if polygon]
    if not transformed_polygons:
        return None
    properties = dict(feature.get("properties") or {})
    properties.setdefault("feature_id", feature_id)
    properties.setdefault(
        "interactive_label",
        str(
            properties.get("用地性质")
            or properties.get("用地代码")
            or properties.get("Layer")
            or properties.get("fid")
            or f"地块 {feature_id}"
        ),
    )
    return {
        "type": "Feature",
        "properties": properties,
        "geometry": {
            "type": "MultiPolygon" if geometry_type == "MultiPolygon" else "Polygon",
            "coordinates": transformed_polygons if geometry_type == "MultiPolygon" else transformed_polygons[0],
        },
    }


def _build_dataset(path: Path) -> LandUseDataset:
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw_features = raw.get("features") or []
    coordinate_mode = _infer_coordinate_mode(raw_features)
    features: list[dict[str, Any]] = []
    for index, feature in enumerate(raw_features, start=1):
        normalized = _normalize_feature(feature, index, coordinate_mode)
        if normalized is not None:
            features.append(normalized)
    meta = {
        "feature_count": len(features),
        "raw_feature_count": len(raw_features),
        "source_name": raw.get("name") or path.name,
        "source_crs": SOURCE_CRS if coordinate_mode == "projected" else "GEOGRAPHIC",
        "target_crs": "GCJ-02" if coordinate_mode == "projected" else "AS_IS",
        "coordinate_mode": coordinate_mode,
        "has_properties": any(bool((feature.get("properties") or {}).keys()) for feature in raw_features),
        "interactive_fields": ["feature_id", "interactive_label", "用地性质", "用地代码", "Layer", "fid"],
    }
    return LandUseDataset(
        geojson={
            "type": "FeatureCollection",
            "features": features,
        },
        meta=meta,
    )


def get_land_use_dataset() -> LandUseDataset:
    settings = get_settings()
    path = settings.land_use_geojson_path
    if not path.exists():
        raise FileNotFoundError(f"土地利用 GeoJSON 文件不存在: {path}")

    mtime = path.stat().st_mtime
    if _CACHE["path"] == str(path) and _CACHE["mtime"] == mtime and isinstance(_CACHE["dataset"], LandUseDataset):
        return _CACHE["dataset"]

    dataset = _build_dataset(path)
    _CACHE["path"] = str(path)
    _CACHE["mtime"] = mtime
    _CACHE["dataset"] = dataset
    return dataset
