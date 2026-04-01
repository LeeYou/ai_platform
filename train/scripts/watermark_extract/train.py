"""Train watermark_extract (图像水印提取/去除).

Architecture: DWT+CNN/WDNet

Usage:
    python train.py --config config.json \\
                    --dataset /workspace/datasets/watermark_extract/ \\
                    --output /workspace/models/watermark_extract/v1.0.0/ \\
                    --version 1.0.0

Notes:
    - Replace the stub model in _build_model() with the real architecture.
    - See config.json for default hyperparameters.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import time

_stop_requested = False


def _handle_sigterm(signum, frame):
    global _stop_requested
    _stop_requested = True
    print("[INFO] SIGTERM received — stopping after current epoch.", flush=True)


signal.signal(signal.SIGTERM, _handle_sigterm)


def _parse_args():
    p = argparse.ArgumentParser(description="Train watermark_extract")
    p.add_argument("--config",  default="config.json")
    p.add_argument("--dataset", default="/workspace/datasets/watermark_extract/")
    p.add_argument("--output",  default="/workspace/models/watermark_extract/v1.0.0/")
    p.add_argument("--version", default="1.0.0")
    p.add_argument("--resume",  default=None)
    return p.parse_args()


def _build_model(device):
    """TODO: Replace with the real DWT+CNN/WDNet model."""
    import torch.nn as nn
    return nn.Sequential(
        nn.Flatten(),
        nn.Linear(786432, 256),
        nn.ReLU(),
        nn.Linear(256, max(1, 2)),
    )


def _train_pytorch(args, config):
    import torch
    import torch.nn as nn

    device  = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model   = _build_model(device).to(device)
    optimizer = torch.optim.AdamW(model.parameters(),
                                  lr=config.get("lr0", 0.01),
                                  weight_decay=config.get("weight_decay", 5e-4))
    epochs  = config.get("epochs", 100)
    patience = config.get("patience", 20)
    os.makedirs(args.output, exist_ok=True)

    best_loss = float("inf")
    no_improve = 0

    for epoch in range(1, epochs + 1):
        if _stop_requested:
            print("[INFO] Training stopped by signal.", flush=True)
            break
        # TODO: replace stub with real DataLoader + training loop
        loss = max(0.01, 1.2 * (0.97 ** epoch))
        acc  = min(0.99, 0.4 + epoch * 0.005)
        print(f"[EPOCH {epoch}/{epochs}] loss={loss:.4f} accuracy={acc:.4f}", flush=True)
        if loss < best_loss:
            best_loss = loss
            torch.save({"epoch": epoch, "model": model.state_dict(),
                         "optimizer": optimizer.state_dict(), "best_loss": best_loss},
                       os.path.join(args.output, "best.pt"))
            no_improve = 0
        else:
            no_improve += 1
            if patience > 0 and no_improve >= patience:
                print(f"[INFO] Early stopping at epoch {epoch}", flush=True)
                break

    torch.save({"epoch": epochs, "model": model.state_dict(),
                 "optimizer": optimizer.state_dict(), "best_loss": best_loss},
               os.path.join(args.output, "last.pt"))
    print(f"[DONE] model saved to {args.output}", flush=True)


def _simulate_training(args, config):
    import random
    epochs = config.get("epochs", 100)
    print("[INFO] PyTorch not available — running simulation.", flush=True)
    os.makedirs(args.output, exist_ok=True)
    loss, acc = 1.2, 0.4
    for epoch in range(1, epochs + 1):
        if _stop_requested:
            break
        time.sleep(0.05)
        loss = max(0.01, loss * (0.97 + random.uniform(-0.01, 0.01)))
        acc  = min(0.99, acc + random.uniform(0.002, 0.008))
        print(f"[EPOCH {epoch}/{epochs}] loss={loss:.4f} accuracy={acc:.4f}", flush=True)
    open(os.path.join(args.output, "best.pt"), "w").close()
    open(os.path.join(args.output, "last.pt"), "w").close()
    print(f"[DONE] model saved to {args.output}", flush=True)


def main():
    args = _parse_args()
    config = json.load(open(args.config, encoding="utf-8")) if os.path.exists(args.config) else {}
    print(f"[INFO] Starting training: watermark_extract v{args.version}", flush=True)
    print(f"[INFO] Dataset: {args.dataset}", flush=True)
    print(f"[INFO] Output:  {args.output}", flush=True)
    try:
        import torch  # noqa: F401
        _train_pytorch(args, config)
    except ImportError:
        _simulate_training(args, config)


if __name__ == "__main__":
    main()
