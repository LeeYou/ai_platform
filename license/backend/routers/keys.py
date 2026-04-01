"""Router: /api/v1/keys"""

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

import crud
import schemas
from database import get_db
from license_signer import generate_key_pair

router = APIRouter(prefix="/api/v1/keys", tags=["keys"])


@router.get("", response_model=list[schemas.KeyPairResponse])
def list_keys(db: Session = Depends(get_db)):
    return crud.get_key_pairs(db)


@router.post("", response_model=schemas.KeyPairResponse, status_code=201)
def create_key(data: schemas.KeyPairCreate, db: Session = Depends(get_db)):
    private_pem, public_pem = generate_key_pair()

    # Write private key to specified path (never stored in DB)
    priv_dir = os.path.dirname(data.privkey_output_path)
    if priv_dir:
        os.makedirs(priv_dir, exist_ok=True)
    with open(data.privkey_output_path, "w") as f:
        f.write(private_pem)
    # Restrict permissions on private key file
    os.chmod(data.privkey_output_path, 0o600)

    return crud.create_key_pair(db, name=data.name, public_key_pem=public_pem)


@router.get("/{key_id}/public", response_class=PlainTextResponse)
def download_public_key(key_id: int, db: Session = Depends(get_db)):
    kp = crud.get_key_pair(db, key_id)
    if not kp:
        raise HTTPException(status_code=404, detail=f"Key pair {key_id} not found")
    return PlainTextResponse(content=kp.public_key_pem, media_type="application/x-pem-file")
