from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_company_db
from app.schemas.company import CompanyDetailOut, CompanyListOut
from app.services.company_service import DEFAULT_QUERY_LIMIT, get_company_by_id, get_district_company_stats, query_companies_in_bbox

router = APIRouter(prefix="/companies", tags=["companies"])


@router.get("", response_model=CompanyListOut)
def list_companies(
    min_lng: float = Query(...),
    min_lat: float = Query(...),
    max_lng: float = Query(...),
    max_lat: float = Query(...),
    limit: int = Query(default=DEFAULT_QUERY_LIMIT, ge=1, le=2000),
    keyword: str | None = Query(default=None),
    district: str | None = Query(default=None),
    db: Session = Depends(get_company_db),
):
    items, truncated = query_companies_in_bbox(
        db,
        min_lng=min_lng,
        min_lat=min_lat,
        max_lng=max_lng,
        max_lat=max_lat,
        limit=limit,
        keyword=keyword,
        district=district,
    )
    return {
        "items": [
            {
                "id": item.id,
                "company_name": item.company_name,
                "district": item.district,
                "industry": item.industry,
                "lng": item.lng,
                "lat": item.lat,
                "survival_status": item.survival_status,
            }
            for item in items
        ],
        "total": len(items),
        "truncated": truncated,
    }


@router.get("/district-stats")
def company_district_stats(
    district: str | None = Query(default=None),
    db: Session = Depends(get_company_db),
):
    return get_district_company_stats(db, district)


@router.get("/{company_id}", response_model=CompanyDetailOut)
def get_company_detail(company_id: int, db: Session = Depends(get_company_db)):
    item = get_company_by_id(db, company_id)
    if item is None:
        raise HTTPException(status_code=404, detail="企业不存在")
    return {
        "id": item.id,
        "company_name": item.company_name,
        "status": item.status,
        "legal_representative": item.legal_representative,
        "registered_capital": item.registered_capital,
        "paid_in_capital": item.paid_in_capital,
        "established_at": item.established_at,
        "district": item.district,
        "industry": item.industry,
        "company_type": item.company_type,
        "insured_count": item.insured_count,
        "address": item.address,
        "business_scope": item.business_scope,
        "lng": item.lng,
        "lat": item.lat,
        "survival_status": item.survival_status,
    }
