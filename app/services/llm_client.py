from __future__ import annotations

import json
from dataclasses import dataclass

from app.services.env_loader import get_env_value, load_project_env


load_project_env()

DEFAULT_ANTHROPIC_MODEL = "claude-sonnet-4-6"
DEFAULT_DEEPSEEK_MODEL = "deepseek-v4-pro-thinking"
DEFAULT_GOOGLE_MODEL = "gemini-2.5-flash"
DEFAULT_MISTRAL_MODEL = "mistral-small-2603"
DEPRECATED_MISTRAL_MODELS = {"ministral-8b-2410"}
VALID_LLM_PROVIDERS = {"anthropic", "deepseek", "google", "mistral"}
COMMON_LLM_MODELS = {
    "anthropic": [
        DEFAULT_ANTHROPIC_MODEL,
        "claude-3-5-haiku-latest",
    ],
    "deepseek": [
        DEFAULT_DEEPSEEK_MODEL,
        "deepseek-v4-pro-non-thinking",
    ],
    "google": [
        DEFAULT_GOOGLE_MODEL,
        "gemini-2.5-pro",
        "gemma-3-27b-it",
    ],
    "mistral": [
        DEFAULT_MISTRAL_MODEL,
    ],
}


@dataclass
class LLMSettings:
    provider: str = "anthropic"
    anthropic_api_key: str = ""
    deepseek_api_key: str = ""
    google_api_key: str = ""
    mistral_api_key: str = ""
    anthropic_model: str = DEFAULT_ANTHROPIC_MODEL
    deepseek_model: str = DEFAULT_DEEPSEEK_MODEL
    google_model: str = DEFAULT_GOOGLE_MODEL
    mistral_model: str = DEFAULT_MISTRAL_MODEL
    mistral_budget_project_agent_id: str = ""
    max_tokens: int = 1500
    temperature: float = 0.1

    @property
    def is_configured(self) -> bool:
        if self.provider == "deepseek":
            return bool(self.deepseek_api_key)
        if self.provider == "google":
            return bool(self.google_api_key)
        if self.provider == "mistral":
            return bool(self.mistral_api_key)
        return bool(self.anthropic_api_key)

    @property
    def active_api_key(self) -> str:
        if self.provider == "deepseek":
            return self.deepseek_api_key
        if self.provider == "google":
            return self.google_api_key
        if self.provider == "mistral":
            return self.mistral_api_key
        return self.anthropic_api_key

    @property
    def active_model(self) -> str:
        if self.provider == "deepseek":
            return self.deepseek_model
        if self.provider == "google":
            return self.google_model
        if self.provider == "mistral":
            return self.mistral_model
        return self.anthropic_model


def _normalize_deepseek_model(model_name: str | None) -> tuple[str, str]:
    model_raw = str(model_name or "").strip() or DEFAULT_DEEPSEEK_MODEL
    normalized = model_raw.lower()
    if normalized in {"deepseek-v4-pro-thinking", "deepseek-v4-pro:thinking"}:
        return "deepseek-v4-pro", "enabled"
    if normalized in {"deepseek-v4-pro-non-thinking", "deepseek-v4-pro:non-thinking"}:
        return "deepseek-v4-pro", "disabled"
    if normalized == "deepseek-v4-pro":
        return "deepseek-v4-pro", "enabled"
    if normalized == "deepseek-chat":
        return "deepseek-chat", "disabled"
    if normalized == "deepseek-reasoner":
        return "deepseek-reasoner", "enabled"
    return model_raw, "enabled"


def get_model_options(provider: str) -> list[str]:
    return list(COMMON_LLM_MODELS.get(provider, []))


def get_configured_providers() -> list[str]:
    settings = load_llm_settings()
    providers: list[str] = []
    if settings.anthropic_api_key:
        providers.append("anthropic")
    if settings.deepseek_api_key:
        providers.append("deepseek")
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
    deepseek_api_key = get_env_value("DEEPSEEK_API_KEY", "")
    google_api_key = get_env_value("GOOGLE_API_KEY", "")
    mistral_api_key = get_env_value("MISTRAL_API_KEY", "")
    mistral_budget_project_agent_id = get_env_value("MISTRAL_AGENT_BUDGET_PROJET_ID", "").strip()

    provider_candidate = (provider_override or provider_raw).strip().lower()

    if provider_candidate not in VALID_LLM_PROVIDERS:
        if deepseek_api_key:
            provider_candidate = "deepseek"
        elif google_api_key:
            provider_candidate = "google"
        elif mistral_api_key:
            provider_candidate = "mistral"
        else:
            provider_candidate = "anthropic"

    anthropic_model = get_env_value("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    deepseek_model = get_env_value("DEEPSEEK_MODEL", DEFAULT_DEEPSEEK_MODEL)
    google_model = get_env_value("GOOGLE_MODEL", DEFAULT_GOOGLE_MODEL)
    mistral_model = get_env_value("MISTRAL_MODEL", DEFAULT_MISTRAL_MODEL)
    if mistral_model in DEPRECATED_MISTRAL_MODELS:
        mistral_model = DEFAULT_MISTRAL_MODEL

    if model_override:
        if provider_candidate == "deepseek":
            deepseek_model = model_override.strip()
        elif provider_candidate == "google":
            google_model = model_override.strip()
        elif provider_candidate == "mistral":
            mistral_model = model_override.strip()
        else:
            anthropic_model = model_override.strip()

    if mistral_model in DEPRECATED_MISTRAL_MODELS:
        mistral_model = DEFAULT_MISTRAL_MODEL

    return LLMSettings(
        provider=provider_candidate,
        anthropic_api_key=anthropic_api_key,
        deepseek_api_key=deepseek_api_key,
        google_api_key=google_api_key,
        mistral_api_key=mistral_api_key,
        anthropic_model=anthropic_model,
        deepseek_model=deepseek_model,
        google_model=google_model,
        mistral_model=mistral_model,
        mistral_budget_project_agent_id=mistral_budget_project_agent_id,
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

    if settings.provider == "deepseek":
        try:
            from openai import OpenAI
        except Exception:
            return None
        return OpenAI(
            api_key=settings.deepseek_api_key,
            base_url="https://api.deepseek.com",
            timeout=35.0,
            max_retries=0,
        )

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
        "DEEPSEEK_API_KEY": "configuree" if settings.deepseek_api_key else "non configuree",
        "GOOGLE_API_KEY": "configuree" if settings.google_api_key else "non configuree",
        "MISTRAL_API_KEY": "configuree" if settings.mistral_api_key else "non configuree",
        "MISTRAL_AGENT_BUDGET_PROJET_ID": settings.mistral_budget_project_agent_id or "non configure",
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
        from google.genai import types as genai_types
        response = client.models.generate_content(
            model=settings.active_model,
            contents=user_prompt,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=settings.temperature,
                max_output_tokens=request_max_tokens,
            ),
        )
    except (ImportError, TypeError):
        # Fallback si la version de google-genai ne supporte pas GenerateContentConfig
        response = client.models.generate_content(
            model=settings.active_model,
            contents=f"{system_prompt}\n\n{user_prompt}",
            config={
                "temperature": settings.temperature,
                "max_output_tokens": request_max_tokens,
            },
        )
    except Exception as exc:
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.active_model,
            "error": f"{exc.__class__.__name__}: {exc}",
            "text": "",
            "usage": {},
        }
    try:
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


def call_deepseek_message(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int | None = None,
    provider_override: str | None = None,
    model_override: str | None = None,
) -> dict[str, object]:
    settings = load_llm_settings(provider_override=provider_override, model_override=model_override)
    if settings.provider != "deepseek":
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.active_model,
            "error": "provider_deepseek_non_actif",
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
    resolved_model, thinking_type = _normalize_deepseek_model(settings.active_model)
    request_kwargs: dict[str, object] = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": request_max_tokens,
        "timeout": 35.0,
        "extra_body": {"thinking": {"type": thinking_type}},
    }
    if thinking_type == "enabled":
        request_kwargs["reasoning_effort"] = "high"
    else:
        request_kwargs["temperature"] = settings.temperature

    try:
        response = client.chat.completions.create(**request_kwargs)
        message = getattr(response, "choices", [None])[0]
        response_message = getattr(message, "message", None) if message else None
        content = getattr(response_message, "content", "") or ""
        usage = getattr(response, "usage", None)
        return {
            "ok": True,
            "provider": settings.provider,
            "model": settings.active_model,
            "text": content.strip(),
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


def call_mistral_agent_message(
    agent_id: str,
    user_prompt: str,
    *,
    max_tokens: int | None = None,
    provider_override: str | None = None,
) -> dict[str, object]:
    settings = load_llm_settings(provider_override=provider_override)
    if settings.provider != "mistral":
        return {
            "ok": False,
            "provider": settings.provider,
            "model": settings.active_model,
            "error": "provider_mistral_non_actif",
            "text": "",
            "usage": {},
        }

    client = create_llm_client(provider_override=provider_override)
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
        response = client.agents.complete(
            agent_id=agent_id,
            max_tokens=request_max_tokens,
            messages=[
                {"role": "user", "content": user_prompt},
            ],
        )
        message = getattr(response, "choices", [None])[0]
        content = getattr(getattr(message, "message", None), "content", "") if message else ""
        usage = getattr(response, "usage", None)
        return {
            "ok": True,
            "provider": settings.provider,
            "model": f"agent:{agent_id}",
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
            "model": f"agent:{agent_id}",
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
    if settings.provider == "deepseek":
        return call_deepseek_message(
            system_prompt,
            user_prompt,
            max_tokens=max_tokens,
            provider_override=provider_override,
            model_override=model_override,
        )
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


def repair_json_response_with_llm(
    text: str,
    *,
    provider_override: str | None = None,
    model_override: str | None = None,
    max_tokens: int = 6500,
) -> dict[str, object]:
    repair_prompt = """
Role
Tu es un moteur de reparation JSON.

Objectif
Recevoir une sortie quasi-JSON invalide et retourner uniquement un JSON valide.

Contraintes
- Ne change pas le sens des donnees.
- Ne supprime pas une cle ou une valeur sauf si elle est manifestement tronquee ou corrompue.
- Ne rajoute aucun commentaire, markdown, explication ou balise.
- Retourne uniquement un objet JSON valide.
- Ne recopie pas d'introduction.
""".strip()

    repair_user_prompt = (
        "Repare cet objet JSON invalide et retourne uniquement le JSON valide.\n\n"
        f"{text.strip()}"
    )
    llm_result = call_llm_message(
        repair_prompt,
        repair_user_prompt,
        max_tokens=max_tokens,
        provider_override=provider_override,
        model_override=model_override,
    )
    if not llm_result.get("ok"):
        return {
            "ok": False,
            "error": llm_result.get("error", "json_repair_llm_error"),
            "payload": None,
            "raw_text": llm_result.get("text", ""),
            "provider": llm_result.get("provider", ""),
            "model": llm_result.get("model", ""),
            "usage": llm_result.get("usage", {}),
        }

    repaired_payload, repaired_error = parse_json_response(str(llm_result.get("text", "")))
    return {
        "ok": repaired_error is None and repaired_payload is not None,
        "error": repaired_error,
        "payload": repaired_payload,
        "raw_text": llm_result.get("text", ""),
        "provider": llm_result.get("provider", ""),
        "model": llm_result.get("model", ""),
        "usage": llm_result.get("usage", {}),
    }
