"""Export face_detect model checkpoint to ONNX format using Ultralytics YOLOv8.

Usage:
    python export.py --output /workspace/models/face_detect/v1.0.0/ \\
                     --version 1.0.0

    python export.py --output /workspace/models/face_detect/v2.0.0/ \\
                     --version 2.0.0 \\
                     --checkpoint /workspace/runs/face_detect/best.pt
"""

import argparse
import json
import os
import shutil
import sys

_IMG_SIZE = 640
_LABELS = ["face", "occluded_face"]
_NUM_CLASSES = len(_LABELS)

# YOLOv8 uses /255 scaling, NOT ImageNet normalization
_SCALE = 1.0 / 255.0


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Export face_detect YOLOv8 model to ONNX",
    )
    parser.add_argument(
        "--output",
        default="/workspace/models/face_detect/v1.0.0/",
        help="Model output directory",
    )
    parser.add_argument("--version", default="1.0.0", help="Model version string")
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="Path to checkpoint file (defaults to best.pt, then last.pt in --output)",
    )
    return parser.parse_args()


def _resolve_checkpoint(checkpoint: str | None, output_dir: str) -> str:
    """Return path to the checkpoint, searching *output_dir* as fallback."""
    if checkpoint:
        if not os.path.isfile(checkpoint):
            print(f"[ERROR] Checkpoint not found: {checkpoint}", file=sys.stderr)
            sys.exit(1)
        return checkpoint

    for name in ("best.pt", "last.pt"):
        candidate = os.path.join(output_dir, name)
        if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
            return candidate

    print("[ERROR] No checkpoint found. Run train.py first.", file=sys.stderr)
    sys.exit(1)


def _write_preprocess_json(output_dir: str) -> None:
    """Write preprocessing config for the inference pipeline."""
    data = {
        "resize": {"width": _IMG_SIZE, "height": _IMG_SIZE, "keep_ratio": True},
        "pad_value": [114, 114, 114],
        "normalize": False,
        "mean": [0.0, 0.0, 0.0],
        "std": [1.0, 1.0, 1.0],
        "color_convert": "BGR2RGB",
        "scale": _SCALE,
    }
    path = os.path.join(output_dir, "preprocess.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"[EXPORT] preprocess.json written to {path}", flush=True)


def _write_labels_json(output_dir: str) -> None:
    """Write class label mapping."""
    data = {
        "labels": _LABELS,
        "num_classes": _NUM_CLASSES,
    }
    path = os.path.join(output_dir, "labels.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"[EXPORT] labels.json written to {path}", flush=True)


def _write_manifest_json(output_dir: str, version: str) -> None:
    """Write model manifest with runtime metadata."""
    data = {
        "capability": "face_detect",
        "version": version,
        "framework": "onnxruntime",
        "model_file": "model.onnx",
        "input_size": [_IMG_SIZE, _IMG_SIZE],
        "num_classes": _NUM_CLASSES,
        "labels": _LABELS,
        "nms_threshold": 0.45,
        "confidence_threshold": 0.25,
    }
    path = os.path.join(output_dir, "manifest.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"[EXPORT] manifest.json written to {path}", flush=True)


def _export_onnx(checkpoint: str, output_dir: str) -> str:
    """Export the YOLOv8 checkpoint to ONNX and return the exported path."""
    try:
        from ultralytics import YOLO
    except ImportError:
        print(
            "[ERROR] ultralytics is not installed.  "
            "Install it with:  pip install ultralytics",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"[EXPORT] Loading checkpoint: {checkpoint}", flush=True)
    model = YOLO(checkpoint)

    print("[EXPORT] Exporting to ONNX …", flush=True)
    exported_path = model.export(
        format="onnx",
        opset=17,
        dynamic=True,
        simplify=True,
        imgsz=_IMG_SIZE,
    )
    print(f"[EXPORT] Ultralytics export complete: {exported_path}", flush=True)

    # Copy to canonical location
    dest = os.path.join(output_dir, "model.onnx")
    if os.path.abspath(exported_path) != os.path.abspath(dest):
        shutil.copy2(exported_path, dest)
        print(f"[EXPORT] ONNX model copied to {dest}", flush=True)
    else:
        print(f"[EXPORT] ONNX model already at {dest}", flush=True)

    return dest


def main():
    args = _parse_args()
    os.makedirs(args.output, exist_ok=True)

    checkpoint = _resolve_checkpoint(args.checkpoint, args.output)

    _export_onnx(checkpoint, args.output)
    _write_preprocess_json(args.output)
    _write_labels_json(args.output)
    _write_manifest_json(args.output, args.version)

    print("[EXPORT] Done", flush=True)


if __name__ == "__main__":
    main()
