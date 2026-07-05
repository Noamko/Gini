"""Resolve an agent's direct tool/credential grants and scope credentials per tool.

An agent's effective tools are the union of its direct ``agent_tools`` grants and the tools
bundled by its assigned skills. Its credential pool is the union of direct ``agent_credentials``
grants and skill-bundled credentials. At execution time each tool receives ONLY the credentials
bound to its declared slots — never the whole pool.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from uuid import UUID

import structlog
from sqlalchemy import select

from app.dependencies import async_session
from app.models.credential import Credential, skill_credentials
from app.models.grant import agent_credentials, agent_tools
from app.models.skill import agent_skills
from app.services.credential_vault import decrypt_value
from app.tools.base import CredentialSlot

logger = structlog.get_logger("grant_resolver")


@dataclass
class PooledCredential:
    id: str
    name: str
    type: str
    value: str


async def get_agent_tool_grants(agent_id: UUID) -> dict[str, dict[str, str | list[str]]]:
    """Return the agent's direct tool grants as ``{tool_name: {slot_name: credential_id(s)}}``.

    A single binding stays a string; a ``multi`` binding stays a list of strings — never
    stringified to a list literal, which would not match any pool key downstream.
    """
    async with async_session() as db:
        result = await db.execute(
            select(agent_tools.c.tool_name, agent_tools.c.slot_bindings).where(agent_tools.c.agent_id == agent_id)
        )
    grants: dict[str, dict[str, str | list[str]]] = {}
    for tool_name, slot_bindings in result.all():
        grants[tool_name] = {
            str(k): ([str(x) for x in v] if isinstance(v, list) else str(v)) for k, v in (slot_bindings or {}).items()
        }
    return grants


async def get_agent_credential_pool(agent_id: UUID) -> dict[str, PooledCredential]:
    """Return the agent's available credentials, decrypted and keyed by credential id (str).

    Pool = direct ``agent_credentials`` grants ∪ credentials bundled by assigned skills.
    Inactive credentials and ones that fail to decrypt are skipped.
    """
    async with async_session() as db:
        direct_res = await db.execute(
            select(Credential)
            .join(agent_credentials, Credential.id == agent_credentials.c.credential_id)
            .where(agent_credentials.c.agent_id == agent_id)
        )
        skill_res = await db.execute(
            select(Credential)
            .join(skill_credentials, Credential.id == skill_credentials.c.credential_id)
            .join(agent_skills, agent_skills.c.skill_id == skill_credentials.c.skill_id)
            .where(agent_skills.c.agent_id == agent_id)
        )
    creds = list(direct_res.scalars().all()) + list(skill_res.scalars().all())

    pool: dict[str, PooledCredential] = {}
    for cred in creds:
        if not cred.is_active or str(cred.id) in pool:
            continue
        try:
            value = decrypt_value(cred.encrypted_value)
        except Exception as e:
            await logger.aerror("credential_decrypt_error", credential=cred.name, error=str(e))
            continue
        pool[str(cred.id)] = PooledCredential(id=str(cred.id), name=cred.name, type=cred.credential_type, value=value)
    return pool


def resolve_tool_credentials(
    *,
    declared_slots: Sequence[CredentialSlot],
    open_credential_slots: bool,
    slot_bindings: dict[str, str | list[str]] | None,
    credential_pool: dict[str, PooledCredential],
) -> tuple[dict[str, str | list[str]], list[str]]:
    """Resolve a single tool's credential slots to ``({slot_name: value(s)}, missing_required)``.

    Only the credentials bound to this tool's slots are returned — never the whole pool. A
    single slot resolves to one value and auto-binds when the pool holds exactly one credential
    of the slot's type. A ``multi`` slot binds a *list* of credentials and resolves to a list of
    values (explicit bindings only — no auto-bind). An unsatisfied required slot is reported as
    missing (a clear config error, not an auth failure).
    """
    slot_bindings = slot_bindings or {}
    resolved: dict[str, str | list[str]] = {}

    if open_credential_slots:
        # Open-slot tools (e.g. run_shell): expose every explicitly bound credential under its
        # binding name. Nothing implicit — only what an admin bound reaches the tool.
        for slot_name, cred_id in slot_bindings.items():
            pooled = credential_pool.get(str(cred_id))
            if pooled is not None:
                resolved[slot_name] = pooled.value
        return resolved, []

    missing: list[str] = []
    for slot in declared_slots:
        bound = slot_bindings.get(slot.name)
        bound_ids = bound if isinstance(bound, list) else ([bound] if bound else [])
        pooled_list = [credential_pool[str(b)] for b in bound_ids if str(b) in credential_pool]

        if slot.multi:
            # Multi slots are explicit-only: never auto-bind a wildcard set of credentials.
            if pooled_list:
                resolved[slot.name] = [p.value for p in pooled_list]
            elif slot.required:
                missing.append(slot.name)
            continue

        pooled = pooled_list[0] if pooled_list else None
        if pooled is None:
            candidates = [c for c in credential_pool.values() if c.type == slot.type]
            if len(candidates) == 1:
                pooled = candidates[0]
        if pooled is None:
            if slot.required:
                missing.append(slot.name)
            continue
        resolved[slot.name] = pooled.value
    return resolved, missing
