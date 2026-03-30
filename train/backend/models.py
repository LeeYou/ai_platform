"""SQLAlchemy ORM models for the training management backend."""

from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Capability
# ---------------------------------------------------------------------------

class Capability(Base):
    """An AI capability (e.g., face_detect) with its training configuration."""

    __tablename__ = "capabilities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name_cn: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    dataset_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    script_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    hyperparams: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    jobs: Mapped[list["TrainingJob"]] = relationship("TrainingJob", back_populates="capability")
    model_versions: Mapped[list["ModelVersion"]] = relationship(
        "ModelVersion", back_populates="capability"
    )


# ---------------------------------------------------------------------------
# TrainingJob
# ---------------------------------------------------------------------------

class TrainingJob(Base):
    """A single training run for a capability."""

    __tablename__ = "training_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    capability_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("capabilities.id"), nullable=False, index=True
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    # pending | running | paused | done | failed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    celery_task_id: Mapped[str] = mapped_column(String(128), nullable=True)
    pid: Mapped[int] = mapped_column(Integer, nullable=True)
    log_path: Mapped[str] = mapped_column(String(512), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    error_msg: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    capability: Mapped["Capability"] = relationship("Capability", back_populates="jobs")
    model_versions: Mapped[list["ModelVersion"]] = relationship(
        "ModelVersion", back_populates="job"
    )


# ---------------------------------------------------------------------------
# ModelVersion
# ---------------------------------------------------------------------------

class ModelVersion(Base):
    """An exported model package produced by a training job."""

    __tablename__ = "model_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    capability_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("capabilities.id"), nullable=False, index=True
    )
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("training_jobs.id"), nullable=True
    )
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    manifest_path: Mapped[str] = mapped_column(String(512), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    capability: Mapped["Capability"] = relationship(
        "Capability", back_populates="model_versions"
    )
    job: Mapped["TrainingJob"] = relationship("TrainingJob", back_populates="model_versions")


# ---------------------------------------------------------------------------
# AnnotationProject
# ---------------------------------------------------------------------------

class AnnotationProject(Base):
    """A sample annotation project linked to an AI capability."""
    __tablename__ = "annotation_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    capability_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("capabilities.id"), nullable=False, index=True
    )
    annotation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    # binary_classification | multi_classification | object_detection | ocr | segmentation
    network_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    dataset_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    label_config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    # in_progress | completed | archived
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="in_progress")
    total_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    annotated_samples: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    capability: Mapped["Capability"] = relationship("Capability")
    records: Mapped[list["AnnotationRecord"]] = relationship(
        "AnnotationRecord", back_populates="project", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# AnnotationRecord
# ---------------------------------------------------------------------------

class AnnotationRecord(Base):
    """A single annotation for a sample in an annotation project."""
    __tablename__ = "annotation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("annotation_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    annotation_data: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    annotated_by: Mapped[str] = mapped_column(String(64), nullable=False, default="default")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    project: Mapped["AnnotationProject"] = relationship(
        "AnnotationProject", back_populates="records"
    )
