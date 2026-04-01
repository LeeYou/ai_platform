"""Capabilities router — CRUD for AI capability configurations."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import crud
from database import get_db
from schemas import CapabilityCreate, CapabilityOut, CapabilityUpdate

router = APIRouter(prefix="/api/v1/capabilities", tags=["capabilities"])


@router.get("/", response_model=list[CapabilityOut])
def list_capabilities(db: Session = Depends(get_db)):
    return crud.list_capabilities(db)


@router.post("/", response_model=CapabilityOut, status_code=status.HTTP_201_CREATED)
def create_capability(data: CapabilityCreate, db: Session = Depends(get_db)):
    if crud.get_capability_by_name(db, data.name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Capability '{data.name}' already exists",
        )
    return crud.create_capability(db, data)


@router.get("/{capability_id}", response_model=CapabilityOut)
def get_capability(capability_id: int, db: Session = Depends(get_db)):
    obj = crud.get_capability(db, capability_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Capability not found")
    return obj


@router.put("/{capability_id}", response_model=CapabilityOut)
def update_capability(
    capability_id: int, data: CapabilityUpdate, db: Session = Depends(get_db)
):
    obj = crud.get_capability(db, capability_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Capability not found")
    return crud.update_capability(db, obj, data)


@router.delete("/{capability_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_capability(capability_id: int, db: Session = Depends(get_db)):
    obj = crud.get_capability(db, capability_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Capability not found")
    crud.delete_capability(db, obj)
