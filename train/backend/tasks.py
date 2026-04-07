"""Celery application and async training tasks."""

import hashlib
import json
import logging
import os
import signal
import subprocess
import tempfile
import threading
from datetime import datetime, timezone

import redis as redis_lib
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
MODELS_ROOT = os.getenv("MODELS_ROOT", "/workspace/models")
TRAINING_TIMEOUT_SECONDS = int(os.getenv("TRAINING_TIMEOUT_SECONDS", "86400"))
logger = logging.getLogger("train")

celery_app = Celery("train_tasks", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.task_serializer = "json"
celery_app.conf.result_serializer = "json"
celery_app.conf.accept_content = ["json"]
celery_app.conf.broker_connection_retry_on_startup = True


def _cleanup_temp_config(path: str) -> None:
    temp_dir = os.path.realpath(tempfile.gettempdir())
    real_path = os.path.realpath(path)
    if real_path != temp_dir and not real_path.startswith(temp_dir + os.sep):
        return
    if os.path.basename(real_path).startswith("train_cfg_") and real_path.endswith(".json"):
        try:
            os.remove(real_path)
        except FileNotFoundError:
            pass


def _redis() -> redis_lib.Redis:
    return redis_lib.Redis.from_url(REDIS_URL)


def _publish(job_id: int, line: str) -> None:
    try:
        _redis().publish(f"train:log:{job_id}", line)
    except Exception:
        pass


def _update_job(job_id: int, status: str, error_msg: str = "") -> None:
    """Update job status directly in the database from within a Celery task."""
    from database import SessionLocal
    import crud

    db = SessionLocal()
    try:
        job = crud.get_job(db, job_id)
        if job:
            crud.update_job_status(db, job, status, error_msg=error_msg or None)
    finally:
        db.close()


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _generate_manifest(
    output_path: str, capability: str, version: str
) -> None:
    """Generate manifest.json and checksum.sha256 if they don't exist."""
    manifest_path = os.path.join(output_path, "manifest.json")
    if os.path.exists(manifest_path):
        return

    model_file = os.path.join(output_path, "model.onnx")
    checksum = _sha256_file(model_file) if os.path.exists(model_file) else ""

    manifest = {
        "capability": capability,
        "model_version": version,
        "backend": "onnxruntime",
        "input_size": [1, 3, 640, 640],
        "input_format": "NCHW",
        "threshold": 0.5,
        "build_env": {
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "trained_by": "agilestar/ai-train:1.0.0",
        },
        "checksum": {
            "model_file": f"sha256:{checksum}",
            "algorithm": "sha256",
        },
        "company": "agilestar.cn",
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    checksum_path = os.path.join(output_path, "checksum.sha256")
    if not os.path.exists(checksum_path) and checksum:
        with open(checksum_path, "w") as f:
            f.write(f"{checksum}  model.onnx\n")


@celery_app.task(bind=True)
def run_training(
    self,
    job_id: int,
    capability_name: str,
    script_path: str,
    config_path: str,
    dataset_path: str,
    output_path: str,
    version: str,
) -> dict:
    """Execute a training job as a subprocess and stream logs via Redis Pub/Sub."""
    from database import SessionLocal
    import crud

    os.makedirs(output_path, exist_ok=True)
    log_dir = "./data/logs"
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{job_id}.log")

    # Mark job as running and record log path
    db = SessionLocal()
    try:
        job = crud.get_job(db, job_id)
        if job:
            crud.update_job_status(db, job, "running", celery_task_id=self.request.id)
            crud.update_job_log_path(db, job, log_file)
    finally:
        db.close()

    cmd = [
        "python",
        script_path,
        "--config", config_path,
        "--dataset", dataset_path,
        "--output", output_path,
        "--version", version,
    ]

    _publish(job_id, f"[INFO] Starting training: {capability_name} v{version}\n")

    try:
        try:
            with open(log_file, "w", encoding="utf-8") as lf:
                timed_out = False
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                    start_new_session=True,
                )

                def _kill_on_timeout() -> None:
                    nonlocal timed_out
                    timed_out = True
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        logger.warning("Training job %s timeout handler could not find process group %s", job_id, proc.pid)

                timeout_timer = threading.Timer(TRAINING_TIMEOUT_SECONDS, _kill_on_timeout)
                timeout_timer.start()

                # Store PID so the API can send signals
                db = SessionLocal()
                try:
                    job = crud.get_job(db, job_id)
                    if job:
                        crud.update_job_pid(db, job, proc.pid)
                finally:
                    db.close()

                try:
                    if proc.stdout is not None:
                        for line in proc.stdout:
                            lf.write(line)
                            lf.flush()
                            _publish(job_id, line)
                    proc.wait()
                finally:
                    timeout_timer.cancel()

            if timed_out:
                raise TimeoutError(f"Training timed out after {TRAINING_TIMEOUT_SECONDS} seconds")
            if proc.returncode != 0:
                raise RuntimeError(f"Training process exited with code {proc.returncode}")

        except Exception as exc:
            _update_job(job_id, "failed", str(exc))
            _publish(job_id, f"[ERROR] {exc}\n")
            _publish(job_id, "__DONE__\n")
            return {"status": "failed", "error": str(exc)}

        # Auto export
        try:
            _auto_export(job_id, capability_name, os.path.dirname(script_path), output_path, version)
        except Exception as exc:
            _publish(job_id, f"[WARN] Export failed: {exc}\n")

        _update_job(job_id, "done")
        _publish(job_id, "[DONE] Training complete.\n")
        _publish(job_id, "__DONE__\n")

        # Register model version in DB
        db = SessionLocal()
        try:
            import crud as _crud
            job = _crud.get_job(db, job_id)
            if job:
                manifest_path = os.path.join(output_path, "manifest.json")
                _crud.create_model_version(
                    db,
                    capability_id=job.capability_id,
                    job_id=job_id,
                    version=version,
                    model_path=output_path,
                    manifest_path=manifest_path if os.path.exists(manifest_path) else None,
                )
        finally:
            db.close()

        return {"status": "done"}
    finally:
        _cleanup_temp_config(config_path)


def _auto_export(
    job_id: int,
    capability_name: str,
    script_dir: str,
    output_path: str,
    version: str,
) -> None:
    """Run export.py then generate manifest + checksum."""
    export_script = os.path.join(script_dir, "export.py")
    if os.path.exists(export_script):
        cmd = [
            "python", export_script,
            "--output", output_path,
            "--version", version,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        _publish(job_id, result.stdout or "")
        if result.returncode != 0:
            _publish(job_id, f"[WARN] export.py stderr: {result.stderr}\n")

    _generate_manifest(output_path, capability_name, version)
