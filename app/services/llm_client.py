from __future__ import annotations

import json
import os
from dataclasses import dataclass

from app.services.env_loader import load_project_env


load_project_env()

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-20250514"


@dataclass
class LLMSettings:
    provider: str = "anthropic"
    api_key: str = ""
    model: str = DEFAULT_ANTHROPIC_MODEL
    max_tokens: int = 1500
    temperature: float = 0.1

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


def load_llm_settings() -> LLMSettings:
    max_tokens_raw = os.getenv("ANTHROPIC_MAX_TOKENS", "1500")
    temperature_raw = os.getenv("ANTHROPIC_TEMPERATURE", "0.1")

    try:
        max_tokens = int(max_tokens_raw)
    except ValueError:
        max_tokens = 1500

    try:
        temperature = float(temperature_raw)
    except ValueError:
        temperature = 0.1

    return LLMSettings(
        provider="anthropic",
        api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        model=os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL),
        max_tokens=max_tokens,
        temperature=temperature,
    )


def create_llm_client():
    settings = load_llm_settings()
    if not settings.is_configured:
        return None

    try:
        import anthropic
    except Exception:
        return None

    return anthropic.Anthropic(api_key=settings.api_key)


def describe_llm_readiness() -> dict[str, str]:
    settings = load_llm_settings()
    return {
        "Provider": settings.provider,
        "Mode integration": "appels directs Python",
        "Modele": settings.model,
        "ANTHROPIC_API_KEY": "configuree" if settings.api_key else "non configuree",
        "Max tokens": str(settings.max_tokens),
        "Temperature": str(settings.temperature),
    }


def extract_text_from_message(message) -> str:
    blocks = getattr(message, "content", []) or []
    texts: list[str] = []
    for block in blocks:
        block_type = getattr(block, "type", None)
        block_text = getattr(block, "text", None)
        if block_type == "text" and block_text:
            texts.append(block_text)
    return "\n".join(texts).strip()


def call_anthropic_message(system_prompt: str, user_prompt: str, *, max_tokens: int | None = None) -> dict[str, object]:
    settings = load_llm_settings()
    client = create_llm_client()
    if client is None:
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.model,
            "error": "client_llm_non_configure",
            "text": "",
            "usage": {},
        }

    request_max_tokens = max_tokens or settings.max_tokens

    try:
        message = client.messages.create(
            model=settings.model,
            max_tokens=request_max_tokens,
            temperature=settings.temperature,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_prompt},
            ],
        )
        return {
            "ok": True,
            "provider": settings.provider,
            "model": settings.model,
            "text": extract_text_from_message(message),
            "usage": {
                "input_tokens": getattr(getattr(message, "usage", None), "input_tokens", None),
                "output_tokens": getattr(getattr(message, "usage", None), "output_tokens", None),
            },
            "raw": message,
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.model,
            "error": f"{exc.__class__.__name__}: {exc}",
            "text": "",
            "usage": {},
        }


def parse_json_response(text: str) -> tuple[dict[str, object] | None, str | None]:
    cleaned = text.strip()
    if not cleaned:
        return None, "reponse_vide"

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.replace("json\n", "", 1).strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed, None
        return None, "json_non_objet"
    except json.JSONDecodeError as exc:
        return None, f"json_invalide: {exc}"
