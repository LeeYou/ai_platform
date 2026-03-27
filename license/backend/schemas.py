from datetime import datetime
from typing import Optional
from pydantic import BaseModel, field_validator


# ─── Customer ────────────────────────────────────────────────────────────────

class CustomerCreate(BaseModel):
    customer_id: str
    name: str
    contact: Optional[str] = None
    email: Optional[str] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    contact: Optional[str] = None
    email: Optional[str] = None


class CustomerResponse(BaseModel):
    id: int
    customer_id: str
    name: str
    contact: Optional[str]
    email: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CustomerWithLicenses(CustomerResponse):
    licenses: list["LicenseResponse"] = []

    model_config = {"from_attributes": True}


# ─── License ──────────────────────────────────────────────────────────────────

class LicenseCreate(BaseModel):
    customer_id: str
    license_type: str  # trial / commercial / permanent
    capabilities: list[str]
    machine_fingerprint: Optional[str] = None
    valid_from: datetime
    valid_until: Optional[datetime] = None
    version_constraint: str = ">=1.0.0"
    max_instances: int = 4
    privkey_path: str  # path to PEM private key file on server


class LicenseResponse(BaseModel):
    id: int
    license_id: str
    customer_id: str
    license_type: str
    capabilities: list[str]
    machine_fingerprint: Optional[str]
    valid_from: datetime
    valid_until: Optional[datetime]
    version_constraint: str
    max_instances: int
    status: str
    issued_at: datetime
    created_at: datetime
    download_url: Optional[str] = None

    model_config = {"from_attributes": True}

    @field_validator("capabilities", mode="before")
    @classmethod
    def parse_capabilities(cls, v):
        if isinstance(v, str):
            import json
            return json.loads(v)
        return v


class LicenseRenew(BaseModel):
    valid_until: datetime
    privkey_path: str


class ExpiringLicenseResponse(BaseModel):
    days: int
    licenses: list[LicenseResponse]


# ─── KeyPair ──────────────────────────────────────────────────────────────────

class KeyPairCreate(BaseModel):
    name: str
    privkey_output_path: str  # where to write the private key PEM on disk


class KeyPairResponse(BaseModel):
    id: int
    name: str
    public_key_pem: str
    created_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


# Update forward references
CustomerWithLicenses.model_rebuild()
