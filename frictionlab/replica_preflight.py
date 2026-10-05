"""Offline preparation check for a user-supplied replica; declarations never authorize execution."""

from __future__ import annotations

import ipaddress
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from frictionlab.configuration import read_json


class ReplicaDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")
    app_origin: str
    source_directory: str
    build_id: str = Field(min_length=1, max_length=120)
    disposable_data: bool = False
    synthetic_accounts: bool = False
    mocked_integrations: bool = False
    production_origins: list[str] = Field(default_factory=list, max_length=30)
    network_boundary: str = Field(default="", max_length=500)
    cleanup_plan: str = Field(default="", max_length=500)


def inspect_declaration(path: Path) -> dict:
    """Read local metadata only; a passing declaration is never proof of isolation."""
    data = ReplicaDeclaration.model_validate(read_json(Path(path)))
    gaps = []
    parts = urlsplit(data.app_origin)
    try:
        address = ipaddress.ip_address(parts.hostname or "")
        local = address.is_loopback
    except ValueError:
        local = False
    if parts.scheme != "http" or not local or not parts.port or parts.path not in {"", "/"}:
        gaps.append("Application origin must be a numeric loopback HTTP origin with an explicit port")
    source = Path(data.source_directory).resolve()
    if not source.is_dir():
        gaps.append("Supply an existing local source/copy directory")
    for field, label in (
        (data.disposable_data, "Disposable data is not declared"),
        (data.synthetic_accounts, "Synthetic accounts are not declared"),
        (data.mocked_integrations, "Mocked external integrations are not declared"),
        (bool(data.production_origins), "Production origins to block are not declared"),
        (bool(data.network_boundary.strip()), "Independent network boundary is not documented"),
        (bool(data.cleanup_plan.strip()), "Owned cleanup plan is not documented"),
    ):
        if not field:
            gaps.append(label)
    gaps.append(
        "External interactive execution remains blocked: this local declaration cannot prove "
        "the runtime's independent egress boundary or backend/service isolation"
    )
    return {
        "execution_enabled": False,
        "target_requests": 0,
        "scope": "preparation_only",
        "build_id": data.build_id,
        "gaps": gaps,
    }
