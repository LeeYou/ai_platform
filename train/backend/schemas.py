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


class TrainingJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    capability_id: int
    version: str
    status: str
    celery_task_id: Optional[str]
    pid: Optional[int]
    log_path: Optional[str]
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    error_msg: Optional[str]
    created_at: datetime


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
