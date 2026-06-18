from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_company_db
from app.schemas.poi import PoiCategoryListOut, PoiListOut
from app.services.poi_service import DEFAULT_QUERY_LIMIT, get_district_poi_stats, list_poi_categories, query_pois_in_bbox

router = APIRouter(prefix="/pois", tags=["pois"])


@router.get("", response_model=PoiListOut)
def list_pois(
    min_lng: float = Query(...),
    min_lat: float = Query(...),
    max_lng: float = Query(...),
    max_lat: float = Query(...),
    limit: int = Query(default=DEFAULT_QUERY_LIMIT, ge=1, le=5000),
    categories: list[str] = Query(default=[]),
    db: Session = Depends(get_company_db),
):
    items, truncated = query_pois_in_bbox(
        db,
        min_lng=min_lng,
        min_lat=min_lat,
        max_lng=max_lng,
        max_lat=max_lat,
        categories=categories,
        limit=limit,
    )
    return {
        "items": [
            {
                "id": item.id,
                "name": item.name,
                "district": item.district,
                "major_category": item.major_category,
                "middle_category": item.middle_category,
                "minor_category": item.minor_category,
                "lng": item.lng,
                "lat": item.lat,
            }
            for item in items
        ],
        "total": len(items),
        "truncated": truncated,
    }


@router.get("/district-stats")
def poi_district_stats(
    district: str | None = Query(default=None),
    db: Session = Depends(get_company_db),
):
    return get_district_poi_stats(db, district)


@router.get("/categories", response_model=PoiCategoryListOut)
def get_poi_categories(db: Session = Depends(get_company_db)):
    items = list_poi_categories(db)
    return {"items": [{"name": name, "count": count} for name, count in items]}
