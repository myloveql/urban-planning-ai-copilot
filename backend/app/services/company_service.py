from __future__ import annotations

import csv
import time
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.company import Company

DATASET_PATH = Path(__file__).resolve().parents[3] / "企业数据" / "佛山市企业.csv"
IMPORT_BATCH_SIZE = 5000
DEFAULT_QUERY_LIMIT = 500


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    return text or None


def _iter_companies_from_csv(dataset_path: Path = DATASET_PATH):
    if not dataset_path.exists():
        return
    batch: list[Company] = []
    with dataset_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                lng = float(row["WGS84_lng"])
                lat = float(row["WGS84_lat"])
            except (KeyError, TypeError, ValueError):
                continue
            company = Company(
                company_name=_clean_text(row.get("公司名称")) or "未命名企业",
                status=_clean_text(row.get("经营状态")),
                legal_representative=_clean_text(row.get("法定代表人")),
                registered_capital=_clean_text(row.get("注册资本")),
                paid_in_capital=_clean_text(row.get("实缴资本")),
                established_at=_clean_text(row.get("成立日期")),
                district=_clean_text(row.get("所属区县")),
                industry=_clean_text(row.get("所属行业")),
                company_type=_clean_text(row.get("公司类型")),
                insured_count=_clean_text(row.get("参保人数")),
                address=_clean_text(row.get("注册地址")),
                business_scope=_clean_text(row.get("经营范围")),
                lng=lng,
                lat=lat,
                survival_status=_clean_text(row.get("生存状态")),
            )
            batch.append(company)
            if len(batch) >= IMPORT_BATCH_SIZE:
                yield batch
                batch.clear()
    if batch:
        yield batch


def companies_initialized(db: Session) -> bool:
    first_row = db.scalar(select(Company.id).limit(1))
    return first_row is not None


def initialize_companies(db: Session, dataset_path: Path = DATASET_PATH) -> int:
    inserted = 0
    started_at = time.perf_counter()
    for batch in _iter_companies_from_csv(dataset_path):
        db.bulk_save_objects(batch)
        db.commit()
        inserted += len(batch)
        elapsed = time.perf_counter() - started_at
        print(f"[companies_import] inserted={inserted} elapsed={elapsed:.1f}s", flush=True)
    return inserted


def bootstrap_companies(db: Session) -> int:
    if companies_initialized(db):
        return 0
    if not DATASET_PATH.exists():
        return 0
    return initialize_companies(db, DATASET_PATH)


def get_company_by_id(db: Session, company_id: int) -> Company | None:
    return db.get(Company, company_id)


def query_companies_in_bbox(
    db: Session,
    *,
    min_lng: float,
    min_lat: float,
    max_lng: float,
    max_lat: float,
    limit: int = DEFAULT_QUERY_LIMIT,
    keyword: str | None = None,
    district: str | None = None,
) -> tuple[list[Company], bool]:
    base = select(Company).where(
        Company.lng >= min_lng,
        Company.lng <= max_lng,
        Company.lat >= min_lat,
        Company.lat <= max_lat,
    )
    keyword_text = (keyword or "").strip()
    district_text = (district or "").strip()
    if keyword_text:
        base = base.where(Company.company_name.ilike(f"%{keyword_text}%"))
    if district_text:
        base = base.where(Company.district == district_text)
    rows = db.scalars(base.order_by(Company.id).limit(limit + 1)).all()
    truncated = len(rows) > limit
    items = rows[:limit]
    return items, truncated


def get_district_company_stats(db: Session, district: str | None = None) -> dict:
    base = select(Company)
    if district:
        base = base.where(Company.district.ilike(f"%{district}%"))
    rows = db.scalars(base).all()

    total = len(rows)
    industry_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    district_counts: dict[str, int] = {}
    for r in rows:
        if r.industry:
            industry_counts[r.industry] = industry_counts.get(r.industry, 0) + 1
        key_status = r.survival_status or "未知"
        status_counts[key_status] = status_counts.get(key_status, 0) + 1
        key_district = r.district or "未知"
        district_counts[key_district] = district_counts.get(key_district, 0) + 1

    return {
        "total": total,
        "by_industry": sorted(industry_counts.items(), key=lambda x: -x[1]),
        "by_status": sorted(status_counts.items(), key=lambda x: -x[1]),
        "by_district": sorted(district_counts.items(), key=lambda x: -x[1]),
    }
