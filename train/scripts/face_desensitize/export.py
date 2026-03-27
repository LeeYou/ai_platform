"""Export face_desensitize (人脸脱敏/像素化) model to ONNX format.

Usage:
    python export.py --output /workspace/models/face_desensitize/v1.0.0/ --version 1.0.0

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _parse_args():
    p = argparse.ArgumentParser(description="Export face_desensitize to ONNX")
    p.add_argument("--output",     default="/workspace/models/face_desensitize/v1.0.0/")
    p.add_argument("--version",    default="1.0.0")
    p.add_argument("--checkpoint", default=None)
    return p.parse_args()


def _write_preprocess_json(output_path: str) -> None:
    data = {
        "resize": {"width": 640, "height": 640, "keep_ratio": True},
        "pad_value": [114, 114, 114],
        "normalize": True,
        "mean": [0.485, 0.456, 0.406],
        "std":  [0.229, 0.224, 0.225],
        "color_convert": "BGR2RGB",
    }
    path = os.path.join(output_path, "preprocess.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[EXPORT] preprocess.json → {path}", flush=True)


def _write_labels_json(output_path: str) -> None:
    data = {"labels": [], "num_classes": 2}
    path = os.path.join(output_path, "labels.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[EXPORT] labels.json → {path}", flush=True)


def main():
    args = _parse_args()
    os.makedirs(args.output, exist_ok=True)

    try:
        import torch
    except ImportError:
        print("[ERROR] PyTorch not installed.", file=sys.stderr)
        sys.exit(1)

    ckpt_path = args.checkpoint
    if not ckpt_path:
        for fname in ("best.pt", "last.pt"):
            candidate = os.path.join(args.output, fname)
            if os.path.exists(candidate) and os.path.getsize(candidate) > 0:
                ckpt_path = candidate
                break
    if not ckpt_path:
        print("[ERROR] No checkpoint found. Run train.py first.", file=sys.stderr)
        sys.exit(1)

    print(f"[EXPORT] Loading checkpoint: {ckpt_path}", flush=True)

    # TODO: replace with real MTCNN+pixel blur model class
    import torch.nn as nn
    model = nn.Sequential(
        nn.Flatten(),
        nn.Linear(1228800, 256),
        nn.ReLU(),
        nn.Linear(256, max(1, 2)),
    )
    ckpt = torch.load(ckpt_path, map_location="cpu")
    model.load_state_dict(ckpt["model"] if "model" in ckpt else ckpt)
    model.eval()

    onnx_path = os.path.join(args.output, "model.onnx")
    dummy = torch.zeros(1, 3, 640, 640)
    try:
        import torch.onnx
        torch.onnx.export(model, dummy, onnx_path, opset_version=17,
                          input_names=["input"], output_names=["output"],
                          dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}})
        print(f"[EXPORT] ONNX → {onnx_path}", flush=True)
    except Exception as exc:
        print(f"[ERROR] ONNX export failed: {exc}", file=sys.stderr)
        sys.exit(1)

    _write_preprocess_json(args.output)
    _write_labels_json(args.output)
    print("[EXPORT] Done", flush=True)


if __name__ == "__main__":
    main()
