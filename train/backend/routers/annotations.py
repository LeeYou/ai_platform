"""Annotation management API router."""

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import crud
from database import get_db
from schemas import (
    AnnotationProjectCreate,
    AnnotationProjectOut,
    AnnotationProjectUpdate,
    AnnotationRecordCreate,
    AnnotationRecordOut,
)

logger = logging.getLogger("train")

router = APIRouter(prefix="/api/v1/annotations", tags=["annotations"])

DATASETS_ROOT = os.getenv("DATASETS_ROOT", "/workspace/datasets")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp", ".gif"}


def _safe_path(base: str, rel: str) -> str:
    """Resolve *rel* under *base* and ensure it doesn't escape *base*."""
    resolved = os.path.realpath(os.path.join(base, rel))
    base_resolved = os.path.realpath(base)
    if not resolved.startswith(base_resolved + os.sep) and resolved != base_resolved:
        raise HTTPException(status_code=400, detail="非法路径")
    return resolved


# ---------------------------------------------------------------------------
# Project endpoints
# ---------------------------------------------------------------------------

@router.get("/projects", response_model=list[AnnotationProjectOut])
def list_projects(
    capability_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    return crud.list_annotation_projects(db, capability_id=capability_id)


@router.post("/projects", response_model=AnnotationProjectOut, status_code=201)
def create_project(data: AnnotationProjectCreate, db: Session = Depends(get_db)):
    cap = crud.get_capability(db, data.capability_id)
    if not cap:
        raise HTTPException(status_code=404, detail="关联的AI能力不存在")
    project = crud.create_annotation_project(db, data)
    _refresh_sample_count(db, project)
    return project


@router.get("/projects/{project_id}", response_model=AnnotationProjectOut)
def get_project(project_id: int, db: Session = Depends(get_db)):
    project = crud.get_annotation_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="标注项目不存在")
    return project


@router.put("/projects/{project_id}", response_model=AnnotationProjectOut)
def update_project(
    project_id: int, data: AnnotationProjectUpdate, db: Session = Depends(get_db)
):
    project = crud.get_annotation_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="标注项目不存在")
    return crud.update_annotation_project(db, project, data)


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int, db: Session = Depends(get_db)):
    project = crud.get_annotation_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="标注项目不存在")
    crud.delete_annotation_project(db, project)


@router.get("/projects/{project_id}/stats")
def project_stats(project_id: int, db: Session = Depends(get_db)):
    project = crud.get_annotation_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="标注项目不存在")
    _refresh_sample_count(db, project)
    annotated = crud.count_annotation_records(db, project_id)
    return {
        "project_id": project_id,
        "total_samples": project.total_samples,
        "annotated_samples": annotated,
        "progress": round(annotated / project.total_samples * 100, 1) if project.total_samples > 0 else 0,
        "annotation_type": project.annotation_type,
        "network_type": project.network_type,
    }


# ---------------------------------------------------------------------------
# Sample listing
# ---------------------------------------------------------------------------

@router.get("/projects/{project_id}/samples")
def list_samples(
    project_id: int,
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    filter_status: Optional[str] = Query(None, alias="status"),
    db: Session = Depends(get_db),
):
    """List samples in the dataset directory with their annotation status."""
    project = crud.get_annotation_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="标注项目不存在")

    ds_path = project.dataset_path or os.path.join(DATASETS_ROOT, "default")
    if not os.path.isdir(ds_path):
        return {"total": 0, "samples": []}

    # Collect all image files
    all_files: list[str] = []
    for root, _dirs, files in os.walk(ds_path):
        for f in sorted(files):
            ext = os.path.splitext(f)[1].lower()
            if ext in IMAGE_EXTENSIONS:
                rel = os.path.relpath(os.path.join(root, f), ds_path)
                all_files.append(rel)
    all_files.sort()

    # Build annotation lookup
    records = crud.list_annotation_records(db, project_id, offset=0, limit=999999)
    annotated_set = {r.file_path for r in records}
    annotation_map = {r.file_path: r for r in records}

    # Filter if requested
    if filter_status == "annotated":
        all_files = [f for f in all_files if f in annotated_set]
    elif filter_status == "unannotated":
        all_files = [f for f in all_files if f not in annotated_set]

    total = len(all_files)
    page_files = all_files[offset: offset + limit]

    samples = []
    for fp in page_files:
        rec = annotation_map.get(fp)
        entry: dict = {
            "file_path": fp,
            "annotated": fp in annotated_set,
        }
        if rec:
            entry["record_id"] = rec.id
            try:
                entry["annotation_data"] = json.loads(rec.annotation_data) if isinstance(rec.annotation_data, str) else rec.annotation_data
            except json.JSONDecodeError:
                entry["annotation_data"] = {}
            entry["annotated_by"] = rec.annotated_by
        samples.append(entry)

    return {"total": total, "offset": offset, "limit": limit, "samples": samples}


# ---------------------------------------------------------------------------
# Annotation record endpoints
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/annotate", response_model=AnnotationRecordOut)
def save_annotation(
    project_id: int, data: AnnotationRecordCreate, db: Session = Depends(get_db)
):
    project = crud.get_annotation_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="标注项目不存在")
    record = crud.create_or_update_annotation_record(db, project_id, data)
    # update annotated count
    project.annotated_samples = crud.count_annotation_records(db, project_id)
    db.commit()
    return record


@router.get("/projects/{project_id}/samples/{record_id}", response_model=AnnotationRecordOut)
def get_annotation_record(
    project_id: int, record_id: int, db: Session = Depends(get_db)
):
    record = crud.get_annotation_record(db, record_id)
    if not record or record.project_id != project_id:
        raise HTTPException(status_code=404, detail="标注记录不存在")
    return record


@router.delete("/projects/{project_id}/samples/{record_id}", status_code=204)
def delete_annotation_record(
    project_id: int, record_id: int, db: Session = Depends(get_db)
):
    record = crud.get_annotation_record(db, record_id)
    if not record or record.project_id != project_id:
        raise HTTPException(status_code=404, detail="标注记录不存在")
    crud.delete_annotation_record(db, record)
    # update count
    project = crud.get_annotation_project(db, project_id)
    if project:
        project.annotated_samples = crud.count_annotation_records(db, project_id)
        db.commit()


# ---------------------------------------------------------------------------
# Image serving (with path security)
# ---------------------------------------------------------------------------

@router.get("/image")
def serve_image(path: str = Query(..., description="图片相对路径"), base: str = Query(DATASETS_ROOT)):
    """Serve an image file from the datasets directory."""
    safe = _safe_path(base, path)
    if not os.path.isfile(safe):
        raise HTTPException(status_code=404, detail="文件不存在")
    ext = os.path.splitext(safe)[1].lower()
    if ext not in IMAGE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="不支持的文件类型")
    media_types = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".bmp": "image/bmp", ".gif": "image/gif", ".webp": "image/webp",
        ".tiff": "image/tiff", ".tif": "image/tiff",
    }
    return FileResponse(safe, media_type=media_types.get(ext, "application/octet-stream"))


# ---------------------------------------------------------------------------
# Export annotations
# ---------------------------------------------------------------------------

@router.post("/projects/{project_id}/export")
def export_annotations(project_id: int, db: Session = Depends(get_db)):
    """Export annotations to training-compatible format in the dataset directory."""
    project = crud.get_annotation_project(db, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="标注项目不存在")

    records = crud.list_annotation_records(db, project_id, offset=0, limit=999999)
    if not records:
        raise HTTPException(status_code=400, detail="暂无标注数据可导出")

    ds_path = project.dataset_path or os.path.join(DATASETS_ROOT, "default")
    export_dir = os.path.join(ds_path, "annotations_export")
    os.makedirs(export_dir, exist_ok=True)

    at = project.annotation_type

    if at in ("binary_classification", "multi_classification"):
        return _export_classification(project, records, ds_path, export_dir)
    elif at == "object_detection":
        return _export_object_detection(project, records, ds_path, export_dir)
    elif at == "ocr":
        return _export_ocr(project, records, ds_path, export_dir)
    else:
        # generic JSON export
        return _export_generic(project, records, export_dir)


def _export_classification(project, records, ds_path, export_dir):
    """Export classification annotations: symlink/copy images into class folders."""
    try:
        label_cfg = json.loads(project.label_config) if isinstance(project.label_config, str) else project.label_config
    except json.JSONDecodeError:
        label_cfg = {"labels": []}

    labels_map = {l["id"]: l["name"] for l in label_cfg.get("labels", [])}

    # Create class folders
    for label_name in labels_map.values():
        os.makedirs(os.path.join(export_dir, label_name), exist_ok=True)

    exported = 0
    for rec in records:
        try:
            ann = json.loads(rec.annotation_data) if isinstance(rec.annotation_data, str) else rec.annotation_data
        except json.JSONDecodeError:
            continue
        label_id = ann.get("label")
        if label_id is None:
            continue
        label_name = labels_map.get(label_id, str(label_id))
        src = os.path.join(ds_path, rec.file_path)
        dst_dir = os.path.join(export_dir, label_name)
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, os.path.basename(rec.file_path))
        if os.path.isfile(src) and not os.path.exists(dst):
            try:
                os.symlink(src, dst)
            except OSError:
                shutil.copy2(src, dst)
            exported += 1

    # Write labels.json
    with open(os.path.join(export_dir, "labels.json"), "w", encoding="utf-8") as f:
        json.dump(label_cfg, f, ensure_ascii=False, indent=2)

    return {"message": f"导出完成，共 {exported} 个样本", "export_dir": export_dir}


def _export_object_detection(project, records, ds_path, export_dir):
    """Export object detection annotations in YOLO format."""
    try:
        label_cfg = json.loads(project.label_config) if isinstance(project.label_config, str) else project.label_config
    except json.JSONDecodeError:
        label_cfg = {"labels": []}

    labels_list = label_cfg.get("labels", [])
    label_id_map = {l["name"]: l["id"] for l in labels_list}

    images_dir = os.path.join(export_dir, "images")
    labels_dir = os.path.join(export_dir, "labels")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(labels_dir, exist_ok=True)

    exported = 0
    for rec in records:
        try:
            ann = json.loads(rec.annotation_data) if isinstance(rec.annotation_data, str) else rec.annotation_data
        except json.JSONDecodeError:
            continue
        boxes = ann.get("boxes", [])
        if not boxes:
            continue

        src = os.path.join(ds_path, rec.file_path)
        if not os.path.isfile(src):
            continue

        fname = os.path.basename(rec.file_path)
        dst_img = os.path.join(images_dir, fname)
        if not os.path.exists(dst_img):
            try:
                os.symlink(src, dst_img)
            except OSError:
                shutil.copy2(src, dst_img)

        # Write YOLO label file
        txt_name = os.path.splitext(fname)[0] + ".txt"
        with open(os.path.join(labels_dir, txt_name), "w") as f:
            for box in boxes:
                cls_id = label_id_map.get(box.get("label", ""), box.get("class_id", 0))
                # YOLO format: class_id cx cy w h (normalized)
                cx = box.get("cx", box.get("x", 0))
                cy = box.get("cy", box.get("y", 0))
                bw = box.get("w", 0)
                bh = box.get("h", 0)
                f.write(f"{cls_id} {cx} {cy} {bw} {bh}\n")
        exported += 1

    # Write data.yaml manually (avoid PyYAML dependency)
    with open(os.path.join(export_dir, "data.yaml"), "w", encoding="utf-8") as f:
        f.write(f"path: {export_dir}\n")
        f.write("train: images\n")
        f.write("val: images\n")
        f.write("names:\n")
        for l in labels_list:
            f.write(f"  {l['id']}: {l['name']}\n")

    return {"message": f"导出完成（YOLO格式），共 {exported} 个样本", "export_dir": export_dir}


def _export_ocr(project, records, ds_path, export_dir):
    """Export OCR annotations."""
    images_dir = os.path.join(export_dir, "images")
    labels_dir = os.path.join(export_dir, "labels")
    os.makedirs(images_dir, exist_ok=True)
    os.makedirs(labels_dir, exist_ok=True)

    exported = 0
    for rec in records:
        try:
            ann = json.loads(rec.annotation_data) if isinstance(rec.annotation_data, str) else rec.annotation_data
        except json.JSONDecodeError:
            continue
        regions = ann.get("regions", [])
        if not regions:
            continue

        src = os.path.join(ds_path, rec.file_path)
        if not os.path.isfile(src):
            continue

        fname = os.path.basename(rec.file_path)
        dst_img = os.path.join(images_dir, fname)
        if not os.path.exists(dst_img):
            try:
                os.symlink(src, dst_img)
            except OSError:
                shutil.copy2(src, dst_img)

        txt_name = os.path.splitext(fname)[0] + ".txt"
        with open(os.path.join(labels_dir, txt_name), "w", encoding="utf-8") as f:
            for region in regions:
                pts = region.get("points", [])
                text = region.get("text", "")
                coords = ",".join(f"{p[0]},{p[1]}" for p in pts)
                f.write(f"{coords},{text}\n")
        exported += 1

    return {"message": f"导出完成（OCR格式），共 {exported} 个样本", "export_dir": export_dir}


def _export_generic(project, records, export_dir):
    """Generic JSON export for any annotation type."""
    output = []
    for rec in records:
        try:
            ann = json.loads(rec.annotation_data) if isinstance(rec.annotation_data, str) else rec.annotation_data
        except json.JSONDecodeError:
            ann = {}
        output.append({
            "file_path": rec.file_path,
            "annotation": ann,
            "annotated_by": rec.annotated_by,
        })

    out_path = os.path.join(export_dir, "annotations.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return {"message": f"导出完成（JSON格式），共 {len(output)} 条标注", "export_dir": export_dir}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _refresh_sample_count(db: Session, project):
    """Scan the dataset directory and update total_samples."""
    ds_path = project.dataset_path or os.path.join(DATASETS_ROOT, "default")
    count = 0
    if os.path.isdir(ds_path):
        for _root, _dirs, files in os.walk(ds_path):
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in IMAGE_EXTENSIONS:
                    count += 1
    project.total_samples = count
    project.annotated_samples = crud.count_annotation_records(db, project.id)
    db.commit()
    db.refresh(project)
