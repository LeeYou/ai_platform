"""Jobs router — training job lifecycle management."""

import os
import signal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

import crud
from database import get_db
from schemas import TrainingJobCreate, TrainingJobOut
from tasks import run_training

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

MODELS_ROOT = os.getenv("MODELS_ROOT", "/workspace/models")


@router.get("/", response_model=list[TrainingJobOut])
def list_jobs(
    capability_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    return crud.list_jobs(db, capability_id=capability_id)


@router.post("/", response_model=TrainingJobOut, status_code=status.HTTP_201_CREATED)
def create_job(data: TrainingJobCreate, db: Session = Depends(get_db)):
    cap = crud.get_capability(db, data.capability_id)
    if not cap:
        raise HTTPException(status_code=404, detail="Capability not found")

    job = crud.create_job(db, data)

    output_path = os.path.join(MODELS_ROOT, cap.name, data.version)

    # Merge capability-level hyperparams with job-specific overrides
    import json, tempfile
    try:
        cap_hp = json.loads(cap.hyperparams)
    except Exception:
        cap_hp = {}

    # Job-specific hyperparams override capability defaults
    if job.hyperparams:
        try:
            job_hp = json.loads(job.hyperparams)
            cap_hp.update(job_hp)
        except Exception:
            pass

    # Write merged hyperparams to temp config file
    tmp_cfg = os.path.join(tempfile.gettempdir(), f"train_cfg_{job.id}.json")
    with open(tmp_cfg, "w") as f:
        json.dump(cap_hp, f)

    task = run_training.delay(
        job_id=job.id,
        capability_name=cap.name,
        script_path=cap.script_path or f"/app/train/scripts/{cap.name}/train.py",
        config_path=tmp_cfg,
        dataset_path=cap.dataset_path or f"/workspace/datasets/{cap.name}",
        output_path=output_path,
        version=data.version,
    )
    crud.update_job_status(db, job, "pending", celery_task_id=task.id)
    db.refresh(job)
    return job


@router.get("/{job_id}", response_model=TrainingJobOut)
def get_job(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/{job_id}/stop", response_model=TrainingJobOut)
def stop_job(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.pid and job.status in ("running", "paused"):
        try:
            os.kill(job.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    return crud.update_job_status(db, job, "failed", error_msg="Stopped by user")


@router.post("/{job_id}/pause", response_model=TrainingJobOut)
def pause_job(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.pid and job.status == "running":
        try:
            os.kill(job.pid, signal.SIGSTOP)
        except ProcessLookupError:
            pass
    return crud.update_job_status(db, job, "paused")


@router.post("/{job_id}/resume", response_model=TrainingJobOut)
def resume_job(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.pid and job.status == "paused":
        try:
            os.kill(job.pid, signal.SIGCONT)
        except ProcessLookupError:
            pass
    return crud.update_job_status(db, job, "running")


@router.get("/{job_id}/logs", response_class=PlainTextResponse)
def get_job_logs(job_id: int, db: Session = Depends(get_db)):
    job = crud.get_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    log_path = job.log_path
    if not log_path or not os.path.exists(log_path):
        return PlainTextResponse("(no logs yet)")
    with open(log_path, encoding="utf-8", errors="replace") as f:
        return PlainTextResponse(f.read())
