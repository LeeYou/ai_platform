#!/usr/bin/env python3
"""Migrate ai_agface face-feature NCNN models into the ai_platform layout.

Supports two feature extractors from old ai_agface:
  - residual256  (residual/residual.param|bin, 256-dim)
  - glint512     (glint360k_r34/glint360k_r34.opt.param|bin, 512-dim)

From (old ai_agface delivery):
  <src_root>/delivery_package/models/residual/residual.{param,bin}
  <src_root>/delivery_package/models/glint360k_r34/glint360k_r34.opt.{param,bin}
or the equivalent non-delivery `models/...` tree.

To (ai_platform standard model packages):
  <dst_root>/agface_face_feature_residual256/1.0.0/{model.param,model.bin,manifest.json}
  <dst_root>/agface_face_feature_glint512/1.0.0/{model.param,model.bin,manifest.json}

Usage:
    python scripts/migrate_agface_face_feature_models.py \
        --src "H:/work/训练数据/caffe-base/ai_agface" \
        --dst "/data/ai_platform/models" \
        --version 1.0.0 \
        --which all        # or: residual256 / glint512

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
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

logger = logging.getLogger("migrate_agface_face_feature")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


@dataclass(frozen=True)
class FeatureModelSpec:
    capability: str
    feature_dim: int
    subdir: str                 # relative to <src_root>/(delivery_package/)models/
    param_name: str             # filename inside subdir
    bin_name: str
    description: str
    output_blob: str = "pre_fc1"


SPECS: dict[str, FeatureModelSpec] = {
    "residual256": FeatureModelSpec(
        capability="agface_face_feature_residual256",
        feature_dim=256,
        subdir="residual",
        param_name="residual.param",
        bin_name="residual.bin",
        description=(
            "agface 人脸特征 (NCNN Residual 256-dim)。迁移自 ai_agface V5 "
            "residual/residual.{param,bin}。"
        ),
    ),
    "glint512": FeatureModelSpec(
        capability="agface_face_feature_glint512",
        feature_dim=512,
        subdir="glint360k_r34",
        param_name="glint360k_r34.opt.param",
        bin_name="glint360k_r34.opt.bin",
        description=(
            "agface 人脸特征 (NCNN Glint360K-R34 512-dim)。迁移自 ai_agface V5 "
            "glint360k_r34/glint360k_r34.opt.{param,bin}。"
        ),
    ),
    "mobilenet256": FeatureModelSpec(
        capability="agface_face_feature_mobilenet256",
        feature_dim=256,
        subdir="mobilefacenet_fc_256",
        param_name="mobilefacenet_fc_256.param",
        bin_name="mobilefacenet_fc_256.bin",
        output_blob="fc1",
        description=(
            "agface 人脸特征 (NCNN MobileFaceNet 256-dim, output=fc1)。迁移自 "
            "ai_agface V5 mobilefacenet_fc_256/mobilefacenet_fc_256.{param,bin}。"
        ),
    ),
}


def _sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve_source_dir(src_root: Path, subdir: str) -> Path:
    candidates = [
        src_root / "delivery_package" / "models" / subdir,
        src_root / "models" / subdir,
    ]
    for d in candidates:
        if d.is_dir():
            return d
    raise FileNotFoundError(
        f"Cannot find subdir '{subdir}' under any of: "
        + ", ".join(str(c) for c in candidates)
    )


def _build_manifest(spec: FeatureModelSpec, version: str,
                    param_sha: str, bin_sha: str) -> dict:
    return {
        "name": spec.capability,
        "version": version,
        "backend": "ncnn",
        "description": spec.description,
        "company": "agilestar.cn",
        "param_file": "model.param",
        "bin_file": "model.bin",
        "feature_dim": spec.feature_dim,
        "input": {
            "blob": "data",
            "base_size": 112,
            "color": "RGB",
            "mean": [127.5, 127.5, 127.5],
            "norm": [1.0 / 128.0, 1.0 / 128.0, 1.0 / 128.0],
        },
        "output": {
            "blob": spec.output_blob,
            "format": "embedding",
        },
        "checksum_sha256": {
            "model.param": param_sha,
            "model.bin": bin_sha,
        },
    }


def migrate_one(spec: FeatureModelSpec, src_root: Path, dst_root: Path,
                version: str, overwrite: bool) -> Path:
    src_dir = _resolve_source_dir(src_root, spec.subdir)
    src_param = src_dir / spec.param_name
    src_bin = src_dir / spec.bin_name
    if not src_param.exists() or not src_bin.exists():
        raise FileNotFoundError(
            f"Missing {spec.param_name} or {spec.bin_name} in {src_dir}"
        )

    target_dir = dst_root / spec.capability / version
    if target_dir.exists():
        if not overwrite:
            raise FileExistsError(
                f"Target exists: {target_dir} (use --overwrite to replace)"
            )
        logger.warning("Removing existing target: %s", target_dir)
        shutil.rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy2(src_param, target_dir / "model.param")
    shutil.copy2(src_bin, target_dir / "model.bin")
    logger.info("Copied %s → %s", src_param.name, target_dir / "model.param")
    logger.info("Copied %s → %s", src_bin.name, target_dir / "model.bin")

    param_sha = _sha256_of(target_dir / "model.param")
    bin_sha = _sha256_of(target_dir / "model.bin")

    manifest = _build_manifest(spec, version, param_sha, bin_sha)
    manifest_path = target_dir / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    logger.info("Wrote manifest: %s", manifest_path)
    return target_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--src", required=True, type=Path,
                        help="Old ai_agface project root")
    parser.add_argument("--dst", required=True, type=Path,
                        help="Target models root, e.g. /data/ai_platform/models")
    parser.add_argument("--version", default="1.0.0")
    parser.add_argument("--which", choices=("all",) + tuple(SPECS.keys()), default="all")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)

    targets = list(SPECS.values()) if args.which == "all" else [SPECS[args.which]]
    src_root = args.src.resolve()
    dst_root = args.dst.resolve()
    if not src_root.exists():
        logger.error("src_root not found: %s", src_root)
        return 1

    fail = 0
    for spec in targets:
        try:
            migrate_one(spec, src_root, dst_root, args.version, args.overwrite)
            logger.info("Migrated %s OK", spec.capability)
        except Exception as e:
            fail += 1
            logger.error("Failed %s: %s", spec.capability, e)
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
