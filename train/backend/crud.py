"""CRUD helpers for the training management backend."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from models import AnnotationProject, AnnotationRecord, Capability, ModelVersion, TrainingJob
from schemas import (
    AnnotationProjectCreate,
    AnnotationProjectUpdate,
    AnnotationRecordCreate,
    CapabilityCreate,
    CapabilityUpdate,
    TrainingJobCreate,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Capability CRUD
# ---------------------------------------------------------------------------

def get_capability(db: Session, capability_id: int) -> Optional[Capability]:
    return db.get(Capability, capability_id)


def get_capability_by_name(db: Session, name: str) -> Optional[Capability]:
    return db.query(Capability).filter(Capability.name == name).first()


def list_capabilities(db: Session) -> list[Capability]:
    return db.query(Capability).order_by(Capability.id).all()


def create_capability(db: Session, data: CapabilityCreate) -> Capability:
    obj = Capability(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_capability(
    db: Session, capability: Capability, data: CapabilityUpdate
) -> Capability:
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(capability, field, value)
    capability.updated_at = _utcnow()
    db.commit()
    db.refresh(capability)
    return capability


def delete_capability(db: Session, capability: Capability) -> None:
    db.delete(capability)
    db.commit()


# ---------------------------------------------------------------------------
# TrainingJob CRUD
# ---------------------------------------------------------------------------

def get_job(db: Session, job_id: int) -> Optional[TrainingJob]:
    return db.get(TrainingJob, job_id)


def list_jobs(
    db: Session, capability_id: Optional[int] = None
) -> list[TrainingJob]:
    q = db.query(TrainingJob)
    if capability_id is not None:
        q = q.filter(TrainingJob.capability_id == capability_id)
    return q.order_by(TrainingJob.id.desc()).all()


def create_job(db: Session, data: TrainingJobCreate) -> TrainingJob:
    obj = TrainingJob(
        capability_id=data.capability_id,
        version=data.version,
        status="pending",
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_job_status(
    db: Session,
    job: TrainingJob,
    status: str,
    *,
    celery_task_id: Optional[str] = None,
    error_msg: Optional[str] = None,
) -> TrainingJob:
    job.status = status
    if status == "running" and job.started_at is None:
        job.started_at = _utcnow()
    if status in ("done", "failed"):
        job.finished_at = _utcnow()
    if celery_task_id is not None:
        job.celery_task_id = celery_task_id
    if error_msg is not None:
        job.error_msg = error_msg
    db.commit()
    db.refresh(job)
    return job


def update_job_pid(db: Session, job: TrainingJob, pid: int) -> TrainingJob:
    job.pid = pid
    db.commit()
    db.refresh(job)
    return job


def update_job_log_path(db: Session, job: TrainingJob, log_path: str) -> TrainingJob:
    job.log_path = log_path
    db.commit()
    db.refresh(job)
    return job


# ---------------------------------------------------------------------------
# ModelVersion CRUD
# ---------------------------------------------------------------------------

def get_model_version(db: Session, version_id: int) -> Optional[ModelVersion]:
    return db.get(ModelVersion, version_id)


def list_model_versions(
    db: Session, capability_id: Optional[int] = None
) -> list[ModelVersion]:
    q = db.query(ModelVersion)
    if capability_id is not None:
        q = q.filter(ModelVersion.capability_id == capability_id)
    return q.order_by(ModelVersion.id.desc()).all()


def create_model_version(
    db: Session,
    capability_id: int,
    job_id: Optional[int],
    version: str,
    model_path: str,
    manifest_path: Optional[str] = None,
) -> ModelVersion:
    obj = ModelVersion(
        capability_id=capability_id,
        job_id=job_id,
        version=version,
        model_path=model_path,
        manifest_path=manifest_path,
        exported_at=_utcnow(),
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def set_current_version(db: Session, version: ModelVersion) -> ModelVersion:
    # Unset all others for the same capability
    db.query(ModelVersion).filter(
        ModelVersion.capability_id == version.capability_id,
        ModelVersion.id != version.id,
    ).update({"is_current": False})
    version.is_current = True
    db.commit()
    db.refresh(version)
    return version


# ---------------------------------------------------------------------------
# AnnotationProject CRUD
# ---------------------------------------------------------------------------

def get_annotation_project(db: Session, project_id: int) -> Optional[AnnotationProject]:
    return db.get(AnnotationProject, project_id)


def list_annotation_projects(
    db: Session, capability_id: Optional[int] = None
) -> list[AnnotationProject]:
    q = db.query(AnnotationProject)
    if capability_id is not None:
        q = q.filter(AnnotationProject.capability_id == capability_id)
    return q.order_by(AnnotationProject.id.desc()).all()


def create_annotation_project(db: Session, data: AnnotationProjectCreate) -> AnnotationProject:
    obj = AnnotationProject(**data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def update_annotation_project(
    db: Session, project: AnnotationProject, data: AnnotationProjectUpdate
) -> AnnotationProject:
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(project, field, value)
    project.updated_at = _utcnow()
    db.commit()
    db.refresh(project)
    return project


def delete_annotation_project(db: Session, project: AnnotationProject) -> None:
    db.delete(project)
    db.commit()


# ---------------------------------------------------------------------------
# AnnotationRecord CRUD
# ---------------------------------------------------------------------------

def get_annotation_record(db: Session, record_id: int) -> Optional[AnnotationRecord]:
    return db.get(AnnotationRecord, record_id)


def get_annotation_record_by_path(
    db: Session, project_id: int, file_path: str
) -> Optional[AnnotationRecord]:
    return (
        db.query(AnnotationRecord)
        .filter(
            AnnotationRecord.project_id == project_id,
            AnnotationRecord.file_path == file_path,
        )
        .first()
    )


def list_annotation_records(
    db: Session, project_id: int, offset: int = 0, limit: int = 50
) -> list[AnnotationRecord]:
    return (
        db.query(AnnotationRecord)
        .filter(AnnotationRecord.project_id == project_id)
        .order_by(AnnotationRecord.id)
        .offset(offset)
        .limit(limit)
        .all()
    )


def count_annotation_records(db: Session, project_id: int) -> int:
    return (
        db.query(AnnotationRecord)
        .filter(AnnotationRecord.project_id == project_id)
        .count()
    )


def create_or_update_annotation_record(
    db: Session, project_id: int, data: AnnotationRecordCreate
) -> AnnotationRecord:
    existing = get_annotation_record_by_path(db, project_id, data.file_path)
    if existing:
        existing.annotation_data = data.annotation_data
        existing.annotated_by = data.annotated_by
        existing.updated_at = _utcnow()
        db.commit()
        db.refresh(existing)
        return existing
    obj = AnnotationRecord(project_id=project_id, **data.model_dump())
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


def delete_annotation_record(db: Session, record: AnnotationRecord) -> None:
    db.delete(record)
    db.commit()
