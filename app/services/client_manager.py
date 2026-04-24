from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from app.services.env_loader import load_project_env
from app.services.supabase_bridge import create_supabase_client


load_project_env()


def get_operator_id() -> str:
    """Retourne l'OPERATOR_ID fixe depuis .env, ou en génère un nouveau en mémoire."""
    raw = os.getenv("OPERATOR_ID", "").strip()
    if raw:
        try:
            UUID(raw)
            return raw
        except ValueError:
            pass
    # Pas configuré : on retourne un UUID constant basé sur le projet
    return "00000000-0000-0000-0000-000000000001"


@dataclass
class ClientRecord:
    id: str
    nom: str
    forme_juridique: str | None
    secteur_activite: str | None
    contact_email: str | None
    contact_telephone: str | None
    siret: str | None

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "ClientRecord":
        return cls(
            id=row["id"],
            nom=row.get("nom", ""),
            forme_juridique=row.get("forme_juridique"),
            secteur_activite=row.get("secteur_activite"),
            contact_email=row.get("contact_email"),
            contact_telephone=row.get("contact_telephone"),
            siret=row.get("siret"),
        )

    def label(self) -> str:
        parts = [self.nom]
        if self.forme_juridique:
            parts.append(f"({self.forme_juridique})")
        return " ".join(parts)


def list_clients() -> list[ClientRecord]:
    """Récupère tous les clients de Supabase triés par nom."""
    client = create_supabase_client(use_service_role=True)
    if client is None:
        return []
    try:
        rows = (
            client.table("clients")
            .select("id,nom,forme_juridique,secteur_activite,contact_email,contact_telephone,siret")
            .eq("owner_id", get_operator_id())
            .order("nom")
            .execute()
            .data
        )
        return [ClientRecord.from_row(r) for r in rows]
    except Exception:
        return []


def get_client_by_id(client_id: str) -> ClientRecord | None:
    """Récupère un client par son UUID."""
    supabase = create_supabase_client(use_service_role=True)
    if supabase is None:
        return None
    try:
        rows = supabase.table("clients").select("*").eq("id", client_id).limit(1).execute().data
        return ClientRecord.from_row(rows[0]) if rows else None
    except Exception:
        return None


def create_client(
    nom: str,
    forme_juridique: str | None = None,
    secteur_activite: str | None = None,
    contact_email: str | None = None,
    contact_telephone: str | None = None,
    siret: str | None = None,
) -> ClientRecord | None:
    """Crée un nouveau client dans Supabase et retourne son enregistrement."""
    supabase = create_supabase_client(use_service_role=True)
    if supabase is None:
        return None
    payload: dict[str, Any] = {
        "nom": nom.strip(),
        "owner_id": get_operator_id(),
    }
    if forme_juridique:
        payload["forme_juridique"] = forme_juridique.strip()
    if secteur_activite:
        payload["secteur_activite"] = secteur_activite.strip()
    if contact_email:
        payload["contact_email"] = contact_email.strip()
    if contact_telephone:
        payload["contact_telephone"] = contact_telephone.strip()
    if siret:
        payload["siret"] = siret.strip()
    try:
        row = supabase.table("clients").insert(payload).execute().data[0]
        return ClientRecord.from_row(row)
    except Exception:
        return None


def list_dossiers_for_client(client_id: str) -> list[dict[str, Any]]:
    """Récupère les dossiers d'un client avec leur score et statut."""
    supabase = create_supabase_client(use_service_role=True)
    if supabase is None:
        return []
    try:
        return (
            supabase.table("dossiers")
            .select("id,titre,type_financement,financeur,statut,created_at")
            .eq("client_id", client_id)
            .order("created_at", desc=True)
            .execute()
            .data
        )
    except Exception:
        return []
