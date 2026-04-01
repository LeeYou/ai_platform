"""Router: /api/v1/prod-tokens — Production Admin Token Management"""

import hashlib
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import crud
import schemas
from database import get_db

router = APIRouter(prefix="/api/v1/prod-tokens", tags=["prod-tokens"])


def _hash_token(plaintext: str) -> str:
    """Generate SHA-256 hash of the token."""
    return hashlib.sha256(plaintext.encode()).hexdigest()


def _generate_secure_token() -> str:
    """Generate a cryptographically secure random token (64 hex chars = 256 bits)."""
    return secrets.token_hex(32)


@router.get("", response_model=list[schemas.ProdAdminTokenResponse])
def list_tokens(db: Session = Depends(get_db)):
    """List all production admin tokens (hashes only, not plaintext)."""
    tokens = crud.get_prod_admin_tokens(db)
    # Truncate hash for display (show only first 8 chars)
    result = []
    for token in tokens:
        token_dict = schemas.ProdAdminTokenResponse.model_validate(token).model_dump()
        token_dict["token_hash"] = token.token_hash[:8] + "..."
        result.append(schemas.ProdAdminTokenResponse.model_validate(token_dict))
    return result


@router.post("", response_model=schemas.ProdAdminTokenWithPlaintext, status_code=201)
def create_token(data: schemas.ProdAdminTokenCreate, db: Session = Depends(get_db)):
    """
    Generate a new production admin token.

    Returns the plaintext token ONLY ONCE. It will never be shown again.
    The database only stores the SHA-256 hash.
    """
    # Check for duplicate name
    existing = crud.get_prod_admin_token_by_name(db, data.token_name)
    if existing:
        raise HTTPException(status_code=400, detail=f"Token name '{data.token_name}' already exists")

    # Generate secure random token
    plaintext_token = _generate_secure_token()
    token_hash = _hash_token(plaintext_token)

    # Create database record
    token_record = crud.create_prod_admin_token(
        db,
        token_name=data.token_name,
        token_hash=token_hash,
        environment=data.environment,
        created_by=data.created_by,
        expires_at=data.expires_at,
    )

    # Return response with plaintext (only time it's shown)
    response = schemas.ProdAdminTokenWithPlaintext.model_validate(token_record)
    response.plaintext_token = plaintext_token
    response.token_hash = token_hash[:8] + "..."  # truncate for display

    return response


@router.get("/{token_id}", response_model=schemas.ProdAdminTokenResponse)
def get_token(token_id: int, db: Session = Depends(get_db)):
    """Get details of a specific token (hash only)."""
    token = crud.get_prod_admin_token(db, token_id)
    if not token:
        raise HTTPException(status_code=404, detail=f"Token {token_id} not found")

    response = schemas.ProdAdminTokenResponse.model_validate(token)
    response.token_hash = token.token_hash[:8] + "..."
    return response


@router.put("/{token_id}", response_model=schemas.ProdAdminTokenResponse)
def update_token(token_id: int, data: schemas.ProdAdminTokenUpdate, db: Session = Depends(get_db)):
    """Update token status (activate/deactivate) or expiration."""
    token = crud.get_prod_admin_token(db, token_id)
    if not token:
        raise HTTPException(status_code=404, detail=f"Token {token_id} not found")

    updated = crud.update_prod_admin_token(db, token, data)
    response = schemas.ProdAdminTokenResponse.model_validate(updated)
    response.token_hash = updated.token_hash[:8] + "..."
    return response


@router.delete("/{token_id}", status_code=204)
def delete_token(token_id: int, db: Session = Depends(get_db)):
    """Delete a production admin token."""
    token = crud.get_prod_admin_token(db, token_id)
    if not token:
        raise HTTPException(status_code=404, detail=f"Token {token_id} not found")

    crud.delete_prod_admin_token(db, token)
    return None


@router.post("/verify", response_model=dict)
def verify_token(plaintext_token: str, db: Session = Depends(get_db)):
    """
    Verify a plaintext token against stored hashes.

    This endpoint can be called by the production service to validate tokens.
    Returns token metadata if valid, raises 401 if invalid.
    """
    token_hash = _hash_token(plaintext_token)

    # Find token by hash
    all_tokens = crud.get_prod_admin_tokens(db)
    for token in all_tokens:
        if token.token_hash == token_hash:
            # Check if token is active
            if not token.is_active:
                raise HTTPException(status_code=401, detail="Token is inactive")

            # Check if token is expired
            if token.expires_at and token.expires_at < datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="Token is expired")

            # Record usage
            crud.record_token_usage(db, token)

            return {
                "valid": True,
                "token_id": token.id,
                "token_name": token.token_name,
                "environment": token.environment,
            }

    # Token not found
    raise HTTPException(status_code=401, detail="Invalid token")
