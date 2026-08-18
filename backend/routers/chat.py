"""Warehouse Copilot chat endpoint."""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from ..services.ai_context import build_warehouse_context
from ..services.gemini import ask_gemini, configured

router = APIRouter(prefix="/chat", tags=["AI Copilot"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[dict] = Field(default_factory=list, max_length=12)


@router.get("/status")
def chat_status():
    return {"configured": configured(), "provider": "gemini"}


@router.post("")
def chat(req: ChatRequest):
    context = build_warehouse_context(req.message)
    result = ask_gemini(req.message, context, req.history)
    if not result.get("ok"):
        raise HTTPException(503, detail=result.get("error", "AI provider unavailable"))
    return {
        **result,
        "context": {
            "warehouse": context["warehouse"]["name"],
            "active_alerts": len(context["active_alerts"]),
            "open_exceptions": len(context["open_exceptions"]),
            "pending_decisions": len(context["pending_decisions"]),
        },
    }
