"""Router: /api/v1/licenses"""

import json
import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import crud
import schemas
from database import get_db
from key_store import has_private_key, read_private_key
from license_signer import sign_license, verify_license as verify_sig

# CST timezone (UTC+8) - Standard timezone for all license operations
CST = timezone(timedelta(hours=8))

LICENSES_DIR = os.environ.get("LICENSES_DIR", "./data/licenses")

router = APIRouter(prefix="/api/v1/licenses", tags=["licenses"])
MISSING_PRIVATE_KEY_DETAIL = (
    "Key pair '{name}' is unavailable because its server-side private key file is missing. "
    "Please create/select a new key pair and retry."
)


def _verify_key_match(privkey_pem: str, pubkey_pem: str) -> None:
    """Verify private key matches the stored public key by sign/verify round-trip."""
    test_data = {"_verify": "key_match_check"}
    signed = sign_license(test_data, privkey_pem)
    if not verify_sig(signed, pubkey_pem):
        raise HTTPException(
            status_code=400,
            detail="Private key does not match the public key of the selected key pair",
        )


def _verify_signed_license(signed_json: str, pubkey_pem: str) -> None:
    """Fail fast if the just-signed license cannot be verified by the selected public key."""
    if not verify_sig(signed_json, pubkey_pem):
        raise HTTPException(
            status_code=500,
            detail="Internal signing verification failed after license generation",
        )


def _save_license_file(license_id: str, content: str) -> str:
    os.makedirs(LICENSES_DIR, exist_ok=True)
    filepath = os.path.join(LICENSES_DIR, f"{license_id}.bin")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath


def _load_private_key_or_raise(key_pair) -> str:
    if not has_private_key(key_pair):
        raise HTTPException(
            status_code=400,
            detail=MISSING_PRIVATE_KEY_DETAIL.format(name=key_pair.name),
        )
    try:
        return read_private_key(key_pair)
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=400,
            detail=MISSING_PRIVATE_KEY_DETAIL.format(name=key_pair.name),
        ) from exc


def _license_to_response(record, request_base_url: str = "") -> schemas.LicenseResponse:
    data = schemas.LicenseResponse.model_validate(record)
    data.download_url = f"{request_base_url}/api/v1/licenses/{record.license_id}/download"
    if data.valid_until:
        data.days_remaining = (data.valid_until.astimezone(CST).date() - datetime.now(CST).date()).days
    # Populate key_pair_name from relationship
    if record.key_pair:
        data.key_pair_name = record.key_pair.name
    return data


@router.get("/expiring", response_model=schemas.ExpiringLicenseResponse)
def get_expiring_licenses(
    days: int = Query(30, ge=1, description="Number of days ahead to check"),
    db: Session = Depends(get_db),
):
    records = crud.get_expiring_licenses(db, days)
    licenses = [_license_to_response(r) for r in records]
    return schemas.ExpiringLicenseResponse(days=days, licenses=licenses)


@router.get("", response_model=list[schemas.LicenseResponse])
def list_licenses(
    customer_id: str | None = Query(None),
    status: str | None = Query(None),
    expiring_in_days: int | None = Query(None, ge=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    if expiring_in_days is not None:
        records = crud.get_expiring_licenses(db, expiring_in_days)
        return [_license_to_response(r) for r in records]
    records = crud.get_licenses(db, customer_id=customer_id, status=status, skip=skip, limit=limit)
    return [_license_to_response(r) for r in records]


@router.post("", response_model=schemas.LicenseResponse, status_code=201)
def create_license(data: schemas.LicenseCreate, db: Session = Depends(get_db)):
    customer = crud.get_customer(db, data.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer '{data.customer_id}' not found")

    # Validate key pair exists and is active
    key_pair = crud.get_key_pair(db, data.key_pair_id)
    if not key_pair:
        raise HTTPException(status_code=404, detail=f"Key pair {data.key_pair_id} not found")
    if not key_pair.is_active:
        raise HTTPException(status_code=400, detail=f"Key pair '{key_pair.name}' is inactive")

    privkey_pem = _load_private_key_or_raise(key_pair)
    # Verify private key matches the selected key pair's public key
    _verify_key_match(privkey_pem, key_pair.public_key_pem)

    issued_at = datetime.now(CST)
    license_id = crud.generate_license_id(db)

    license_data = {
        "license_id": license_id,
        "customer_id": data.customer_id,
        "customer_name": customer.name,
        "license_type": data.license_type,
        "capabilities": data.capabilities,
        "operating_system": data.operating_system,
        "minimum_os_version": data.minimum_os_version or "",
        "system_architecture": data.system_architecture or "",
        "application_name": data.application_name,
        "machine_fingerprint": data.machine_fingerprint or "",
        "valid_from": data.valid_from.isoformat(),
        "valid_until": data.valid_until.isoformat() if data.valid_until else "",
        "version_constraint": data.version_constraint,
        "max_instances": data.max_instances,
        "issuer": os.environ.get("LICENSE_ISSUER", "agilestar.cn"),
        "issued_at": issued_at.isoformat(),
    }

    signed_json = sign_license(license_data, privkey_pem)
    _verify_signed_license(signed_json, key_pair.public_key_pem)
    _save_license_file(license_id, signed_json)

    record = crud.create_license_record(db, license_id, data, signed_json, issued_at)
    return _license_to_response(record)


@router.get("/{license_id}", response_model=schemas.LicenseResponse)
def get_license(license_id: str, db: Session = Depends(get_db)):
    record = crud.get_license(db, license_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"License '{license_id}' not found")
    return _license_to_response(record)


@router.get("/{license_id}/download")
def download_license(license_id: str, db: Session = Depends(get_db)):
    record = crud.get_license(db, license_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"License '{license_id}' not found")

    filepath = os.path.join(LICENSES_DIR, f"{license_id}.bin")
    if not os.path.isfile(filepath):
        # Regenerate from stored content
        _save_license_file(license_id, record.license_content)

    return FileResponse(
        path=filepath,
        media_type="application/octet-stream",
        filename=f"{license_id}.bin",
    )


@router.post("/{license_id}/renew", response_model=schemas.LicenseResponse)
def renew_license(license_id: str, data: schemas.LicenseRenew, db: Session = Depends(get_db)):
    record = crud.get_license(db, license_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"License '{license_id}' not found")
    if record.status == "revoked":
        raise HTTPException(status_code=400, detail="Cannot renew a revoked license")

    key_pair = record.key_pair or (crud.get_key_pair(db, record.key_pair_id) if record.key_pair_id else None)
    if not key_pair:
        raise HTTPException(status_code=400, detail="License has no associated key pair")
    privkey_pem = _load_private_key_or_raise(key_pair)
    _verify_key_match(privkey_pem, key_pair.public_key_pem)
    issued_at = datetime.now(CST)

    old_data = json.loads(record.license_content)
    old_data.pop("signature", None)
    old_data["valid_until"] = data.valid_until.isoformat()
    old_data["issued_at"] = issued_at.isoformat()
    # Normalize legacy null fields to "" for consistent canonical JSON.
    for _str_field in ("minimum_os_version", "system_architecture", "machine_fingerprint"):
        if old_data.get(_str_field) is None:
            old_data[_str_field] = ""

    signed_json = sign_license(old_data, privkey_pem)
    _verify_signed_license(signed_json, key_pair.public_key_pem)
    _save_license_file(license_id, signed_json)

    updated = crud.update_license_content(db, record, signed_json, data.valid_until, issued_at)
    if updated.status != "active":
        updated.status = "active"
        db.commit()
        db.refresh(updated)

    return _license_to_response(updated)


@router.post("/{license_id}/revoke", response_model=schemas.LicenseResponse)
def revoke_license(license_id: str, db: Session = Depends(get_db)):
    record = crud.get_license(db, license_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"License '{license_id}' not found")
    if record.status == "revoked":
        raise HTTPException(status_code=400, detail="License is already revoked")
    updated = crud.revoke_license(db, record)
    return _license_to_response(updated)
