import base64
import asyncio
import json
import logging
from pathlib import Path
from typing import Any, AsyncIterator

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_AREA_KEYWORDS = (
    "面积", "用地面积", "用地平衡", "平衡表", "用地构成", "地类构成",
    "地类平衡", "用地分类统计", "圈选面积", "计算面积", "测算面积",
    "统计面积", "面积构成", "面积占比", "多大", "多少平方米", "多少平米",
    "多少公顷", "多大面积", "用地", "面积统计",
)
_MAP_KEYWORDS = (
    "路线", "导航", "怎么走", "周边", "附近", "位置", "在哪", "地址",
    "距离", "多远", "交通", "地铁", "公交", "道路", "高速", "路口",
    " POI", "兴趣点", "设施", "配套",
)
_KB_KEYWORDS = (
    "规范", "政策", "法规", "标准", "条例", "规定", "历史", "资料",
    "文件", "规划文本", "控规", "总规", "专项规划", "国土空间规划",
    "容积率", "建筑密度", "限高", "绿地率",
)
_INDUSTRY_KEYWORDS = (
    "产业链", "上下游", "产业关联", "产业基础", "产业集聚", "产业发展",
    "产业集群", "产业链条", "行业分析", "产业配套", "关联产业",
)

_DISTRICT_PATTERNS = (
    "三水区", "南海区", "禅城区", "顺德区", "高明区",
    "乐平镇", "西南街道", "云东海街道", "白坭镇", "芦苞镇",
    "大塘镇", "南山镇",
)


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _chat(self, model: str | None = None) -> ChatOpenAI | None:
        if not self.settings.llm_api_key:
            return None
        return ChatOpenAI(
            model=model or self.settings.llm_model,
            api_key=self.settings.llm_api_key,
            base_url=self.settings.llm_base_url,
            temperature=0.1,
        )

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.lower().startswith("json"):
                stripped = stripped[4:].strip()
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start >= 0 and end >= start:
            stripped = stripped[start : end + 1]
        return json.loads(stripped)

    @staticmethod
    def _keyword_fallback(question: str) -> dict[str, Any]:
        q = question.lower()
        tools = []
        district = next((d for d in _DISTRICT_PATTERNS if d in question), None)
        if any(kw in q for kw in _INDUSTRY_KEYWORDS):
            result: dict[str, Any] = {"intent": "industry_relation", "tools": ["industry_relation"], "industry": question, "reason": "LLM不可用，关键词匹配到产业关联分析"}
            if district:
                result["district"] = district
            return result
        if any(kw in q for kw in _AREA_KEYWORDS):
            tools.append("area_calculation")
        if any(kw in q for kw in _MAP_KEYWORDS):
            tools.append("amap")
        if any(kw in q for kw in _KB_KEYWORDS):
            tools.append("knowledge_base")
        if not tools:
            return {"intent": "general", "tools": [], "reason": "LLM不可用且无关键词匹配，按通用问答处理"}
        return {"intent": "keyword_fallback", "tools": tools, "reason": "LLM不可用，已通过关键词匹配推断意图"}

    async def identify_legend_and_scale(self, image_path: Path) -> tuple[dict[str, str], dict[str, Any]]:
        chat = self._chat(self.settings.llm_vision_model)
        if chat is None:
            return {}, {"source": "fallback", "meters_per_pixel": 1.0, "note": "未配置LLM_API_KEY，默认1像素=1米"}

        image_data = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        prompt = (
            "你是规划图纸识别助手。请优先观察图纸中的图例框，并完整提取所有可见图例项和比例尺。"
            "要求：1. 图例项必须逐项抄录，保持原有类别文字，不要合并相近类别，不要省略低占比类别。"
            "2. 每个图例类别都返回其对应的实际填充颜色，使用十六进制RGB，例如#AABBCC。"
            "3. 若同一类别存在边框色和填充色，只返回填充色。"
            "4. 比例尺请优先抄录原始文字，例如0 500m 1000m。"
            "5. 若无法可靠直接换算meters_per_pixel，则返回null，后端会继续做图像测量。"
            "6. 只输出JSON，不要输出解释。"
            "输出格式：{\"legend\":{\"类别1\":\"#RRGGBB\"},\"scale\":{\"meters_per_pixel\":number|null,\"scale_text\":string|null,\"confidence\":0-1}}"
        )
        message = HumanMessage(
            content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image_data}"}},
            ]
        )
        try:
            response = await chat.ainvoke([message])
        except Exception as exc:
            logger.warning("视觉模型识别失败: %s", exc)
            return {}, {
                "source": "llm_request_failed",
                "meters_per_pixel": 1.0,
                "note": "视觉模型识别失败，已降级为默认比例尺，可在图例和比例尺面板手动校准。",
                "error": str(exc),
            }
        try:
            parsed = self._extract_json(str(response.content))
        except Exception:
            return {}, {"source": "llm_parse_failed", "meters_per_pixel": 1.0, "raw": str(response.content)}

        legend = parsed.get("legend") or {}
        scale = parsed.get("scale") or {}
        if not isinstance(legend, dict):
            legend = {}
        if not isinstance(scale, dict):
            scale = {}
        if not scale.get("meters_per_pixel"):
            scale["meters_per_pixel"] = 1.0
            scale["note"] = "LLM未能确定比例尺，已使用默认值，可在数据库中修正"
        return {str(k): str(v).upper() for k, v in legend.items()}, scale

    async def classify_intent(self, question: str) -> dict[str, Any]:
        chat = self._chat()
        if chat is None:
            return self._keyword_fallback(question)
        system = SystemMessage(
            content="你是规划AI总师的意图识别器。可用工具：area_calculation、amap、knowledge_base、industry_relation。只输出JSON。"
        )
        human = HumanMessage(
            content=(
                f"用户问题：{question}\n"
                "判断需要调用哪些工具：\n"
                "- 面积/用地/圈选统计 → area_calculation\n"
                "- 地理位置/路线/周边 → amap\n"
                "- 规范/政策/历史资料 → knowledge_base\n"
                "- 产业链/上下游/产业关联/产业基础/产业集聚/行业发展 → industry_relation\n"
                '- 如果问题与以上工具均无关（如一般性提问、闲聊、解释概念等），tools设为空数组[]，intent设为"general"\n'
                '如果调用了industry_relation，必须额外输出"industry"字段，值为用户查询的产业名称（如新能源汽车、电子信息、食品加工）。\n'
                '如果用户问题包含地区或区域信息（如三水区、南海区、乐平镇、西南街道、产业园等），输出"district"字段，值为提取的地区名称。无法识别则不输出。\n'
                "输出格式：{\"intent\":\"...\",\"tools\":[...],\"industry\":\"...\",\"district\":\"...\",\"reason\":\"...\"}"
            )
        )
        try:
            response = await chat.ainvoke([system, human])
        except Exception as exc:
            logger.warning("LLM意图识别调用失败，降级为关键词匹配: %s", exc)
            return self._keyword_fallback(question)
        try:
            parsed = self._extract_json(str(response.content))
        except Exception:
            parsed = {"intent": "general", "tools": [], "reason": str(response.content)}
        tools = parsed.get("tools") if isinstance(parsed.get("tools"), list) else []
        result: dict[str, Any] = {"intent": parsed.get("intent", "general"), "tools": tools, "reason": parsed.get("reason", "")}
        if "industry" in parsed and parsed["industry"]:
            result["industry"] = parsed["industry"]
        if "district" in parsed and parsed["district"]:
            result["district"] = parsed["district"]
        return result

    @staticmethod
    def _is_industry_report(context: dict[str, Any]) -> bool:
        return "industry_relation" in context.get("tool_results", {})

    @staticmethod
    def _is_industry_judgment(question: str, context: dict[str, Any]) -> bool:
        if "industry_relation" not in context.get("tool_results", {}):
            return False
        judgment_keywords = (
            "是否适合", "是否具备条件", "具备条件", "发展前景",
            "产业定位", "招商方向", "规划建议", "是否可行",
            "能不能", "值不值得", "有没有条件", "适合不适合",
            "建议", "前景", "可行性",
        )
        return any(kw in question for kw in judgment_keywords)

    @staticmethod
    def _is_industry_direction(context: dict[str, Any]) -> bool:
        return "industry_direction" in context.get("tool_results", {})

    @staticmethod
    def _industry_direction_prompt() -> str:
        return (
            "你是一位区域产业规划咨询专家，正在基于产业数据分析结果撰写区域产业发展方向建议报告。\n\n"
            "报告结构（必须严格按此结构输出）：\n\n"
            "一、区域产业概况\n"
            "用2-3句话概括区域企业总数、产业覆盖面和总体特征。\n\n"
            "二、优势产业分析\n"
            "列出综合评分排名前3-5的产业，每个产业用2-3句话说明：\n"
            "- 产业基础情况（企业数量）\n"
            "- 产业链完整程度\n"
            "- 集聚程度\n"
            "- 与上下游的关联强度\n\n"
            "三、产业链机会分析\n"
            "针对排名靠前的产业，指出：\n"
            "- 已有较好基础但存在短板的环节（补链机会）\n"
            "- 具有发展潜力但目前企业较少的环节（招商机会）\n"
            "- 上下游配套较为完整的环节（强链方向）\n\n"
            "四、服务配套评价\n"
            "基于区域内POI数据，评价商业、金融、教育、医疗等服务配套对产业发展的支撑能力。\n\n"
            "五、产业招商建议\n"
            "按优先级排列3-5条招商方向建议，每条包含：\n"
            "- 建议引入的产业或行业\n"
            "- 引入理由（补链/强链/延链）\n"
            "- 预期效果（1句话）\n\n"
            "写作要求：\n"
            "- 总字数800-1200字\n"
            "- 使用规划咨询行业用语\n"
            "- 先给出结论性判断，再展开分析\n"
            "- 不要出现评分、权重等量化指标，用定性语言表达\n"
            '- 不要使用Markdown标题符号#，直接用「一、」「二、」等编号'
        )

    @staticmethod
    def _industry_report_prompt() -> str:
        return (
            "你是一位产业规划咨询专家，请基于以下产业关联分析数据撰写一份产业规划分析报告。\n\n"
            "报告结构（必须严格按此结构输出）：\n\n"
            "一、产业定位\n"
            "用1-2句话概括该产业在区域经济中的定位和总体规模。\n\n"
            "二、产业链结构\n"
            '- 核心上游：列出2-3个最重要的上游供应产业，用「高度依赖」「具备一定基础」等定性表达描述依赖程度。不要列举系数。\n'
            "- 核心下游：列出2-3个最重要的下游需求产业，同样使用定性表达。\n\n"
            "三、本地产业基础\n"
            "列出目标产业、上游、下游企业数量，以及主要支撑行业（企业数排名前3的行业名称）。用自然语言描述，不要用表格。\n\n"
            "四、主要优势\n"
            '根据企业集聚情况，总结2-3条产业优势。例如：「XX产业已形成一定集聚，具备XX基础」。\n\n'
            "五、主要短板\n"
            '根据产业链缺失环节或企业数量较少的环节，总结2-3条短板。例如：「上游XX环节企业较少，存在补链空间」。\n\n'
            "六、规划建议\n"
            "- 补链建议：针对缺失环节的招商方向。\n"
            "- 强链建议：做强现有优势环节的措施。\n"
            "- 延链建议：向产业链高附加值环节延伸的方向。\n\n"
            "写作要求：\n"
            "- 总字数500-800字\n"
            '- 使用规划行业用语，如「具备一定基础」「支撑能力较强」「产业链较完整」「存在补链空间」「集聚效应初步显现」等\n'
            "- 不要出现投入产出系数、flow_value等学术数据\n"
            "- 不要复述所有数据，只保留最重要的\n"
            '- 不要使用Markdown标题符号#，直接用「一、」「二、」等编号'
        )

    @staticmethod
    def _industry_judgment_prompt() -> str:
        return (
            "你是一位资深产业规划咨询师，正在为地方政府撰写产业招商研判意见。\n"
            "请基于以下产业关联分析数据，直接回答用户的问题，给出明确的专业判断。\n\n"
            "输出结构（必须严格按此结构输出）：\n\n"
            "【综合判断】\n"
            '用2-3句话给出明确结论。格式：「综合来看，XX产业（适合/暂不适合）在XX区域发展，主要基于以下分析。」\n'
            "结论要直接、明确，不要模棱两可。\n\n"
            "【优势分析】\n"
            "基于产业链数据和本地企业数据，列出2-3条核心优势。每条优势必须引用具体数据支撑（企业数量、行业名称），但不要罗列系数。\n"
            '使用规划行业表达：「已形成初步集聚」「具备一定产业基础」「上下游配套较为完善」等。\n\n'
            "【短板分析】\n"
            "基于数据中企业数量较少或缺失的环节，列出2-3条关键短板。\n"
            '使用规划行业表达：「上游XX环节存在断链风险」「本地配套能力不足」「产业链延伸空间有限」等。\n\n'
            "【发展方向建议】\n"
            "给出3-4条可操作的建议，每条包含：\n"
            "- 建议方向（补链/强链/延链）\n"
            "- 具体措施（1句话）\n"
            "- 重点招商目标行业（如有）\n\n"
            "写作要求：\n"
            "- 总字数600-900字\n"
            "- 先结论，后分析。读者第一眼就能看到判断结果\n"
            "- 使用招商咨询报告语气，不要学术论文语气\n"
            '- 使用规划行业用语：「具备一定基础」「支撑能力较强」「产业链较完整」「存在补链空间」「集聚效应初步显现」「建议重点关注」「优先引进」等\n'
            "- 不要出现投入产出系数、flow_value、coefficient等学术数据\n"
            "- 不要复述原始数据表格，只提取关键结论\n"
            '- 不要使用Markdown标题符号#'
        )

    async def synthesize_answer(self, question: str, context: dict[str, Any]) -> str:
        chat = self._chat()
        if chat is None:
            if context.get("tool_results"):
                return "已完成工具计算。" + json.dumps(context, ensure_ascii=False, indent=2)
            return "抱歉，当前未配置大语言模型，无法回答该问题。"
        has_tools = bool(context.get("tool_results"))
        if has_tools:
            if self._is_industry_judgment(question, context):
                system_prompt = self._industry_judgment_prompt()
            elif self._is_industry_direction(context):
                system_prompt = self._industry_direction_prompt()
            elif self._is_industry_report(context):
                system_prompt = self._industry_report_prompt()
            else:
                system_prompt = "你是轻量化规划AI总师，请基于工具结果给出简洁、专业、中文回答。"
            user_content = f"问题：{question}\n工具结果：{json.dumps(context, ensure_ascii=False)}"
        else:
            system_prompt = "你是轻量化规划AI总师，一位专业的城市规划助手。请用简洁、专业的中文直接回答用户问题。"
            user_content = question
        try:
            response = await chat.ainvoke(
                [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
            )
            return str(response.content)
        except Exception as exc:
            logger.warning("LLM答案合成失败: %s", exc)
            if has_tools:
                return "工具计算已完成。" + json.dumps(context, ensure_ascii=False, indent=2)
            return f"抱歉，回答生成失败：{exc}"

    async def stream_synthesize_answer(self, question: str, context: dict[str, Any]) -> AsyncIterator[str]:
        chat = self._chat()
        has_tools = bool(context.get("tool_results"))
        if chat is None:
            if has_tools:
                yield "已完成工具计算。" + json.dumps(context, ensure_ascii=False, indent=2)
            else:
                yield "抱歉，当前未配置大语言模型，无法回答该问题。"
            return
        if has_tools:
            if self._is_industry_judgment(question, context):
                system_prompt = self._industry_judgment_prompt()
            elif self._is_industry_direction(context):
                system_prompt = self._industry_direction_prompt()
            elif self._is_industry_report(context):
                system_prompt = self._industry_report_prompt()
            else:
                system_prompt = "你是轻量化规划AI总师，请基于工具结果给出简洁、专业、中文回答。"
            user_content = f"问题：{question}\n工具结果：{json.dumps(context, ensure_ascii=False)}"
        else:
            system_prompt = "你是轻量化规划AI总师，一位专业的城市规划助手。请用简洁、专业的中文直接回答用户问题。"
            user_content = question
        messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
        try:
            async for chunk in chat.astream(messages):
                text = getattr(chunk, "content", "")
                if isinstance(text, list):
                    text = "".join(str(part) for part in text)
                if text:
                    yield str(text)
        except Exception:
            try:
                response = await chat.ainvoke(messages)
                text = str(response.content)
                if text:
                    yield text
            except Exception as exc:
                logger.warning("LLM流式/阻塞答案合成均失败: %s", exc)
                if has_tools:
                    yield "工具计算已完成。" + json.dumps(context, ensure_ascii=False, indent=2)
                else:
                    yield f"抱歉，回答生成失败：{exc}"

    async def answer_with_uploaded_image(
        self,
        question: str,
        image_data_url: str,
        *,
        image_name: str | None = None,
    ) -> str:
        chat = self._chat(self.settings.llm_vision_model)
        if chat is None:
            return "当前未配置视觉模型，暂时无法分析上传图片。"

        prompt = (
            "你是规划分析助手。用户上传了一张 jpg/png 图片，请结合图片内容回答用户问题。"
            "如果图片涉及规划、土地利用、道路、建筑、图纸标注或空间关系，请优先围绕这些内容进行分析。"
            "回答使用简洁、专业的中文。"
        )
        if image_name:
            prompt += f" 图片文件名：{image_name}。"

        message = HumanMessage(
            content=[
                {"type": "text", "text": f"{prompt}\n用户问题：{question}"},
                {"type": "image_url", "image_url": {"url": image_data_url}},
            ]
        )
        try:
            response = await chat.ainvoke([message])
        except Exception as exc:
            return f"上传图片已收到，但视觉分析失败：{exc}"
        return str(response.content).strip()
