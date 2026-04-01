"""Models router — model version management."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from typing import Optional
import os

import crud
from database import get_db
from schemas import ModelVersionOut

router = APIRouter(prefix="/api/v1/models", tags=["models"])


@router.get("/", response_model=list[ModelVersionOut])
def list_models(
    capability_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return crud.list_model_versions(db, capability_id=capability_id)


@router.get("/{version_id}", response_model=ModelVersionOut)
def get_model(version_id: int, db: Session = Depends(get_db)):
    obj = crud.get_model_version(db, version_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Model version not found")
    return obj


@router.post("/{version_id}/set-current", response_model=ModelVersionOut)
def set_current(version_id: int, db: Session = Depends(get_db)):
    obj = crud.get_model_version(db, version_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Model version not found")
    return crud.set_current_version(db, obj)


@router.post("/{version_id}/unset-current", response_model=ModelVersionOut)
def unset_current(version_id: int, db: Session = Depends(get_db)):
    obj = crud.get_model_version(db, version_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Model version not found")
    if not obj.is_current:
        raise HTTPException(status_code=400, detail="Model version is not currently set as current")
    return crud.unset_current_version(db, obj)


@router.get("/{version_id}/download")
def download_manifest(version_id: int, db: Session = Depends(get_db)):
    obj = crud.get_model_version(db, version_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Model version not found")
    if not obj.manifest_path or not os.path.exists(obj.manifest_path):
        raise HTTPException(status_code=404, detail="manifest.json not found")
    return FileResponse(obj.manifest_path, filename="manifest.json")
