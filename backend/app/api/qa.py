import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.qa import AskRequest, AskResponse
from app.services.agent_service import PlanningAgentService
from app.services.dify_chat_service import DifyChatService

router = APIRouter(prefix="/qa", tags=["qa"])
agent = PlanningAgentService()
dify_agent = DifyChatService()

AREA_TASK_HINT = "计算面积"
TEXT_TASK_HINT = "规划文本问答"
INDUSTRY_TASK_HINT = "企业关联分析"
ANALYSIS_TASK_HINT = "数据分析问答"
AREA_KEYWORDS = (
    "面积",
    "面积统计",
    "用地面积",
    "用地平衡",
    "用地平衡表",
    "平衡表",
    "用地构成",
    "地类构成",
    "地类平衡",
    "用地分类统计",
    "圈选面积",
    "计算面积",
    "测算面积",
    "统计面积",
    "面积构成",
    "面积占比",
)
AREA_SHAPE_KEYWORDS = ("多大", "多少平方米", "多少平米", "多少公顷", "多大面积")


def infer_task_hint(question: str, shape: object | None) -> str | None:
    normalized = question.strip().lower()
    if any(keyword in normalized for keyword in AREA_KEYWORDS):
        return AREA_TASK_HINT
    if shape is not None and any(keyword in normalized for keyword in AREA_SHAPE_KEYWORDS):
        return AREA_TASK_HINT
    return None


def resolve_service(task_hint: str | None, question: str, shape: object | None, image_data_url: str | None):
    if image_data_url:
        return (dify_agent if dify_agent.is_enabled() else agent), task_hint

    effective_task_hint = task_hint or infer_task_hint(question, shape)
    if effective_task_hint == AREA_TASK_HINT:
        return agent, effective_task_hint

    if effective_task_hint == INDUSTRY_TASK_HINT:
        return agent, effective_task_hint

    if effective_task_hint == ANALYSIS_TASK_HINT:
        return agent, effective_task_hint

    # Knowledge base uses Dify
    if effective_task_hint == TEXT_TASK_HINT:
        return (dify_agent if dify_agent.is_enabled() else agent), effective_task_hint

    if effective_task_hint is None:
        effective_task_hint = TEXT_TASK_HINT

    return agent, effective_task_hint


@router.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest, db: Session = Depends(get_db)):
    try:
        service, effective_task_hint = resolve_service(
            request.task_hint,
            request.question,
            request.shape,
            request.image_data_url,
        )
        return await service.ask(
            db=db,
            diagram_id=request.diagram_id,
            question=request.question,
            shape=request.shape.model_dump(exclude_none=True) if request.shape is not None else None,
            task_hint=effective_task_hint,
            conversation_id=request.conversation_id,
            image_data_url=request.image_data_url,
            image_name=request.image_name,
            map_bbox=request.map_bbox.model_dump() if request.map_bbox is not None else None,
            map_selection=request.map_selection.model_dump(exclude_none=True) if request.map_selection is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/ask/stream")
async def ask_stream(request: AskRequest, db: Session = Depends(get_db)):
    async def event_generator():
        try:
            service, effective_task_hint = resolve_service(
                request.task_hint,
                request.question,
                request.shape,
                request.image_data_url,
            )
            async for event in service.ask_stream(
                db=db,
                diagram_id=request.diagram_id,
                question=request.question,
                shape=request.shape.model_dump(exclude_none=True) if request.shape is not None else None,
                task_hint=effective_task_hint,
                conversation_id=request.conversation_id,
                image_data_url=request.image_data_url,
                image_name=request.image_name,
                map_bbox=request.map_bbox.model_dump() if request.map_bbox is not None else None,
                map_selection=request.map_selection.model_dump(exclude_none=True) if request.map_selection is not None else None,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except ValueError as exc:
            error_event = {"type": "error", "message": str(exc)}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        except HTTPException as exc:
            error_event = {"type": "error", "message": str(exc.detail)}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"
        except Exception as exc:
            error_event = {"type": "error", "message": f"流式问答失败：{exc}"}
            yield f"data: {json.dumps(error_event, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
