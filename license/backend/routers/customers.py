"""Router: /api/v1/customers"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import crud
import schemas
from database import get_db

router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


@router.get("", response_model=list[schemas.CustomerResponse])
def list_customers(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return crud.get_customers(db, skip=skip, limit=limit)


@router.post("", response_model=schemas.CustomerResponse, status_code=201)
def create_customer(data: schemas.CustomerCreate, db: Session = Depends(get_db)):
    existing = crud.get_customer(db, data.customer_id)
    if existing:
        raise HTTPException(status_code=400, detail=f"Customer '{data.customer_id}' already exists")
    return crud.create_customer(db, data)


@router.get("/{customer_id}", response_model=schemas.CustomerWithLicenses)
def get_customer(customer_id: str, db: Session = Depends(get_db)):
    customer = crud.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer '{customer_id}' not found")
    return customer


@router.put("/{customer_id}", response_model=schemas.CustomerResponse)
def update_customer(
    customer_id: str, data: schemas.CustomerUpdate, db: Session = Depends(get_db)
):
    customer = crud.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer '{customer_id}' not found")
    return crud.update_customer(db, customer, data)


@router.delete("/{customer_id}", status_code=204)
def delete_customer(customer_id: str, db: Session = Depends(get_db)):
    customer = crud.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer '{customer_id}' not found")
    if crud.has_active_licenses(db, customer_id):
        raise HTTPException(
            status_code=400,
            detail="Cannot delete customer with active licenses. Revoke all licenses first.",
        )
    crud.delete_customer(db, customer)
