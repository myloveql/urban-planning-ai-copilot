import base64
import binascii
import json
import re
from typing import Any, AsyncIterator

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.diagram import Diagram


class DifyChatService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def is_enabled(self) -> bool:
        return bool(self.settings.dify_base_url and self.settings.dify_api_key)

    def _base_url(self) -> str:
        return self.settings.dify_base_url.rstrip("/")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.settings.dify_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
        }

    @staticmethod
    def _clean_answer(text: str) -> str:
        return re.sub(r"<think>.*?</think>\s*", "", text, flags=re.DOTALL).strip()

    @staticmethod
    def _extract_tool_results(data: dict[str, Any]) -> dict[str, Any]:
        metadata = data.get("metadata")
        return metadata if isinstance(metadata, dict) else {}

    @staticmethod
    def _compose_query(question: str, has_image: bool) -> str:
        if not has_image:
            return question
        return (
            "请优先基于知识库或已接入的规划文本检索直接依据，并明确指出相关文件名、章节或表格。"
            "图片只能作为辅助判断，不能仅凭图片推测规划定位、规划指标或权属结论。"
            "如果知识库没有明确依据，请先明确说明“知识库未检索到直接依据”，再补充图片观察结果。\n"
            f"用户问题：{question}"
        )

    @staticmethod
    def _parse_image_data_url(image_data_url: str, image_name: str | None) -> tuple[str, bytes, str]:
        matched = re.match(r"^data:(image/(png|jpeg|jpg));base64,(.+)$", image_data_url, flags=re.IGNORECASE)
        if not matched:
            raise ValueError("仅支持 jpg/png 格式的图片数据")

        mime_type = matched.group(1).lower().replace("jpg", "jpeg")
        extension = "png" if mime_type.endswith("png") else "jpg"
        filename = image_name.strip() if image_name else f"chat-image.{extension}"
        if "." not in filename:
            filename = f"{filename}.{extension}"

        try:
            content = base64.b64decode(matched.group(3), validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("图片数据解析失败") from exc

        return filename, content, mime_type

    def _build_inputs(
        self,
        diagram: Diagram,
        question: str,
        shape: dict[str, Any] | None,
        task_hint: str | None,
    ) -> dict[str, Any]:
        inputs: dict[str, Any] = {}

        question_field = self.settings.dify_question_field.strip()
        shape_field = self.settings.dify_shape_field.strip()
        diagram_id_field = self.settings.dify_diagram_id_field.strip()

        if question_field:
            inputs[question_field] = question
        inputs.setdefault("task_hint", (task_hint or self.settings.dify_task_hint).strip())

        if shape is not None:
            serialized_shape = json.dumps(shape, ensure_ascii=False)
            inputs[shape_field or "shape"] = serialized_shape

        inputs[diagram_id_field or "diagram_id"] = diagram.id
        inputs.setdefault("diagram_filename", diagram.filename)
        return inputs

    async def _upload_image_file(
        self,
        *,
        image_data_url: str,
        image_name: str | None,
        user: str,
    ) -> dict[str, Any]:
        filename, content, mime_type = self._parse_image_data_url(image_data_url, image_name)
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self._base_url()}/files/upload",
                headers={"Authorization": f"Bearer {self.settings.dify_api_key}"},
                data={"user": user},
                files={"file": (filename, content, mime_type)},
            )

        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Dify 图片上传失败：{response.text}")

        result = response.json()
        file_id = result.get("id")
        if not isinstance(file_id, str) or not file_id:
            raise HTTPException(status_code=502, detail="Dify 图片上传返回缺少文件 id")

        return {
            "type": "image",
            "transfer_method": "local_file",
            "upload_file_id": file_id,
        }

    async def ask(
        self,
        db: Session,
        diagram_id: int,
        question: str,
        shape: dict[str, Any] | None,
        task_hint: str | None = None,
        conversation_id: str | None = None,
        image_data_url: str | None = None,
        image_name: str | None = None,
        map_bbox: dict[str, Any] | None = None,
        map_selection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        diagram = db.get(Diagram, diagram_id)
        if diagram is None:
            raise ValueError("图纸不存在")
        if not self.is_enabled():
            raise RuntimeError("Dify 对话应用未配置")

        user = f"diagram-{diagram.id}"
        query_text = self._compose_query(question, bool(image_data_url))
        payload = {
            "inputs": self._build_inputs(diagram, query_text, shape, task_hint),
            "query": query_text,
            "response_mode": "blocking",
            "conversation_id": conversation_id or "",
            "user": user,
        }
        if image_data_url:
            payload["files"] = [
                await self._upload_image_file(image_data_url=image_data_url, image_name=image_name, user=user)
            ]

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{self._base_url()}/chat-messages",
                headers=self._headers(),
                json=payload,
            )

        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"Dify 调用失败：{response.text}")

        result = response.json()
        return {
            "answer": self._clean_answer(str(result.get("answer", ""))),
            "intent": {"source": "dify-chat"},
            "tool_results": self._extract_tool_results(result),
            "conversation_id": result.get("conversation_id"),
        }

    async def ask_stream(
        self,
        db: Session,
        diagram_id: int,
        question: str,
        shape: dict[str, Any] | None,
        task_hint: str | None = None,
        conversation_id: str | None = None,
        image_data_url: str | None = None,
        image_name: str | None = None,
        map_bbox: dict[str, Any] | None = None,
        map_selection: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "status", "stage": "classify", "message": "正在连接 Dify 对话应用"}
        yield {"type": "status", "stage": "answer", "message": "正在等待 Dify 返回结果"}
        result = await self.ask(
            db=db,
            diagram_id=diagram_id,
            question=question,
            shape=shape,
            task_hint=task_hint,
            conversation_id=conversation_id,
            image_data_url=image_data_url,
            image_name=image_name,
        )
        yield {
            "type": "final",
            "answer": result["answer"],
            "intent": result["intent"],
            "tool_results": result["tool_results"],
            "conversation_id": result.get("conversation_id"),
        }
