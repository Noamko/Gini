"""Credential CRUD endpoints — values are never exposed in responses."""
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.credential import Credential
from app.schemas.credential import CredentialCreate, CredentialResponse, CredentialUpdate
from app.services.credential_vault import decrypt_value, encrypt_value

logger = structlog.get_logger("credentials_api")

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


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
    return cred


@router.get("/{credential_id}/reveal")
async def reveal_credential(credential_id: UUID, db: AsyncSession = Depends(get_db)):
    """Return the decrypted credential value."""
    cred = await db.get(Credential, credential_id)
    if not cred:
        raise HTTPException(404, "Credential not found")
    try:
        value = decrypt_value(cred.encrypted_value)
    except Exception:
        raise HTTPException(500, "Failed to decrypt credential") from None
    return {"value": value}


@router.delete("/{credential_id}", status_code=204)
async def delete_credential(credential_id: UUID, db: AsyncSession = Depends(get_db)):
    cred = await db.get(Credential, credential_id)
    if not cred:
        raise HTTPException(404, "Credential not found")
    await db.delete(cred)
    await db.commit()
