from typing import Any


async def amap_tool(question: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": "reserved",
        "message": "高德API接口已预留，后续可接入地理编码、POI、路径规划等能力。",
        "question": question,
        "context": context or {},
    }
