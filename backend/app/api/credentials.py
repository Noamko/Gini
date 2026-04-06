"""Credential CRUD endpoints — values are never exposed in responses."""
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.credential import Credential, skill_credentials
from app.models.skill import agent_skills
from app.schemas.credential import CredentialCreate, CredentialResponse, CredentialUpdate
from app.services.credential_vault import encrypt_value
from app.services.skill_executor import invalidate_prompt_cache

logger = structlog.get_logger("credentials_api")

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


async def _invalidate_credential_prompt_caches(credential_id: UUID, db: AsyncSession) -> None:
    result = await db.execute(
        select(agent_skills.c.agent_id)
        .join(skill_credentials, skill_credentials.c.skill_id == agent_skills.c.skill_id)
        .where(skill_credentials.c.credential_id == credential_id)
    )
    for (agent_id,) in result:
        await invalidate_prompt_cache(agent_id)


@router.get("", response_model=list[CredentialResponse])
async def list_credentials(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Credential).order_by(Credential.name))
    return result.scalars().all()


@router.get("/{credential_id}", response_model=CredentialResponse)
async def get_credential(credential_id: UUID, db: AsyncSession = Depends(get_db)):
    cred = await db.get(Credential, credential_id)
    if not cred:
        raise HTTPException(404, "Credential not found")
    return cred


@router.post("", response_model=CredentialResponse, status_code=201)
async def create_credential(body: CredentialCreate, db: AsyncSession = Depends(get_db)):
    encrypted = encrypt_value(body.value)
    cred = Credential(
        name=body.name,
        description=body.description,
        credential_type=body.credential_type,
        encrypted_value=encrypted,
    )
    db.add(cred)
    await db.commit()
    await db.refresh(cred)
    return cred


@router.put("/{credential_id}", response_model=CredentialResponse)
async def update_credential(credential_id: UUID, body: CredentialUpdate, db: AsyncSession = Depends(get_db)):
    cred = await db.get(Credential, credential_id)
    if not cred:
        raise HTTPException(404, "Credential not found")

    if body.name is not None:
        cred.name = body.name
    if body.description is not None:
        cred.description = body.description
    if body.credential_type is not None:
        cred.credential_type = body.credential_type
    if body.value is not None:
        cred.encrypted_value = encrypt_value(body.value)
    if body.is_active is not None:
        cred.is_active = body.is_active

    await db.commit()
    await db.refresh(cred)
    await _invalidate_credential_prompt_caches(credential_id, db)
    return cred


@router.get("/{credential_id}/reveal")
async def reveal_credential(credential_id: UUID, db: AsyncSession = Depends(get_db)):
    """Disabled: raw credential reveal is not allowed over the API."""
    cred = await db.get(Credential, credential_id)
    if not cred:
        raise HTTPException(404, "Credential not found")
    raise HTTPException(403, "Credential reveal is disabled. Update or replace the credential instead.")


@router.delete("/{credential_id}", status_code=204)
async def delete_credential(credential_id: UUID, db: AsyncSession = Depends(get_db)):
    cred = await db.get(Credential, credential_id)
    if not cred:
        raise HTTPException(404, "Credential not found")
    await _invalidate_credential_prompt_caches(credential_id, db)
    await db.delete(cred)
    await db.commit()
