"""Export desktop_recapture_detect model checkpoint to ONNX format.

Usage:
    python export.py --output /workspace/models/desktop_recapture_detect/v1.0.0/ \\
                     --version 1.0.0

    python export.py --output /workspace/models/desktop_recapture_detect/v1.0.0/ \\
                     --version 1.0.0 \\
                     --checkpoint /workspace/runs/best.pth

Migrated from LeeYou/recapture_detect (dev branch) for ai_platform integration.
"""

import argparse
import json
import os
import sys

_IMG_SIZE = 224
_LABELS = ["real", "fake"]

# ImageNet normalization
_MEAN = [0.485, 0.456, 0.406]
_STD  = [0.229, 0.224, 0.225]


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Export desktop_recapture_detect EfficientNet-B0 to ONNX",
    )
    parser.add_argument(
        "--output",
        default="/workspace/models/desktop_recapture_detect/v1.0.0/",
        help="Model output directory",
    )
    parser.add_argument("--version", default="1.0.0", help="Model version string")
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="Path to .pth checkpoint (defaults to best.pth in --output)",
    )
    return parser.parse_args()


def _resolve_checkpoint(checkpoint, output_dir):
    if checkpoint:
        if not os.path.isfile(checkpoint):
            print(f"[ERROR] Checkpoint not found: {checkpoint}", file=sys.stderr)
            sys.exit(1)
        return checkpoint

    for name in ("best.pth", "last.pth"):
        candidate = os.path.join(output_dir, name)
        if os.path.isfile(candidate) and os.path.getsize(candidate) > 0:
            return candidate

    print("[ERROR] No checkpoint found. Run train.py first.", file=sys.stderr)
    sys.exit(1)


def _load_checkpoint(path, device):
    import torch
    try:
        return torch.load(path, map_location=device, weights_only=True)
    except Exception:
        return torch.load(path, map_location=device, weights_only=False)


def _write_preprocess_json(output_dir):
    data = {
        "resize": {"width": _IMG_SIZE, "height": _IMG_SIZE, "keep_ratio": False},
        "normalize": True,
        "mean": _MEAN,
        "std": _STD,
        "color_convert": "BGR2RGB",
        "scale": 1.0 / 255.0,
    }
    path = os.path.join(output_dir, "preprocess.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"[EXPORT] preprocess.json written to {path}", flush=True)


def _write_labels_json(output_dir):
    data = {
        "labels": _LABELS,
        "num_classes": len(_LABELS),
    }
    path = os.path.join(output_dir, "labels.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"[EXPORT] labels.json written to {path}", flush=True)


def _write_manifest_json(output_dir, version):
    data = {
        "capability": "desktop_recapture_detect",
        "model_version": version,
        "framework": "onnxruntime",
        "model_file": "model.onnx",
        "input_size": [_IMG_SIZE, _IMG_SIZE],
        "num_classes": len(_LABELS),
        "labels": _LABELS,
        "threshold": 0.5,
        "preprocessing": {
            "mean": _MEAN,
            "std": _STD,
        },
    }
    path = os.path.join(output_dir, "manifest.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    print(f"[EXPORT] manifest.json written to {path}", flush=True)


def _export_onnx(checkpoint_path, output_dir, version):
    import torch

    device = torch.device("cpu")
    ckpt = _load_checkpoint(checkpoint_path, device)

    from model import DesktopRecaptureDetector
    model = DesktopRecaptureDetector(pretrained=False).to(device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    onnx_path = os.path.join(output_dir, "model.onnx")
    dummy = torch.randn(1, 3, _IMG_SIZE, _IMG_SIZE, device=device)

    with torch.no_grad():
        torch.onnx.export(
            model,
            dummy,
            onnx_path,
            input_names=["input_image"],
            output_names=["fake_logit"],
            dynamic_axes={"input_image": {0: "batch"}, "fake_logit": {0: "batch"}},
            opset_version=17,
            do_constant_folding=True,
        )

    print(f"[EXPORT] ONNX model saved to {onnx_path}", flush=True)
    print(f"[EXPORT] Source checkpoint epoch: {ckpt.get('epoch', 'N/A')}", flush=True)
    return onnx_path


def main():
    args = _parse_args()
    os.makedirs(args.output, exist_ok=True)

    checkpoint = _resolve_checkpoint(args.checkpoint, args.output)
    print(f"[EXPORT] Loading checkpoint: {checkpoint}", flush=True)

    _export_onnx(checkpoint, args.output, args.version)
    _write_preprocess_json(args.output)
    _write_labels_json(args.output)
    _write_manifest_json(args.output, args.version)

    print("[EXPORT] Done", flush=True)


if __name__ == "__main__":
    main()
