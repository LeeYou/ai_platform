#!/usr/bin/env python3
"""Migrate ai_agface legacy vision-analysis NCNN models into ai_platform layout.

Supported capabilities:
  - agface_barehead
  - agface_fake_photo
  - agface_face_property

It copies the required detection submodels into each capability version directory and
writes a minimal manifest.json so the ai_platform resource scanner can discover them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("migrate_agface_vision_models")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass(frozen=True)
class CapabilitySpec:
    capability: str
    required_files: tuple[str, ...]
    description: str


SPECS: dict[str, CapabilitySpec] = {
    "barehead": CapabilitySpec(
        capability="agface_barehead",
        required_files=(
            "detection/detection.param",
            "detection/detection.bin",
            "detection/det3.param",
            "detection/det3.bin",
            "detection/modelht.param",
            "detection/modelht.bin",
        ),
        description="agface 裸头检测（NCNN legacy barehead），迁移自 ai_agface barehead_module。",
    ),
    "fake_photo": CapabilitySpec(
        capability="agface_fake_photo",
        required_files=(
            "detection/detection.param",
            "detection/detection.bin",
            "detection/det3.param",
            "detection/det3.bin",
            "detection/model_1.param",
            "detection/model_1.bin",
            "detection/model_2.param",
            "detection/model_2.bin",
            "detection/model_3.param",
            "detection/model_3.bin",
            "detection/yolov7s320face.param",
            "detection/yolov7s320face.bin",
        ),
        description="agface 翻拍照检测（NCNN legacy fake_photo），迁移自 ai_agface fake_photo_module。",
    ),
    "face_property": CapabilitySpec(
        capability="agface_face_property",
        required_files=(
            "detection/detection.param",
            "detection/detection.bin",
            "detection/det3.param",
            "detection/det3.bin",
            "detection/model_1.param",
            "detection/model_1.bin",
            "detection/model_2.param",
            "detection/model_2.bin",
            "detection/model_3.param",
            "detection/model_3.bin",
            "detection/modelht.param",
            "detection/modelht.bin",
            "detection/yolov7s320face.param",
            "detection/yolov7s320face.bin",
            "detection/face_landmark_with_attention.param",
            "detection/face_landmark_with_attention.bin",
        ),
        description="agface 人脸属性检测（NCNN legacy face_property），迁移自 ai_agface face_property_module。",
    ),
}


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_models_root(src_root: Path) -> Path:
    candidates = [
        src_root / "delivery_package" / "models",
        src_root / "models",
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise FileNotFoundError("cannot find delivery_package/models or models under src root")


def _build_manifest(spec: CapabilitySpec, version: str, checksum_map: dict[str, str]) -> dict:
    return {
        "name": spec.capability,
        "version": version,
        "backend": "ncnn",
        "description": spec.description,
        "company": "agilestar.cn",
        "param_file": "detection/detection.param",
        "bin_file": "detection/detection.bin",
        "input": {
            "blob": "data",
            "base_size": 192,
            "color": "BGR",
            "mean": [104.0, 117.0, 123.0],
            "norm": [1.0, 1.0, 1.0],
        },
        "output": {
            "blob": "legacy_vision_bundle",
            "format": "legacy_vision_bundle",
        },
        "entry": {
            "kind": "legacy_vision_bundle",
            "detector": "detection/detection.param",
        },
        "checksum_sha256": checksum_map,
    }


def migrate_one(spec: CapabilitySpec, src_root: Path, dst_root: Path, version: str, overwrite: bool) -> Path:
    models_root = _resolve_models_root(src_root)
    target_dir = dst_root / spec.capability / version
    if target_dir.exists():
        if not overwrite:
            raise FileExistsError(f"target exists: {target_dir} (use --overwrite to replace)")
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    checksum_map: dict[str, str] = {}
    for rel in spec.required_files:
        src = models_root / rel
        if not src.exists():
            raise FileNotFoundError(f"missing required file: {src}")
        dst = target_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        checksum_map[rel] = _sha256_of(dst)
        logger.info("Copied %s -> %s", src, dst)

    manifest = _build_manifest(spec, version, checksum_map)
    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Wrote manifest: %s", manifest_path)
    return target_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", required=True, type=Path, help="Old ai_agface project root")
    parser.add_argument("--dst", required=True, type=Path, help="Target ai_platform models root")
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--which", choices=("all",) + tuple(SPECS.keys()), default="all")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    src_root = args.src.resolve()
    dst_root = args.dst.resolve()
    specs = list(SPECS.values()) if args.which == "all" else [SPECS[args.which]]

    failed = 0
    for spec in specs:
        try:
            migrate_one(spec, src_root, dst_root, args.version, args.overwrite)
            logger.info("Migrated %s OK", spec.capability)
        except Exception as exc:
            failed += 1
            logger.error("Failed %s: %s", spec.capability, exc)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
