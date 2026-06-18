import asyncio
import json
from typing import Any, AsyncIterator, TypedDict

from langgraph.graph import END, StateGraph
from sqlalchemy.orm import Session

from app.models.diagram import Diagram
from app.services.llm_service import LLMService
from app.tools.amap import amap_tool
from app.tools.area_calculation import calculate_land_area, normalize_shape_payload
from app.tools.industry_relation import industry_relation_tool
from app.tools.industry_direction import industry_direction_tool
from app.tools.knowledge_base import knowledge_base_tool

AREA_TASK_HINT = "计算面积"
INDUSTRY_TASK_HINT = "企业关联分析"
DEV_DIRECTION_HINT = "产业发展方向分析"


class AgentState(TypedDict, total=False):
    question: str
    diagram: Diagram
    shape: dict[str, Any] | None
    intent: dict[str, Any]
    tool_results: dict[str, Any]
    answer: str


class PlanningAgentService:
    def __init__(self) -> None:
        self.llm = LLMService()
        self.graph = self._build_graph()

    @staticmethod
    def _should_run_tools(state: AgentState) -> str:
        tools = state.get("intent", {}).get("tools", [])
        if tools:
            return "tools"
        return "compose_answer"

    def _build_graph(self):
        graph = StateGraph(AgentState)
        graph.add_node("classify", self._classify)
        graph.add_node("tools", self._run_tools)
        graph.add_node("compose_answer", self._answer)
        graph.set_entry_point("classify")
        graph.add_conditional_edges("classify", self._should_run_tools, {"tools": "tools", "compose_answer": "compose_answer"})
        graph.add_edge("tools", "compose_answer")
        graph.add_edge("compose_answer", END)
        return graph.compile()

    async def _classify(self, state: AgentState) -> AgentState:
        state["intent"] = await self.llm.classify_intent(state["question"])
        return state

    async def _run_tools(self, state: AgentState) -> AgentState:
        diagram = state["diagram"]
        question = state["question"]
        tools = state.get("intent", {}).get("tools", [])
        results: dict[str, Any] = {}
        legend = json.loads(diagram.legend_json or "{}")
        scale = json.loads(diagram.scale_json or "{}")
        meters_per_pixel = float(scale.get("meters_per_pixel") or 1.0)

        if "area_calculation" in tools:
            if not state.get("shape"):
                results["area_calculation"] = {
                    "status": "missing_shape",
                    "message": "请先在图纸上圈选需要统计面积的区域。",
                }
            elif not legend:
                results["area_calculation"] = {
                    "status": "missing_legend",
                    "message": "当前图纸缺少图例信息，无法执行面积计算。",
                }
            else:
                results["area_calculation"] = calculate_land_area(
                    image_path=diagram.processed_path or diagram.original_path,
                    shape_payload=normalize_shape_payload(state["shape"]),
                    legend=legend,
                    meters_per_pixel=meters_per_pixel,
                )

        if "amap" in tools:
            results["amap"] = await amap_tool(question, {"diagram_id": diagram.id})
        if "knowledge_base" in tools:
            results["knowledge_base"] = await knowledge_base_tool(question, {"diagram_id": diagram.id})
        if "industry_relation" in tools:
            industry_name = state.get("intent", {}).get("industry", question)
            district = state.get("intent", {}).get("district")
            ctx: dict[str, Any] = {"industry": industry_name, "question": question}
            if district:
                ctx["district"] = district
            results["industry_relation"] = await industry_relation_tool(question, ctx)
        state["tool_results"] = results
        return state

    async def _answer(self, state: AgentState) -> AgentState:
        context = {"intent": state.get("intent", {}), "tool_results": state.get("tool_results", {})}
        state["answer"] = await self.llm.synthesize_answer(state["question"], context)
        return state

    def _run_area_only(self, diagram: Diagram, shape: dict[str, Any] | None) -> dict[str, Any]:
        if not shape:
            return {
                "status": "missing_shape",
                "message": "请先在图纸上圈选需要统计面积的区域。",
            }
        legend = json.loads(diagram.legend_json or "{}")
        if not legend:
            return {
                "status": "missing_legend",
                "message": "当前图纸缺少图例信息，无法执行面积计算。",
            }
        scale = json.loads(diagram.scale_json or "{}")
        meters_per_pixel = float(scale.get("meters_per_pixel") or 1.0)
        return calculate_land_area(
            image_path=diagram.processed_path or diagram.original_path,
            shape_payload=normalize_shape_payload(shape),
            legend=legend,
            meters_per_pixel=meters_per_pixel,
        )

    async def _run_area_only_async(self, diagram: Diagram, shape: dict[str, Any] | None) -> dict[str, Any]:
        return await asyncio.to_thread(self._run_area_only, diagram, shape)

    async def _run_industry_only(self, question: str, map_bbox: dict[str, Any] | None = None, map_selection: dict[str, Any] | None = None) -> dict[str, Any]:
        intent = await self.llm.classify_intent(question)
        industry_name = intent.get("industry", question)
        district = intent.get("district")
        context: dict[str, Any] = {
            "industry": industry_name,
            "question": question,
            "map_bbox": map_bbox,
            "map_selection": map_selection,
        }
        if district:
            context["district"] = district
        tool_result = await industry_relation_tool(question, context)
        return {
            "answer": tool_result.get("summary", ""),
            "intent": {"intent": "industry_relation", "tools": ["industry_relation"], "source": "industry-mode"},
            "tool_results": {"industry_relation": tool_result},
        }

    async def _run_industry_direction_only(self, question: str, map_bbox: dict[str, Any] | None = None, map_selection: dict[str, Any] | None = None) -> dict[str, Any]:
        tool_result = await industry_direction_tool(question, {"question": question, "map_bbox": map_bbox, "map_selection": map_selection})
        return {
            "answer": tool_result.get("summary", ""),
            "intent": {"intent": "industry_direction", "tools": ["industry_direction"], "source": "industry-mode"},
            "tool_results": {"industry_direction": tool_result},
        }

    async def _ask_with_uploaded_image(
        self,
        question: str,
        image_data_url: str,
        image_name: str | None = None,
    ) -> dict[str, Any]:
        answer = await self.llm.answer_with_uploaded_image(question, image_data_url, image_name=image_name)
        return {
            "answer": answer,
            "intent": {"intent": "image_analysis", "tools": [], "source": "local-vision-chat"},
            "tool_results": {"uploaded_image": {"filename": image_name or "uploaded-image", "status": "analyzed"}},
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
        if image_data_url:
            return await self._ask_with_uploaded_image(question, image_data_url, image_name=image_name)
        if task_hint == AREA_TASK_HINT:
            area_result = await self._run_area_only_async(diagram, shape)
            return {
                "answer": area_result.get("message", "面积统计已完成。"),
                "intent": {"intent": "area", "tools": ["area_calculation"], "source": "local-area"},
                "tool_results": {"area_calculation": area_result},
            }
        if task_hint == INDUSTRY_TASK_HINT:
            return await self._run_industry_only(question, map_bbox=map_bbox, map_selection=map_selection)
        if task_hint == DEV_DIRECTION_HINT:
            return await self._run_industry_direction_only(question, map_bbox=map_bbox, map_selection=map_selection)
        result = await self.graph.ainvoke({"diagram": diagram, "question": question, "shape": shape})
        return {
            "answer": result.get("answer", ""),
            "intent": result.get("intent", {}),
            "tool_results": result.get("tool_results", {}),
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
        diagram = db.get(Diagram, diagram_id)
        if diagram is None:
            raise ValueError("图纸不存在")

        if image_data_url:
            yield {"type": "status", "stage": "tools", "message": "正在分析上传图片"}
            result = await self._ask_with_uploaded_image(question, image_data_url, image_name=image_name)
            yield {
                "type": "final",
                "answer": result["answer"],
                "intent": result["intent"],
                "tool_results": result["tool_results"],
            }
            return

        if task_hint == AREA_TASK_HINT:
            yield {"type": "status", "stage": "tools", "message": "正在执行面积统计"}
            area_result = await self._run_area_only_async(diagram, shape)
            yield {
                "type": "tool_result",
                "tool": "area_calculation",
                "result": area_result,
                "message": "area_calculation 已完成",
            }
            yield {"type": "tool_results", "tool_results": {"area_calculation": area_result}}
            yield {
                "type": "final",
                "answer": area_result.get("message", "面积统计已完成。"),
                "intent": {"intent": "area", "tools": ["area_calculation"], "source": "local-area"},
                "tool_results": {"area_calculation": area_result},
            }
            return

        if task_hint == INDUSTRY_TASK_HINT:
            yield {"type": "status", "stage": "tools", "message": "正在执行产业关联分析"}
            industry_result = await self._run_industry_only(question, map_bbox=map_bbox, map_selection=map_selection)
            intent_data = industry_result.get("intent", {})
            tool_data = industry_result.get("tool_results", {})
            for tool, result in tool_data.items():
                yield {"type": "tool_result", "tool": tool, "result": result, "message": f"{tool} 已完成"}
            yield {"type": "tool_results", "tool_results": tool_data}
            yield {"type": "status", "stage": "answer", "message": "正在组织规划答复"}
            context = {"intent": intent_data, "tool_results": tool_data}
            answer_parts: list[str] = []
            async for delta in self.llm.stream_synthesize_answer(question, context):
                answer_parts.append(delta)
                yield {"type": "answer_delta", "delta": delta}
            yield {
                "type": "final",
                "answer": "".join(answer_parts),
                "intent": intent_data,
                "tool_results": tool_data,
            }
            return

        if task_hint == DEV_DIRECTION_HINT:
            yield {"type": "status", "stage": "tools", "message": "正在分析区域产业发展方向"}
            dir_result = await self._run_industry_direction_only(question, map_bbox=map_bbox, map_selection=map_selection)
            intent_data = dir_result.get("intent", {})
            tool_data = dir_result.get("tool_results", {})
            for tool, result in tool_data.items():
                yield {"type": "tool_result", "tool": tool, "result": result, "message": f"{tool} 已完成"}
            yield {"type": "tool_results", "tool_results": tool_data}
            yield {"type": "status", "stage": "answer", "message": "正在组织规划答复"}
            context = {"intent": intent_data, "tool_results": tool_data}
            answer_parts: list[str] = []
            async for delta in self.llm.stream_synthesize_answer(question, context):
                answer_parts.append(delta)
                yield {"type": "answer_delta", "delta": delta}
            yield {
                "type": "final",
                "answer": "".join(answer_parts),
                "intent": intent_data,
                "tool_results": tool_data,
            }
            return

        state: AgentState = {"diagram": diagram, "question": question, "shape": shape}
        yield {"type": "status", "stage": "classify", "message": "正在识别提问信息"}
        state = await self._classify(state)
        tools = state.get("intent", {}).get("tools", [])
        yield {
            "type": "intent",
            "intent": state.get("intent", {}),
            "message": f"已识别工具链：{', '.join(tools) or '无（直接问答）'}",
        }

        tool_results: dict[str, Any] = {}
        if tools:
            yield {"type": "status", "stage": "tools", "message": "正在执行规划分析工具"}
            state = await self._run_tools(state)
            tool_results = state.get("tool_results", {})
            for tool, result in tool_results.items():
                yield {
                    "type": "tool_result",
                    "tool": tool,
                    "result": result,
                    "message": f"{tool} 已完成",
                }
            yield {"type": "tool_results", "tool_results": tool_results}
        else:
            yield {"type": "status", "stage": "answer", "message": "正在思考回答"}

        yield {"type": "status", "stage": "answer", "message": "正在组织规划答复" if tools else "正在生成回答"}
        context = {"intent": state.get("intent", {}), "tool_results": tool_results}
        answer_parts: list[str] = []
        async for delta in self.llm.stream_synthesize_answer(question, context):
            answer_parts.append(delta)
            yield {"type": "answer_delta", "delta": delta}
        answer = "".join(answer_parts)
        yield {
            "type": "final",
            "answer": answer,
            "intent": state.get("intent", {}),
            "tool_results": tool_results,
        }
