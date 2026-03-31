"""Pydantic v2 schemas for the training management backend."""

import json
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator


# ---------------------------------------------------------------------------
# Capability schemas
# ---------------------------------------------------------------------------

class CapabilityCreate(BaseModel):
    name: str
    name_cn: str = ""
    description: str = ""
    dataset_path: str = ""
    script_path: str = ""
    hyperparams: str = "{}"

    @field_validator("hyperparams")
    @classmethod
    def validate_json(cls, v: str) -> str:
        try:
            json.loads(v)
        except json.JSONDecodeError as exc:
            raise ValueError(f"hyperparams must be valid JSON: {exc}") from exc
        return v


class CapabilityUpdate(BaseModel):
    name_cn: Optional[str] = None
    description: Optional[str] = None
    dataset_path: Optional[str] = None
    script_path: Optional[str] = None
    hyperparams: Optional[str] = None

    @field_validator("hyperparams")
    @classmethod
    def validate_json(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                json.loads(v)
            except json.JSONDecodeError as exc:
                raise ValueError(f"hyperparams must be valid JSON: {exc}") from exc
        return v


class CapabilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    name_cn: str
    description: str
    dataset_path: str
    script_path: str
    hyperparams: Any
    created_at: datetime
    updated_at: datetime

    @field_validator("hyperparams", mode="before")
    @classmethod
    def parse_hyperparams(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v


# ---------------------------------------------------------------------------
# TrainingJob schemas
# ---------------------------------------------------------------------------

class TrainingJobCreate(BaseModel):
    capability_id: int
    version: str
    hyperparams: Optional[str] = None  # Optional job-specific overrides

    @field_validator("hyperparams")
    @classmethod
    def validate_json(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                json.loads(v)
            except json.JSONDecodeError as exc:
                raise ValueError(f"hyperparams must be valid JSON: {exc}") from exc
        return v


class TrainingJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    capability_id: int
    version: str
    status: str
    hyperparams: Any
    celery_task_id: Optional[str]
    pid: Optional[int]
    log_path: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error_msg: Optional[str]
    created_at: datetime

    @field_validator("hyperparams", mode="before")
    @classmethod
    def parse_hyperparams(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v


# ---------------------------------------------------------------------------
# ModelVersion schemas
# ---------------------------------------------------------------------------

class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    capability_id: int
    job_id: Optional[int]
    version: str
    model_path: str
    manifest_path: Optional[str]
    is_current: bool
    exported_at: Optional[datetime]
    created_at: datetime


# ---------------------------------------------------------------------------
# AnnotationProject schemas
# ---------------------------------------------------------------------------

ANNOTATION_TYPES = {"binary_classification", "multi_classification", "object_detection", "ocr", "segmentation"}


class AnnotationProjectCreate(BaseModel):
    name: str
    capability_id: int
    annotation_type: str
    network_type: str = ""
    dataset_path: str = ""
    label_config: str = "{}"

    @field_validator("annotation_type")
    @classmethod
    def validate_annotation_type(cls, v: str) -> str:
        if v not in ANNOTATION_TYPES:
            raise ValueError(f"annotation_type must be one of {ANNOTATION_TYPES}")
        return v

    @field_validator("label_config")
    @classmethod
    def validate_label_json(cls, v: str) -> str:
        try:
            json.loads(v)
        except json.JSONDecodeError as exc:
            raise ValueError(f"label_config must be valid JSON: {exc}") from exc
        return v


class AnnotationProjectUpdate(BaseModel):
    name: Optional[str] = None
    network_type: Optional[str] = None
    dataset_path: Optional[str] = None
    label_config: Optional[str] = None
    status: Optional[str] = None

    @field_validator("label_config")
    @classmethod
    def validate_label_json(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                json.loads(v)
            except json.JSONDecodeError as exc:
                raise ValueError(f"label_config must be valid JSON: {exc}") from exc
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ("in_progress", "completed", "archived"):
            raise ValueError("status must be one of: in_progress, completed, archived")
        return v


class AnnotationProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    capability_id: int
    annotation_type: str
    network_type: str
    dataset_path: str
    label_config: Any
    status: str
    total_samples: int
    annotated_samples: int
    created_at: datetime
    updated_at: datetime

    @field_validator("label_config", mode="before")
    @classmethod
    def parse_label_config(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v


# ---------------------------------------------------------------------------
# AnnotationRecord schemas
# ---------------------------------------------------------------------------

class AnnotationRecordCreate(BaseModel):
    file_path: str
    annotation_data: str = "{}"
    annotated_by: str = "default"

    @field_validator("annotation_data")
    @classmethod
    def validate_annotation_json(cls, v: str) -> str:
        try:
            json.loads(v)
        except json.JSONDecodeError as exc:
            raise ValueError(f"annotation_data must be valid JSON: {exc}") from exc
        return v


class AnnotationRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    file_path: str
    annotation_data: Any
    annotated_by: str
    created_at: datetime
    updated_at: datetime

    @field_validator("annotation_data", mode="before")
    @classmethod
    def parse_annotation_data(cls, v: Any) -> Any:
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v
