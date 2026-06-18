import json

from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.diagram import Diagram
from app.schemas.diagram import DiagramListOut, DiagramOut, DiagramRenameRequest, ScaleCalibrationRequest
from app.services.diagram_service import DiagramService, diagram_to_dict
from app.services.legend_service import calibrate_legend_colors, summarize_legend_calibration_debug

router = APIRouter(prefix="/diagrams", tags=["diagrams"])


@router.post("", response_model=DiagramOut)
async def upload_diagram(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        diagram = await DiagramService().create_from_upload(db, file)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return diagram_to_dict(diagram)


@router.get("", response_model=DiagramListOut)
def list_diagrams(db: Session = Depends(get_db)):
    items = db.scalars(select(Diagram).order_by(Diagram.created_at.desc())).all()
    return {"items": [diagram_to_dict(item) for item in items]}


@router.get("/{diagram_id}", response_model=DiagramOut)
def get_diagram(diagram_id: int, db: Session = Depends(get_db)):
    diagram = db.get(Diagram, diagram_id)
    if diagram is None:
        raise HTTPException(status_code=404, detail="图纸不存在")
    return diagram_to_dict(diagram)


@router.get("/{diagram_id}/image")
def get_diagram_image(diagram_id: int, db: Session = Depends(get_db)):
    diagram = db.get(Diagram, diagram_id)
    if diagram is None:
        raise HTTPException(status_code=404, detail="图纸不存在")
    path = diagram.processed_path or diagram.original_path
    return FileResponse(path)


@router.patch("/{diagram_id}", response_model=DiagramOut)
def rename_diagram(diagram_id: int, payload: DiagramRenameRequest, db: Session = Depends(get_db)):
    diagram = db.get(Diagram, diagram_id)
    if diagram is None:
        raise HTTPException(status_code=404, detail="图纸不存在")
    filename = payload.filename.strip()
    if not filename:
        raise HTTPException(status_code=400, detail="图纸名称不能为空")
    diagram.filename = filename
    db.add(diagram)
    db.commit()
    db.refresh(diagram)
    return diagram_to_dict(diagram)


@router.delete("/{diagram_id}")
def delete_diagram(diagram_id: int, db: Session = Depends(get_db)):
    diagram = db.get(Diagram, diagram_id)
    if diagram is None:
        raise HTTPException(status_code=404, detail="图纸不存在")
    original_path = Path(diagram.original_path)
    processed_path = Path(diagram.processed_path) if diagram.processed_path else None
    db.delete(diagram)
    db.commit()
    try:
        if original_path.exists():
            original_path.unlink()
        if processed_path and processed_path.exists():
            processed_path.unlink()
    except OSError:
        pass
    return {"ok": True}


@router.post("/{diagram_id}/recalibrate-legend", response_model=DiagramOut)
def recalibrate_legend(diagram_id: int, db: Session = Depends(get_db)):
    diagram = db.get(Diagram, diagram_id)
    if diagram is None:
        raise HTTPException(status_code=404, detail="图纸不存在")
    legend = diagram_to_dict(diagram)["legend_json"]
    if not legend:
        raise HTTPException(status_code=400, detail="当前图纸没有可校准的图例JSON")
    image_path = diagram.processed_path or diagram.original_path
    calibrated_legend, calibration_debug = calibrate_legend_colors(image_path, legend)
    scale = diagram_to_dict(diagram)["scale_json"]
    calibration_summary = summarize_legend_calibration_debug(calibration_debug)
    scale["legend_calibration_status"] = {
        "enabled": True,
        "items": len(calibrated_legend),
        "source": "manual_api",
        "method": calibration_summary.get("summary", {}).get("method"),
    }
    scale["legend_calibration_debug"] = calibration_summary
    diagram.legend_json = json.dumps(calibrated_legend, ensure_ascii=False)
    diagram.scale_json = json.dumps(scale, ensure_ascii=False)
    db.add(diagram)
    db.commit()
    db.refresh(diagram)
    return diagram_to_dict(diagram)


@router.post("/{diagram_id}/calibrate-scale", response_model=DiagramOut)
def calibrate_scale(diagram_id: int, payload: ScaleCalibrationRequest, db: Session = Depends(get_db)):
    diagram = db.get(Diagram, diagram_id)
    if diagram is None:
        raise HTTPException(status_code=404, detail="图纸不存在")

    scale = diagram_to_dict(diagram)["scale_json"]
    meters_per_pixel = payload.meters_per_pixel
    if meters_per_pixel is None:
        if payload.reference_distance_meters is None or payload.reference_pixel_length is None:
            raise HTTPException(status_code=400, detail="请提供 meters_per_pixel 或者参考距离与像素长度")
        if payload.reference_distance_meters <= 0 or payload.reference_pixel_length <= 0:
            raise HTTPException(status_code=400, detail="参考距离和像素长度必须大于0")
        meters_per_pixel = payload.reference_distance_meters / payload.reference_pixel_length
    if meters_per_pixel <= 0:
        raise HTTPException(status_code=400, detail="meters_per_pixel 必须大于0")

    scale["meters_per_pixel"] = meters_per_pixel
    if payload.scale_text is not None and payload.scale_text.strip():
        scale["scale_text"] = payload.scale_text.strip()
    scale["manual_calibration"] = {
        "enabled": True,
        "meters_per_pixel": meters_per_pixel,
        "reference_distance_meters": payload.reference_distance_meters,
        "reference_pixel_length": payload.reference_pixel_length,
        "source": "manual_api",
    }
    diagram.scale_json = json.dumps(scale, ensure_ascii=False)
    db.add(diagram)
    db.commit()
    db.refresh(diagram)
    return diagram_to_dict(diagram)
