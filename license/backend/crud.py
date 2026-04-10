"""CRUD helper functions for the license management backend."""

import json
import os
from datetime import datetime, timezone, timedelta

from sqlalchemy.orm import Session

import models
import schemas

# CST timezone (UTC+8) - Standard timezone for all license operations
CST = timezone(timedelta(hours=8))


# ─── License ID generation ───────────────────────────────────────────────────

def generate_license_id(db: Session) -> str:
    today = datetime.now(CST).strftime("%Y%m%d")
    prefix = f"LS-{today}-"
    count = (
        db.query(models.LicenseRecord)
        .filter(models.LicenseRecord.license_id.like(f"{prefix}%"))
        .count()
    )
    return f"{prefix}{(count + 1):04d}"


# ─── Customer CRUD ───────────────────────────────────────────────────────────

def get_customers(db: Session, skip: int = 0, limit: int = 100) -> list[models.Customer]:
    return db.query(models.Customer).offset(skip).limit(limit).all()


def get_customer(db: Session, customer_id: str) -> models.Customer | None:
    return (
        db.query(models.Customer)
        .filter(models.Customer.customer_id == customer_id)
        .first()
    )


def create_customer(db: Session, data: schemas.CustomerCreate) -> models.Customer:
    customer = models.Customer(**data.model_dump())
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def update_customer(
    db: Session, customer: models.Customer, data: schemas.CustomerUpdate
) -> models.Customer:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(customer, field, value)
    customer.updated_at = datetime.now(CST)
    db.commit()
    db.refresh(customer)
    return customer


def delete_customer(db: Session, customer: models.Customer) -> None:
    db.delete(customer)
    db.commit()


def has_active_licenses(db: Session, customer_id: str) -> bool:
    return (
        db.query(models.LicenseRecord)
        .filter(
            models.LicenseRecord.customer_id == customer_id,
            models.LicenseRecord.status == "active",
        )
        .count()
        > 0
    )


# ─── LicenseRecord CRUD ──────────────────────────────────────────────────────

def get_licenses(
    db: Session,
    customer_id: str | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 100,
) -> list[models.LicenseRecord]:
    q = db.query(models.LicenseRecord)
    if customer_id:
        q = q.filter(models.LicenseRecord.customer_id == customer_id)
    if status:
        q = q.filter(models.LicenseRecord.status == status)
    return q.offset(skip).limit(limit).all()


def get_dashboard_stats(db: Session) -> dict:
    from datetime import timedelta

    now = datetime.now(CST)
    total_customers = db.query(models.Customer).count()
    active_licenses = (
        db.query(models.LicenseRecord)
        .filter(models.LicenseRecord.status == "active")
        .count()
    )
    cutoff_30 = now + timedelta(days=30)
    expiring_30 = (
        db.query(models.LicenseRecord)
        .filter(
            models.LicenseRecord.status == "active",
            models.LicenseRecord.valid_until.isnot(None),
            models.LicenseRecord.valid_until <= cutoff_30,
            models.LicenseRecord.valid_until > now,
        )
        .count()
    )
    cutoff_7 = now + timedelta(days=7)
    expiring_7 = (
        db.query(models.LicenseRecord)
        .filter(
            models.LicenseRecord.status == "active",
            models.LicenseRecord.valid_until.isnot(None),
            models.LicenseRecord.valid_until <= cutoff_7,
            models.LicenseRecord.valid_until > now,
        )
        .count()
    )
    return {
        "total_customers": total_customers,
        "active_licenses": active_licenses,
        "expiring_30": expiring_30,
        "expiring_7": expiring_7,
    }


def get_expiring_licenses(db: Session, days: int) -> list[models.LicenseRecord]:
    now = datetime.now(CST)
    cutoff = now + timedelta(days=days)
    return (
        db.query(models.LicenseRecord)
        .filter(
            models.LicenseRecord.status == "active",
            models.LicenseRecord.valid_until.isnot(None),
            models.LicenseRecord.valid_until <= cutoff,
            models.LicenseRecord.valid_until > now,
        )
        .all()
    )


def get_license(db: Session, license_id: str) -> models.LicenseRecord | None:
    return (
        db.query(models.LicenseRecord)
        .filter(models.LicenseRecord.license_id == license_id)
        .first()
    )


def create_license_record(
    db: Session,
    license_id: str,
    data: schemas.LicenseCreate,
    license_content: str,
    issued_at: datetime,
) -> models.LicenseRecord:
    record = models.LicenseRecord(
        license_id=license_id,
        customer_id=data.customer_id,
        key_pair_id=data.key_pair_id,
        license_type=data.license_type,
        capabilities=json.dumps(data.capabilities, ensure_ascii=False),
        operating_system=data.operating_system,
        minimum_os_version=data.minimum_os_version,
        system_architecture=data.system_architecture,
        application_name=data.application_name,
        machine_fingerprint=data.machine_fingerprint,
        valid_from=data.valid_from,
        valid_until=data.valid_until,
        version_constraint=data.version_constraint,
        max_instances=data.max_instances,
        status="active",
        license_content=license_content,
        issued_at=issued_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_license_content(
    db: Session,
    record: models.LicenseRecord,
    license_content: str,
    valid_until: datetime,
    issued_at: datetime,
) -> models.LicenseRecord:
    record.license_content = license_content
    record.valid_until = valid_until
    record.issued_at = issued_at
    db.commit()
    db.refresh(record)
    return record


def revoke_license(db: Session, record: models.LicenseRecord) -> models.LicenseRecord:
    record.status = "revoked"
    db.commit()
    db.refresh(record)
    return record


# ─── KeyPair CRUD ────────────────────────────────────────────────────────────

def get_key_pairs(db: Session) -> list[models.KeyPair]:
    return db.query(models.KeyPair).all()


def get_key_pair(db: Session, key_id: int) -> models.KeyPair | None:
    return db.query(models.KeyPair).filter(models.KeyPair.id == key_id).first()


def create_key_pair(db: Session, name: str, public_key_pem: str) -> models.KeyPair:
    kp = models.KeyPair(name=name, public_key_pem=public_key_pem)
    db.add(kp)
    db.commit()
    db.refresh(kp)
    return kp


# ─── ProdAdminToken CRUD ─────────────────────────────────────────────────────

def get_prod_admin_tokens(db: Session) -> list[models.ProdAdminToken]:
    return db.query(models.ProdAdminToken).order_by(models.ProdAdminToken.id.desc()).all()


def get_prod_admin_token(db: Session, token_id: int) -> models.ProdAdminToken | None:
    return db.query(models.ProdAdminToken).filter(models.ProdAdminToken.id == token_id).first()


def get_prod_admin_token_by_name(db: Session, token_name: str) -> models.ProdAdminToken | None:
    return db.query(models.ProdAdminToken).filter(models.ProdAdminToken.token_name == token_name).first()


def create_prod_admin_token(
    db: Session,
    token_name: str,
    token_hash: str,
    environment: str | None = None,
    created_by: str | None = None,
    expires_at: datetime | None = None,
) -> models.ProdAdminToken:
    token = models.ProdAdminToken(
        token_name=token_name,
        token_hash=token_hash,
        environment=environment,
        created_by=created_by,
        expires_at=expires_at,
    )
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def update_prod_admin_token(
    db: Session,
    token: models.ProdAdminToken,
    data: schemas.ProdAdminTokenUpdate,
) -> models.ProdAdminToken:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(token, field, value)
    db.commit()
    db.refresh(token)
    return token


def delete_prod_admin_token(db: Session, token: models.ProdAdminToken) -> None:
    db.delete(token)
    db.commit()


def record_token_usage(db: Session, token: models.ProdAdminToken) -> None:
    """Record that a token was used (for audit purposes)."""
    token.last_used_at = datetime.now(CST)
    token.usage_count += 1
    db.commit()
