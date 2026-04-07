from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator


# ─── Customer ────────────────────────────────────────────────────────────────

class CustomerCreate(BaseModel):
    customer_id: Optional[str] = None  # auto-generated if omitted
    name: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    contact_person: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None


class CustomerResponse(BaseModel):
    id: int
    customer_id: str
    name: str
    contact_person: Optional[str]
    email: Optional[str]
    notes: Optional[str]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CustomerWithLicenses(CustomerResponse):
    licenses: list["LicenseResponse"] = []

    model_config = {"from_attributes": True}


# ─── License ──────────────────────────────────────────────────────────────────

class LicenseCreate(BaseModel):
    customer_id: str
    key_pair_id: int  # which key pair to sign with (one customer = one key pair)
    license_type: str  # trial / commercial / permanent
    capabilities: list[str]
    operating_system: str
    application_name: str
    machine_fingerprint: Optional[str] = None
    minimum_os_version: Optional[str] = None
    system_architecture: Optional[str] = None
    valid_from: datetime
    valid_until: Optional[datetime] = None
    version_constraint: str = ">=1.0.0"
    max_instances: int = 4
    privkey_path: Optional[str] = None  # deprecated: private key is resolved from server-managed key store

    @field_validator("operating_system")
    @classmethod
    def validate_operating_system(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"windows", "linux", "android", "ios"}:
            raise ValueError("operating_system must be one of: windows, linux, android, ios")
        return normalized

    @field_validator("application_name")
    @classmethod
    def validate_application_name(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("application_name cannot be empty")
        return normalized

    @field_validator("minimum_os_version", "system_architecture", mode="before")
    @classmethod
    def normalize_environment_strings(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("machine_fingerprint", mode="before")
    @classmethod
    def normalize_machine_fingerprint(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    @field_validator("version_constraint", mode="before")
    @classmethod
    def normalize_version_constraint(cls, value):
        if value is None:
            return ">=1.0.0"
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or ">=1.0.0"
        return value


class LicenseResponse(BaseModel):
    id: int
    license_id: str
    customer_id: str
    key_pair_id: Optional[int] = None
    key_pair_name: Optional[str] = None
    license_type: str
    capabilities: list[str]
    operating_system: Optional[str] = None
    minimum_os_version: Optional[str] = None
    system_architecture: Optional[str] = None
    application_name: Optional[str] = None
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
    privkey_path: Optional[str] = None


class ExpiringLicenseResponse(BaseModel):
    days: int
    licenses: list[LicenseResponse]


# ─── KeyPair ──────────────────────────────────────────────────────────────────

class KeyPairCreate(BaseModel):
    name: str
    privkey_output_path: Optional[str] = None  # deprecated: backend now stores keys in a controlled directory


class KeyPairResponse(BaseModel):
    id: int
    name: str
    public_key_pem: str
    created_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


# ─── ProdAdminToken ───────────────────────────────────────────────────────────

class ProdAdminTokenCreate(BaseModel):
    token_name: str
    environment: Optional[str] = None
    created_by: Optional[str] = None
    expires_at: Optional[datetime] = None


class ProdAdminTokenResponse(BaseModel):
    id: int
    token_name: str
    token_hash: str  # only first 8 chars for display
    environment: Optional[str]
    created_at: datetime
    created_by: Optional[str]
    expires_at: Optional[datetime]
    is_active: bool
    last_used_at: Optional[datetime]
    usage_count: int

    model_config = {"from_attributes": True}


class ProdAdminTokenWithPlaintext(ProdAdminTokenResponse):
    """Only returned once during creation — includes the plaintext token."""
    plaintext_token: str


class ProdAdminTokenUpdate(BaseModel):
    is_active: Optional[bool] = None
    expires_at: Optional[datetime] = None


# Update forward references
CustomerWithLicenses.model_rebuild()
