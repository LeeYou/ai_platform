"""Export face_detect model checkpoint to ONNX format.

Usage:
    python export.py --output /workspace/models/face_detect/v1.0.0/ \\
                     --version 1.0.0
"""

import argparse
import json
import os
import sys


def _parse_args():
    parser = argparse.ArgumentParser(description="Export face_detect model to ONNX")
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


def _write_preprocess_json(output_path: str) -> None:
    data = {
        "resize": {"width": 640, "height": 640, "keep_ratio": True},
        "pad_value": [114, 114, 114],
        "normalize": True,
        "mean": [0.485, 0.456, 0.406],
        "std": [0.229, 0.224, 0.225],
        "color_convert": "BGR2RGB",
    }
    path = os.path.join(output_path, "preprocess.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[EXPORT] preprocess.json written to {path}", flush=True)


def _write_labels_json(output_path: str) -> None:
    data = {"labels": ["face"], "num_classes": 1}
    path = os.path.join(output_path, "labels.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[EXPORT] labels.json written to {path}", flush=True)


def main():
    args = _parse_args()
    os.makedirs(args.output, exist_ok=True)

    try:
        import torch
    except ImportError:
        print("[ERROR] PyTorch is not installed. Cannot export model.", file=sys.stderr)
        sys.exit(1)

    # Locate checkpoint
    ckpt_path = args.checkpoint
    if not ckpt_path:
        best_pt = os.path.join(args.output, "best.pt")
        last_pt = os.path.join(args.output, "last.pt")
        if os.path.exists(best_pt) and os.path.getsize(best_pt) > 0:
            ckpt_path = best_pt
        elif os.path.exists(last_pt) and os.path.getsize(last_pt) > 0:
            ckpt_path = last_pt
        else:
            print("[ERROR] No checkpoint found. Run train.py first.", file=sys.stderr)
            sys.exit(1)

    print(f"[EXPORT] Loading checkpoint: {ckpt_path}", flush=True)

    # Rebuild model architecture
    import torch.nn as nn

    class SimpleFaceDetector(nn.Module):
        def __init__(self):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Conv2d(3, 16, 3, stride=2, padding=1), nn.BatchNorm2d(16), nn.ReLU(),
                nn.Conv2d(16, 32, 3, stride=2, padding=1), nn.BatchNorm2d(32), nn.ReLU(),
                nn.Conv2d(32, 64, 3, stride=2, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
                nn.Conv2d(64, 128, 3, stride=2, padding=1), nn.BatchNorm2d(128), nn.ReLU(),
                nn.AdaptiveAvgPool2d((8, 8)),
            )
            self.head_bbox = nn.Linear(128 * 8 * 8, 4)
            self.head_conf = nn.Linear(128 * 8 * 8, 1)

        def forward(self, x):
            feat = self.backbone(x).flatten(1)
            return self.head_bbox(feat), self.head_conf(feat)

    model = SimpleFaceDetector()
    ckpt = torch.load(ckpt_path, map_location="cpu")
    if "model" in ckpt:
        model.load_state_dict(ckpt["model"])
    else:
        model.load_state_dict(ckpt)
    model.eval()

    # Export ONNX
    onnx_path = os.path.join(args.output, "model.onnx")
    dummy = torch.zeros(1, 3, 640, 640)

    try:
        import torch.onnx

        torch.onnx.export(
            model,
            dummy,
            onnx_path,
            opset_version=17,
            input_names=["input"],
            output_names=["bbox", "confidence"],
            dynamic_axes={
                "input": {0: "batch_size"},
                "bbox": {0: "batch_size"},
                "confidence": {0: "batch_size"},
            },
        )
        print(f"[EXPORT] ONNX model saved to {onnx_path}", flush=True)
    except Exception as exc:
        print(f"[ERROR] ONNX export failed: {exc}", file=sys.stderr)
        sys.exit(1)

    _write_preprocess_json(args.output)
    _write_labels_json(args.output)

    print("[EXPORT] Done", flush=True)


if __name__ == "__main__":
    main()
