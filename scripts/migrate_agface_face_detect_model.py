#!/usr/bin/env python3
"""Migrate ai_agface RetinaFace detection model into the ai_platform standard layout.

From (old ai_agface delivery):
    <src_root>/delivery_package/models/detection/detection.param
    <src_root>/delivery_package/models/detection/detection.bin
  或
    <src_root>/models/detection/detection.param
    <src_root>/models/detection/detection.bin

To (ai_platform standard model package):
    <dst_root>/agface_face_detect/1.0.0/
        ├── detection.param
        ├── detection.bin
        └── manifest.json

Usage (PowerShell / bash):
    python scripts/migrate_agface_face_detect_model.py \
        --src "H:/work/训练数据/caffe-base/ai_agface" \
        --dst "/data/ai_platform/models" \
        --version 1.0.0

After migration, also make sure the `current` symlink (or directory) points to
the version inside the prod container's mount:
    /mnt/ai_platform/models/agface_face_detect/current -> 1.0.0

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger("migrate_agface_face_detect")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

CAPABILITY_NAME = "agface_face_detect"
REQUIRED_FILES = ("detection.param", "detection.bin")


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_source_detection_dir(src_root: Path) -> Path:
    """Locate detection.param/bin inside either delivery_package/models or models/."""
    candidates = [
        src_root / "delivery_package" / "models" / "detection",
        src_root / "models" / "detection",
    ]
    for d in candidates:
        if all((d / f).exists() for f in REQUIRED_FILES):
            return d
    raise FileNotFoundError(
        f"Cannot find {REQUIRED_FILES} under any of: "
        + ", ".join(str(c) for c in candidates)
    )


def _build_manifest(
    version: str,
    param_name: str,
    bin_name: str,
    param_sha256: str,
    bin_sha256: str,
) -> dict:
    return {
        "name": CAPABILITY_NAME,
        "version": version,
        "backend": "ncnn",
        "description": (
            "agface 人脸检测（NCNN RetinaFace/SSD 头）。迁移自 ai_agface V5 "
            "detection.param/bin。与 ai_agface FaceDetectRetina 的推理流程等价。"
        ),
        "company": "agilestar.cn",
        "param_file": param_name,
        "bin_file": bin_name,
        "input": {
            "blob": "data",
            "base_size": 192,
            "color": "BGR",
            "mean": [104.0, 117.0, 123.0],
            "norm": [1.0, 1.0, 1.0],
        },
        "output": {
            "blob": "detection_out",
            "format": "ssd",
        },
        "thresholds": {
            "score": 0.5,
            "min_face": 40,
            "max_image_dim": 1200,
        },
        "checksum_sha256": {
            param_name: param_sha256,
            bin_name: bin_sha256,
        },
    }


def migrate(src_root: Path, dst_root: Path, version: str, overwrite: bool) -> Path:
    if not src_root.exists():
        raise FileNotFoundError(f"src_root not found: {src_root}")

    detection_dir = _resolve_source_detection_dir(src_root)
    logger.info("Source detection dir: %s", detection_dir)

    target_dir = dst_root / CAPABILITY_NAME / version
    if target_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"Target already exists: {target_dir} (use --overwrite to replace)"
            )
        logger.warning("Removing existing target: %s", target_dir)
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    # Copy model files
    for fname in REQUIRED_FILES:
        src = detection_dir / fname
        dst = target_dir / fname
        shutil.copy2(src, dst)
        logger.info("Copied %s → %s (%d bytes)", src.name, dst, dst.stat().st_size)

    param_sha = _sha256_of(target_dir / "detection.param")
    bin_sha = _sha256_of(target_dir / "detection.bin")

    manifest = _build_manifest(
        version=version,
        param_name="detection.param",
        bin_name="detection.bin",
        param_sha256=param_sha,
        bin_sha256=bin_sha,
    )
    manifest_path = target_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    logger.info("Wrote manifest: %s", manifest_path)

    logger.info("Migration complete → %s", target_dir)
    return target_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--src",
        required=True,
        type=Path,
        help="Old ai_agface project root (must contain delivery_package/ or models/)",
    )
    parser.add_argument(
        "--dst",
        required=True,
        type=Path,
        help="Target models root, e.g. /data/ai_platform/models",
    )
    parser.add_argument("--version", default="1.0.0", help="Model package version")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing target dir")
    args = parser.parse_args(argv)

    try:
        migrate(args.src.resolve(), args.dst.resolve(), args.version, args.overwrite)
    except Exception as e:
        logger.error("Migration failed: %s", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
