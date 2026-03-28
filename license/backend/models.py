from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    customer_id: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_person: Mapped[str] = mapped_column(String(255), nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    notes: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    licenses: Mapped[list["LicenseRecord"]] = relationship(
        "LicenseRecord", back_populates="customer", foreign_keys="LicenseRecord.customer_id"
    )


class LicenseRecord(Base):
    __tablename__ = "license_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    license_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    customer_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("customers.customer_id"), nullable=False
    )
    license_type: Mapped[str] = mapped_column(String(32), nullable=False)  # trial/commercial/permanent
    capabilities: Mapped[str] = mapped_column(Text, nullable=False)  # JSON array as text
    machine_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version_constraint: Mapped[str] = mapped_column(String(64), nullable=False, default=">=1.0.0")
    max_instances: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # active/expired/revoked
    license_content: Mapped[str] = mapped_column(Text, nullable=False)  # full signed JSON
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    customer: Mapped["Customer"] = relationship(
        "Customer", back_populates="licenses", foreign_keys=[customer_id]
    )


class KeyPair(Base):
    __tablename__ = "key_pairs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    public_key_pem: Mapped[str] = mapped_column(Text, nullable=False)
    # private key is NEVER stored in DB — only on disk/HSM
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
