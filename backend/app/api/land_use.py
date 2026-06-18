from fastapi import APIRouter, HTTPException

from app.services.land_use_service import get_land_use_dataset

router = APIRouter(prefix="/land-use", tags=["land-use"])


@router.get("")
def get_land_use():
    try:
        dataset = get_land_use_dataset()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"土地利用数据加载失败: {exc}") from exc
    return {
        "geojson": dataset.geojson,
        "meta": dataset.meta,
    }
