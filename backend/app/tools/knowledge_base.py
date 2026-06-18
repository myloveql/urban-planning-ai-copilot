from typing import Any


async def knowledge_base_tool(question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "reserved",
        "message": "知识库检索增强接口已预留，后续可接入向量库或Dify知识库。",
        "question": question,
        "context": context or {},
    }
