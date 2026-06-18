from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.poi import Poi

IMPORT_BATCH_SIZE = 5000
DEFAULT_QUERY_LIMIT = 800


def _resolve_dataset_path() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        candidate = parent / "现状" / "佛山市poi2.csv"
        if candidate.exists():
            return candidate
    return current.parents[6] / "现状" / "佛山市poi2.csv"


DATASET_PATH = _resolve_dataset_path()


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _iter_pois_from_csv(dataset_path: Path = DATASET_PATH):
    if not dataset_path.exists():
        return
    batch: list[Poi] = []
    for encoding in ("utf-8-sig", "gb18030", "gbk"):
        try:
            with dataset_path.open("r", encoding=encoding, newline="") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    try:
                        lng = float(row["X"])
                        lat = float(row["Y"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    poi = Poi(
                        object_id=_parse_int(row.get("OBJECTID")),
                        source_id=_parse_int(row.get("FID_POI_all")),
                        name=_clean_text(row.get("NAME")) or "未命名POI",
                        district=_clean_text(row.get("县区")),
                        major_category=_clean_text(row.get("大类")),
                        middle_category=_clean_text(row.get("中类")),
                        minor_category=_clean_text(row.get("小类")),
                        lng=lng,
                        lat=lat,
                    )
                    batch.append(poi)
                    if len(batch) >= IMPORT_BATCH_SIZE:
                        yield batch
                        batch.clear()
            break
        except UnicodeDecodeError:
            batch.clear()
            continue
    if batch:
        yield batch


def _parse_int(value: str | None) -> int | None:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def pois_initialized(db: Session) -> bool:
    first_row = db.scalar(select(Poi.id).limit(1))
    return first_row is not None


def initialize_pois(db: Session, dataset_path: Path = DATASET_PATH) -> int:
    inserted = 0
    started_at = time.perf_counter()
    for batch in _iter_pois_from_csv(dataset_path):
        db.bulk_save_objects(batch)
        db.commit()
        inserted += len(batch)
        elapsed = time.perf_counter() - started_at
        print(f"[pois_import] inserted={inserted} elapsed={elapsed:.1f}s", flush=True)
    return inserted


def bootstrap_pois(db: Session) -> int:
    if pois_initialized(db):
        return 0
    if not DATASET_PATH.exists():
        return 0
    return initialize_pois(db, DATASET_PATH)


def list_poi_categories(db: Session) -> list[tuple[str, int]]:
    rows = db.execute(
        select(Poi.major_category, func.count(Poi.id))
        .where(Poi.major_category.is_not(None))
        .group_by(Poi.major_category)
        .order_by(func.count(Poi.id).desc(), Poi.major_category.asc())
    ).all()
    return [(name, count) for name, count in rows if name]


def query_pois_in_bbox(
    db: Session,
    *,
    min_lng: float,
    min_lat: float,
    max_lng: float,
    max_lat: float,
    categories: Sequence[str] | None = None,
    limit: int = DEFAULT_QUERY_LIMIT,
) -> tuple[list[Poi], bool]:
    base = select(Poi).where(
        Poi.lng >= min_lng,
        Poi.lng <= max_lng,
        Poi.lat >= min_lat,
        Poi.lat <= max_lat,
    )
    category_values = [item.strip() for item in (categories or []) if item and item.strip()]
    if category_values:
        base = base.where(Poi.major_category.in_(category_values))
    rows = db.scalars(base.order_by(Poi.id).limit(limit + 1)).all()
    truncated = len(rows) > limit
    items = rows[:limit]
    return items, truncated


def get_district_poi_stats(db: Session, district: str | None = None) -> dict:
    base = select(Poi)
    if district:
        base = base.where(Poi.district.ilike(f"%{district}%"))
    rows = db.scalars(base).all()

    total = len(rows)
    major_counts: dict[str, int] = {}
    middle_counts: dict[str, int] = {}
    minor_counts: dict[str, int] = {}
    district_counts: dict[str, int] = {}
    for r in rows:
        if r.major_category:
            major_counts[r.major_category] = major_counts.get(r.major_category, 0) + 1
        if r.middle_category:
            middle_counts[r.middle_category] = middle_counts.get(r.middle_category, 0) + 1
        if r.minor_category:
            minor_counts[r.minor_category] = minor_counts.get(r.minor_category, 0) + 1
        key_district = r.district or "未知"
        district_counts[key_district] = district_counts.get(key_district, 0) + 1

    return {
        "total": total,
        "by_major": sorted(major_counts.items(), key=lambda x: -x[1]),
        "by_middle": sorted(middle_counts.items(), key=lambda x: -x[1]),
        "by_minor": sorted(minor_counts.items(), key=lambda x: -x[1]),
        "by_district": sorted(district_counts.items(), key=lambda x: -x[1]),
    }
