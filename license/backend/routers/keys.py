"""Router: /api/v1/keys"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

import crud
import schemas
from database import get_db
from key_store import has_private_key, write_private_key
from license_signer import generate_key_pair

router = APIRouter(prefix="/api/v1/keys", tags=["keys"])


def _key_pair_to_response(key_pair) -> schemas.KeyPairResponse:
    data = schemas.KeyPairResponse.model_validate(key_pair)
    data.private_key_available = has_private_key(key_pair)
    return data


@router.get("", response_model=list[schemas.KeyPairResponse])
def list_keys(db: Session = Depends(get_db)):
    return [_key_pair_to_response(key_pair) for key_pair in crud.get_key_pairs(db)]


@router.post("", response_model=schemas.KeyPairResponse, status_code=201)
def create_key(data: schemas.KeyPairCreate, db: Session = Depends(get_db)):
    private_pem, public_pem = generate_key_pair()
    key_pair = crud.create_key_pair(db, name=data.name, public_key_pem=public_pem)
    try:
        write_private_key(key_pair, private_pem)
    except Exception as exc:
        db.delete(key_pair)
        db.commit()
        raise HTTPException(status_code=500, detail=f"Failed to persist private key: {exc}") from exc
    return _key_pair_to_response(key_pair)


@router.get("/{key_id}/public", response_class=PlainTextResponse)
def download_public_key(key_id: int, db: Session = Depends(get_db)):
    kp = crud.get_key_pair(db, key_id)
    if not kp:
        raise HTTPException(status_code=404, detail=f"Key pair {key_id} not found")
    return PlainTextResponse(content=kp.public_key_pem, media_type="application/x-pem-file")
