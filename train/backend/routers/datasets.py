"""Datasets router — filesystem-based dataset discovery."""

import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/datasets", tags=["datasets"])

DATASETS_ROOT = os.getenv("DATASETS_ROOT", "/workspace/datasets")


class DatasetInfo(BaseModel):
    name: str
    path: str
    file_count: int
    total_size_bytes: int
    last_modified: Optional[datetime]


def _scan_dataset(name: str, path: str) -> DatasetInfo:
    file_count = 0
    total_size = 0
    last_mtime: Optional[float] = None

    for dirpath, _dirs, files in os.walk(path):
        for fname in files:
            fp = os.path.join(dirpath, fname)
            try:
                st = os.stat(fp)
                file_count += 1
                total_size += st.st_size
                if last_mtime is None or st.st_mtime > last_mtime:
                    last_mtime = st.st_mtime
            except OSError:
                pass

    last_modified = (
        datetime.fromtimestamp(last_mtime, tz=timezone.utc) if last_mtime else None
    )
    return DatasetInfo(
        name=name,
        path=path,
        file_count=file_count,
        total_size_bytes=total_size,
        last_modified=last_modified,
    )


@router.get("/", response_model=list[DatasetInfo])
def list_datasets():
    if not os.path.isdir(DATASETS_ROOT):
        return []
    results = []
    for entry in sorted(os.scandir(DATASETS_ROOT), key=lambda e: e.name):
        if entry.is_dir():
            results.append(_scan_dataset(entry.name, entry.path))
    return results


@router.get("/{name}", response_model=DatasetInfo)
def get_dataset(name: str):
    path = os.path.join(DATASETS_ROOT, name)
    if not os.path.isdir(path):
        raise HTTPException(status_code=404, detail=f"Dataset '{name}' not found")
    return _scan_dataset(name, path)
