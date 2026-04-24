from __future__ import annotations

import json
from dataclasses import dataclass

from app.services.env_loader import get_env_value, load_project_env


load_project_env()

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_GOOGLE_MODEL = "gemini-2.5-flash"
DEFAULT_MISTRAL_MODEL = "mistral-small-2603"
VALID_LLM_PROVIDERS = {"anthropic", "google", "mistral"}
COMMON_LLM_MODELS = {
    "anthropic": [
        DEFAULT_ANTHROPIC_MODEL,
        "claude-3-5-haiku-latest",
    ],
    "google": [
        DEFAULT_GOOGLE_MODEL,
        "gemini-2.5-pro",
        "gemma-3-27b-it",
    ],
    "mistral": [
        DEFAULT_MISTRAL_MODEL,
        "ministral-8b-2410",
    ],
}


@dataclass
class LLMSettings:
    provider: str = "anthropic"
    anthropic_api_key: str = ""
    google_api_key: str = ""
    mistral_api_key: str = ""
    anthropic_model: str = DEFAULT_ANTHROPIC_MODEL
    google_model: str = DEFAULT_GOOGLE_MODEL
    mistral_model: str = DEFAULT_MISTRAL_MODEL
    max_tokens: int = 1500
    temperature: float = 0.1

    @property
    def is_configured(self) -> bool:
        if self.provider == "google":
            return bool(self.google_api_key)
        if self.provider == "mistral":
            return bool(self.mistral_api_key)
        return bool(self.anthropic_api_key)

    @property
    def active_api_key(self) -> str:
        if self.provider == "google":
            return self.google_api_key
        if self.provider == "mistral":
            return self.mistral_api_key
        return self.anthropic_api_key

    @property
    def active_model(self) -> str:
        if self.provider == "google":
            return self.google_model
        if self.provider == "mistral":
            return self.mistral_model
        return self.anthropic_model


def get_model_options(provider: str) -> list[str]:
    return list(COMMON_LLM_MODELS.get(provider, []))


def get_configured_providers() -> list[str]:
    settings = load_llm_settings()
    providers: list[str] = []
    if settings.anthropic_api_key:
        providers.append("anthropic")
    if settings.google_api_key:
        providers.append("google")
    if settings.mistral_api_key:
        providers.append("mistral")
    return providers


def load_llm_settings(provider_override: str | None = None, model_override: str | None = None) -> LLMSettings:
    max_tokens_raw = get_env_value("ANTHROPIC_MAX_TOKENS", "4000")
    temperature_raw = get_env_value("ANTHROPIC_TEMPERATURE", "0.1")
    provider_raw = get_env_value("LLM_PROVIDER", "").strip().lower()

    try:
        max_tokens = int(max_tokens_raw)
    except ValueError:
        max_tokens = 1500

    try:
        temperature = float(temperature_raw)
    except ValueError:
        temperature = 0.1

    anthropic_api_key = get_env_value("ANTHROPIC_API_KEY", "")
    google_api_key = get_env_value("GOOGLE_API_KEY", "")
    mistral_api_key = get_env_value("MISTRAL_API_KEY", "")

    provider_candidate = (provider_override or provider_raw).strip().lower()

    if provider_candidate not in VALID_LLM_PROVIDERS:
        if google_api_key:
            provider_candidate = "google"
        elif mistral_api_key:
            provider_candidate = "mistral"
        else:
            provider_candidate = "anthropic"

    anthropic_model = get_env_value("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    google_model = get_env_value("GOOGLE_MODEL", DEFAULT_GOOGLE_MODEL)
    mistral_model = get_env_value("MISTRAL_MODEL", DEFAULT_MISTRAL_MODEL)

    if model_override:
        if provider_candidate == "google":
            google_model = model_override.strip()
        elif provider_candidate == "mistral":
            mistral_model = model_override.strip()
        else:
            anthropic_model = model_override.strip()

    return LLMSettings(
        provider=provider_candidate,
        anthropic_api_key=anthropic_api_key,
        google_api_key=google_api_key,
        mistral_api_key=mistral_api_key,
        anthropic_model=anthropic_model,
        google_model=google_model,
        mistral_model=mistral_model,
        max_tokens=max_tokens,
        temperature=temperature,
    )


def create_llm_client(provider_override: str | None = None, model_override: str | None = None):
    settings = load_llm_settings(provider_override=provider_override, model_override=model_override)
    if not settings.is_configured:
        return None

    if settings.provider == "google":
        try:
            from google import genai
        except Exception:
            return None
        return genai.Client(api_key=settings.google_api_key)

    if settings.provider == "mistral":
        try:
            from mistralai import Mistral
        except Exception:
            return None
        return Mistral(api_key=settings.mistral_api_key)

    try:
        import anthropic
    except Exception:
        return None

    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def describe_llm_readiness() -> dict[str, str]:
    settings = load_llm_settings()
    return {
        "Provider": settings.provider,
        "Mode integration": "appels directs Python",
        "Modele": settings.active_model,
        "LLM_PROVIDER": settings.provider,
        "ANTHROPIC_API_KEY": "configuree" if settings.anthropic_api_key else "non configuree",
        "GOOGLE_API_KEY": "configuree" if settings.google_api_key else "non configuree",
        "MISTRAL_API_KEY": "configuree" if settings.mistral_api_key else "non configuree",
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


def call_anthropic_message(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, object]:
    settings = load_llm_settings(provider_override=provider_override, model_override=model_override)
    if settings.provider != "anthropic":
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.active_model,
            "error": "provider_anthropic_non_actif",
            "text": "",
            "usage": {},
        }
    client = create_llm_client(provider_override=provider_override, model_override=model_override)
    if client is None:
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.active_model,
            "error": "client_llm_non_configure",
            "text": "",
            "usage": {},
        }

    request_max_tokens = max_tokens or settings.max_tokens

    try:
        message = client.messages.create(
            model=settings.active_model,
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
            "model": settings.active_model,
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
            "model": settings.active_model,
            "error": f"{exc.__class__.__name__}: {exc}",
            "text": "",
            "usage": {},
        }


def call_google_message(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, object]:
    settings = load_llm_settings(provider_override=provider_override, model_override=model_override)
    if settings.provider != "google":
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.active_model,
            "error": "provider_google_non_actif",
            "text": "",
            "usage": {},
        }
    client = create_llm_client(provider_override=provider_override, model_override=model_override)
    if client is None:
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.active_model,
            "error": "client_llm_non_configure",
            "text": "",
            "usage": {},
        }

    request_max_tokens = max_tokens or settings.max_tokens

    try:
        response = client.models.generate_content(
            model=settings.active_model,
            contents=f"{system_prompt}\n\n{user_prompt}",
            config={
                "temperature": settings.temperature,
                "max_output_tokens": request_max_tokens,
            },
        )
        text = getattr(response, "text", "") or ""
        usage = getattr(response, "usage_metadata", None)
        return {
            "ok": True,
            "provider": settings.provider,
            "model": settings.active_model,
            "text": text.strip(),
            "usage": {
                "input_tokens": getattr(usage, "prompt_token_count", None),
                "output_tokens": getattr(usage, "candidates_token_count", None),
            },
            "raw": response,
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.active_model,
            "error": f"{exc.__class__.__name__}: {exc}",
            "text": "",
            "usage": {},
        }


def call_mistral_message(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, object]:
    settings = load_llm_settings(provider_override=provider_override, model_override=model_override)
    if settings.provider != "mistral":
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.active_model,
            "error": "provider_mistral_non_actif",
            "text": "",
            "usage": {},
        }
    client = create_llm_client(provider_override=provider_override, model_override=model_override)
    if client is None:
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.active_model,
            "error": "client_llm_non_configure",
            "text": "",
            "usage": {},
        }

    request_max_tokens = max_tokens or settings.max_tokens

    try:
        response = client.chat.complete(
            model=settings.active_model,
            max_tokens=request_max_tokens,
            temperature=settings.temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        message = getattr(response, "choices", [None])[0]
        content = getattr(getattr(message, "message", None), "content", "") if message else ""
        usage = getattr(response, "usage", None)
        return {
            "ok": True,
            "provider": settings.provider,
            "model": settings.active_model,
            "text": (content or "").strip(),
            "usage": {
                "input_tokens": getattr(usage, "prompt_tokens", None),
                "output_tokens": getattr(usage, "completion_tokens", None),
            },
            "raw": response,
        }
    except Exception as exc:
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.active_model,
            "error": f"{exc.__class__.__name__}: {exc}",
            "text": "",
            "usage": {},
        }


def call_llm_message(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, object]:
    settings = load_llm_settings(provider_override=provider_override, model_override=model_override)
    if settings.provider == "google":
        return call_google_message(
            system_prompt,
            user_prompt,
            max_tokens=max_tokens,
            provider_override=provider_override,
            model_override=model_override,
        )
    if settings.provider == "mistral":
        return call_mistral_message(
            system_prompt,
            user_prompt,
            max_tokens=max_tokens,
            provider_override=provider_override,
            model_override=model_override,
        )
    return call_anthropic_message(
        system_prompt,
        user_prompt,
        max_tokens=max_tokens,
        provider_override=provider_override,
        model_override=model_override,
    )


def parse_json_response(text: str) -> tuple[dict[str, object] | None, str | None]:
    import re

    cleaned = text.strip()
    if not cleaned:
        return None, "reponse_vide"

    # Extract JSON from markdown code fence if present (```json ... ``` or ``` ... ```)
    fence_match = re.search(r"```(?:json)?\s*\n?([\s\S]+?)\n?```", cleaned)
    if fence_match:
        cleaned = fence_match.group(1).strip()

    # Try to extract the first JSON object if there is surrounding text
    if not cleaned.startswith("{"):
        obj_match = re.search(r"\{[\s\S]+\}", cleaned)
        if obj_match:
            cleaned = obj_match.group(0)

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed, None
        return None, "json_non_objet"
    except json.JSONDecodeError as exc:
        return None, f"json_invalide: {exc}"
