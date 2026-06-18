import json
import shutil
from pathlib import Path
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import is_image_file
from app.models.diagram import Diagram
from app.services.llm_service import LLMService
from app.services.legend_service import calibrate_legend_colors, summarize_legend_calibration_debug
from app.services.scale_service import estimate_scale_from_image


def diagram_to_dict(diagram: Diagram) -> dict:
    return {
        "id": diagram.id,
        "filename": diagram.filename,
        "original_path": diagram.original_path,
        "processed_path": diagram.processed_path,
        "legend_json": json.loads(diagram.legend_json or "{}"),
        "scale_json": json.loads(diagram.scale_json or "{}"),
        "image_width": diagram.image_width,
        "image_height": diagram.image_height,
        "created_at": diagram.created_at,
        "updated_at": diagram.updated_at,
    }


class DiagramService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.llm = LLMService()

    async def create_from_upload(self, db: Session, file: UploadFile) -> Diagram:
        if not file.filename or not is_image_file(file.filename):
            raise ValueError("当前MVP仅支持PNG/JPG等图片格式图纸")

        suffix = Path(file.filename).suffix.lower()
        stem = uuid4().hex
        original_path = self.settings.upload_dir / f"{stem}{suffix}"
        processed_path = self.settings.processed_dir / f"{stem}.png"

        with original_path.open("wb") as output:
            shutil.copyfileobj(file.file, output)

        with Image.open(original_path) as image:
            rgba = image.convert("RGBA")
            width, height = rgba.size
            rgba.save(processed_path)

        legend, scale = await self.llm.identify_legend_and_scale(processed_path)
        legend, legend_calibration = calibrate_legend_colors(processed_path, legend)
        scale = estimate_scale_from_image(processed_path, scale)
        calibration_summary = summarize_legend_calibration_debug(legend_calibration)
        scale["legend_calibration_status"] = {
            "enabled": True,
            "items": len(legend),
            "source": "upload_pipeline",
            "method": calibration_summary.get("summary", {}).get("method"),
        }
        scale["legend_calibration_debug"] = calibration_summary
        diagram = Diagram(
            filename=file.filename,
            original_path=str(original_path),
            processed_path=str(processed_path),
            legend_json=json.dumps(legend, ensure_ascii=False),
            scale_json=json.dumps(scale, ensure_ascii=False),
            image_width=width,
            image_height=height,
        )
        db.add(diagram)
        db.commit()
        db.refresh(diagram)
        return diagram
