"""Gemini API integration for the Warehouse Copilot.

Uses the REST API directly so the project does not require a heavyweight AI
SDK. The API key is read only from GEMINI_API_KEY / GEMINI_MODEL environment
variables and is never stored in the SQLite database.
"""
import os
import requests
from typing import Any

DEFAULT_MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """You are Warehouse Copilot for a live warehouse operations platform.
You answer questions using ONLY the warehouse context supplied by the application.
Never invent stock, order, alert, financial, worker, or timing values.
The application calculates metrics; you explain them and reason over them.
Clearly distinguish actual database facts from estimates/recommendations.
If information is missing, say that it is not available instead of guessing.
For critical/high-risk situations, identify the cause, affected orders/products,
financial impact, and the safest next action when the data supports one.
Never claim an email, WhatsApp message, desktop notification, database mutation,
or operational action happened unless the context/API result explicitly says it did.
Do not execute destructive actions from natural language alone. Actions must be
performed by explicit backend endpoints with human confirmation.
Use Indian English where natural and format money in INR (₹).
Keep answers operational, concise, and useful. Use bullets when helpful.
"""


def _config():
    key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    return key, model


def configured() -> bool:
    return bool(_config()[0])


def ask_gemini(message: str, context: dict, history: list[dict] | None = None) -> dict:
    api_key, model = _config()
    if not api_key:
        return {
            "ok": False,
            "error": "GEMINI_API_KEY is not configured. Add it to app/backend/.env or the process environment.",
            "provider": "gemini",
            "model": model,
        }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    prompt = (
        SYSTEM_PROMPT
        + "\n\nLIVE WAREHOUSE CONTEXT (JSON):\n"
        + __import__("json").dumps(context, ensure_ascii=False, default=str)
        + "\n\nUSER QUESTION:\n"
        + message
    )
    contents: list[dict[str, Any]] = []
    for item in (history or [])[-8:]:
        role = "model" if item.get("role") in ("assistant", "model") else "user"
        text = str(item.get("content", "")).strip()
        if text:
            contents.append({"role": role, "parts": [{"text": text}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})

    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 1400,
        },
    }
    try:
        resp = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=45,
        )
        if resp.status_code >= 400:
            try:
                err = resp.json().get("error", {}).get("message", resp.text)
            except Exception:
                err = resp.text
            return {"ok": False, "error": f"Gemini API {resp.status_code}: {err}", "provider": "gemini", "model": model}
        data = resp.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "\n".join(p.get("text", "") for p in parts if p.get("text"))
        if not text:
            text = "Gemini returned no text for this request."
        return {"ok": True, "answer": text, "provider": "gemini", "model": model}
    except requests.RequestException as exc:
        return {"ok": False, "error": f"Gemini network error: {exc}", "provider": "gemini", "model": model}
