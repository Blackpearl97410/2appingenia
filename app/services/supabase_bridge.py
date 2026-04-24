from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import re
import unicodedata

from app.services.env_loader import load_project_env


load_project_env()

ROOT_DIR = Path(__file__).resolve().parents[2]
SUPABASE_DIR = ROOT_DIR / "supabase"
SUPABASE_MIGRATIONS_DIR = SUPABASE_DIR / "migrations"
SUPABASE_SEED_FILE = SUPABASE_DIR / "seed.sql"
SUPABASE_CONFIG_FILE = SUPABASE_DIR / "config.toml"


@dataclass
class SupabaseSettings:
    url: str
    anon_key: str
    service_role_key: str
    storage_bucket: str = "subly-documents"
    project_ref: str = ""

    @property
    def is_configured(self) -> bool:
        return bool(self.url and self.anon_key)


def load_supabase_settings() -> SupabaseSettings:
    return SupabaseSettings(
        url=os.getenv("SUPABASE_URL", ""),
        anon_key=os.getenv("SUPABASE_ANON_KEY", ""),
        service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
        storage_bucket=os.getenv("SUPABASE_STORAGE_BUCKET", "subly-documents"),
        project_ref=os.getenv("SUPABASE_PROJECT_REF", ""),
    )


def create_supabase_client(use_service_role: bool | None = None):
    settings = load_supabase_settings()
    if use_service_role is None:
        use_service_role = bool(settings.service_role_key)
    key = settings.service_role_key if use_service_role and settings.service_role_key else settings.anon_key
    if not settings.url or not key:
        return None

    try:
        from supabase import Client, create_client
    except Exception:
        return None

    client: Client = create_client(settings.url, key)
    return client


def ensure_private_documents_bucket() -> dict[str, object]:
    settings = load_supabase_settings()
    client = create_supabase_client(use_service_role=True)
    if client is None:
        return {
            "ok": False,
            "bucket": settings.storage_bucket,
            "error": "client_supabase_service_role_non_configure",
        }

    bucket_name = settings.storage_bucket

    try:
        buckets = client.storage.list_buckets()
        existing = next((bucket for bucket in buckets if bucket.get("name") == bucket_name), None)
        if existing:
            if existing.get("public") is True:
                client.storage.update_bucket(bucket_name, {"public": False})
                return {
                    "ok": True,
                    "bucket": bucket_name,
                    "created": False,
                    "updated": True,
                    "public": False,
                }
            return {
                "ok": True,
                "bucket": bucket_name,
                "created": False,
                "updated": False,
                "public": bool(existing.get("public", False)),
            }

        client.storage.create_bucket(
            bucket_name,
            options={
                "public": False,
            },
        )
        return {
            "ok": True,
            "bucket": bucket_name,
            "created": True,
            "updated": False,
            "public": False,
        }
    except Exception as exc:
        return {
            "ok": False,
            "bucket": bucket_name,
            "error": f"{exc.__class__.__name__}: {exc}",
        }


def describe_supabase_readiness() -> dict[str, str]:
    settings = load_supabase_settings()
    return {
        "Dossier supabase": "pret" if SUPABASE_DIR.exists() else "absent",
        "Config locale": "presente" if SUPABASE_CONFIG_FILE.exists() else "absente",
        "Migrations": "presentes" if SUPABASE_MIGRATIONS_DIR.exists() else "absentes",
        "Seed SQL": "present" if SUPABASE_SEED_FILE.exists() else "absent",
        "SUPABASE_PROJECT_REF": "configure" if settings.project_ref else "non configure",
        "SUPABASE_URL": "configuree" if settings.url else "non configuree",
        "SUPABASE_ANON_KEY": "configuree" if settings.anon_key else "non configuree",
        "SUPABASE_SERVICE_ROLE_KEY": "configuree" if settings.service_role_key else "non configuree",
    }


def build_storage_path(document_name: str, document_type: str, record_id: str) -> str:
    safe_name = Path(document_name).name
    safe_name = unicodedata.normalize("NFKD", safe_name).encode("ascii", "ignore").decode("ascii")
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", safe_name).strip("-")
    if not safe_name:
        safe_name = "document"
    return f"{document_type}/{record_id}/{safe_name}"
