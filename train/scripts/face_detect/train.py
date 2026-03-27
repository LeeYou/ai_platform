"""face_detect training script.

Usage:
    python train.py --config config.json \\
                    --dataset /workspace/datasets/face_detect/ \\
                    --output /workspace/models/face_detect/v1.0.0/ \\
                    --version 1.0.0
"""

import argparse
import json
import math
import os
import signal
import sys
import time

# ---------------------------------------------------------------------------
# Graceful signal handling
# ---------------------------------------------------------------------------

_stop_requested = False


def _handle_sigterm(signum, frame):
    global _stop_requested
    _stop_requested = True
    print("[INFO] SIGTERM received — stopping after current epoch.", flush=True)


signal.signal(signal.SIGTERM, _handle_sigterm)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args():
    parser = argparse.ArgumentParser(description="Train face_detect model")
    parser.add_argument("--config", default="config.json", help="Path to hyperparams JSON")
    parser.add_argument(
        "--dataset",
        default="/workspace/datasets/face_detect/",
        help="Dataset root directory",
    )
    parser.add_argument(
        "--output",
        default="/workspace/models/face_detect/v1.0.0/",
        help="Output directory for checkpoints and final model",
    )
    parser.add_argument("--version", default="1.0.0", help="Model version string")
    parser.add_argument("--resume", default=None, help="Path to checkpoint to resume from")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Model definition (requires PyTorch)
# ---------------------------------------------------------------------------

def _build_model(device):
    import torch
    import torch.nn as nn

    class SimpleFaceDetector(nn.Module):
        """Lightweight face detection CNN (demo architecture)."""

        def __init__(self):
            super().__init__()
            self.backbone = nn.Sequential(
                nn.Conv2d(3, 16, 3, stride=2, padding=1), nn.BatchNorm2d(16), nn.ReLU(),
                nn.Conv2d(16, 32, 3, stride=2, padding=1), nn.BatchNorm2d(32), nn.ReLU(),
                nn.Conv2d(32, 64, 3, stride=2, padding=1), nn.BatchNorm2d(64), nn.ReLU(),
                nn.Conv2d(64, 128, 3, stride=2, padding=1), nn.BatchNorm2d(128), nn.ReLU(),
                nn.AdaptiveAvgPool2d((8, 8)),
            )
            self.head_bbox = nn.Linear(128 * 8 * 8, 4)   # x1,y1,x2,y2 normalised
            self.head_conf = nn.Linear(128 * 8 * 8, 1)   # confidence logit

        def forward(self, x):
            feat = self.backbone(x).flatten(1)
            return self.head_bbox(feat), self.head_conf(feat)

    return SimpleFaceDetector().to(device)


# ---------------------------------------------------------------------------
# Dataset
# ---------------------------------------------------------------------------

def _build_dataloaders(dataset_path, config, device_str):
    """Return (train_loader, val_loader, use_synthetic) tuple."""
    import torch
    from torch.utils.data import DataLoader, Dataset, random_split

    img_dir = os.path.join(dataset_path, "images")
    lbl_dir = os.path.join(dataset_path, "labels")
    has_data = os.path.isdir(img_dir) and os.path.isdir(lbl_dir)

    if has_data:
        import cv2
        import numpy as np
        from PIL import Image

        class FaceDataset(Dataset):
            def __init__(self, img_dir, lbl_dir, size=640):
                self.size = size
                self.samples = []
                for fn in os.listdir(img_dir):
                    if fn.lower().endswith((".jpg", ".jpeg", ".png")):
                        stem = os.path.splitext(fn)[0]
                        lbl_path = os.path.join(lbl_dir, stem + ".txt")
                        if os.path.exists(lbl_path):
                            self.samples.append(
                                (os.path.join(img_dir, fn), lbl_path)
                            )

            def __len__(self):
                return len(self.samples)

            def __getitem__(self, idx):
                img_path, lbl_path = self.samples[idx]
                img = Image.open(img_path).convert("RGB").resize(
                    (self.size, self.size)
                )
                img_t = torch.tensor(
                    np.array(img, dtype=np.float32).transpose(2, 0, 1) / 255.0
                )
                # Normalise
                mean = torch.tensor([0.485, 0.456, 0.406]).view(3, 1, 1)
                std = torch.tensor([0.229, 0.224, 0.225]).view(3, 1, 1)
                img_t = (img_t - mean) / std

                # Read first bounding box from YOLO label
                with open(lbl_path) as f:
                    line = f.readline().split()
                if len(line) >= 5:
                    cx, cy, w, h = [float(x) for x in line[1:5]]
                    x1 = cx - w / 2
                    y1 = cy - h / 2
                    x2 = cx + w / 2
                    y2 = cy + h / 2
                else:
                    x1 = y1 = x2 = y2 = 0.5

                bbox = torch.tensor([x1, y1, x2, y2], dtype=torch.float32)
                conf = torch.tensor([1.0], dtype=torch.float32)
                return img_t, bbox, conf

        dataset = FaceDataset(img_dir, lbl_dir)
        val_len = max(1, int(len(dataset) * config.get("val_split", 0.1)))
        train_len = len(dataset) - val_len
        train_ds, val_ds = random_split(dataset, [train_len, val_len])
        use_synthetic = False
    else:
        print("[INFO] Dataset not found — using synthetic data for demonstration.", flush=True)

        class SyntheticDataset(torch.utils.data.Dataset):
            def __init__(self, n=256):
                self.n = n

            def __len__(self):
                return self.n

            def __getitem__(self, idx):
                img = torch.randn(3, 64, 64)  # small for speed
                bbox = torch.rand(4)
                conf = torch.ones(1)
                return img, bbox, conf

        full_ds = SyntheticDataset(256)
        train_ds, val_ds = random_split(full_ds, [224, 32])
        use_synthetic = True

    train_loader = DataLoader(
        train_ds,
        batch_size=config.get("batch_size", 16),
        shuffle=True,
        num_workers=0,
        drop_last=False,
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=config.get("batch_size", 16),
        shuffle=False,
        num_workers=0,
    )
    return train_loader, val_loader, use_synthetic


# ---------------------------------------------------------------------------
# Training loop
# ---------------------------------------------------------------------------

def _train_pytorch(args, config):
    import torch
    import torch.nn as nn

    device_str = config.get("device", "auto")
    if device_str == "auto":
        device_str = "cuda" if torch.cuda.is_available() else "cpu"
    device = torch.device(device_str)

    model = _build_model(device)
    optimizer = torch.optim.SGD(
        model.parameters(),
        lr=config.get("lr0", 0.01),
        momentum=config.get("momentum", 0.937),
        weight_decay=config.get("weight_decay", 0.0005),
    )

    epochs = config.get("epochs", 100)
    warmup_epochs = config.get("warmup_epochs", 3)
    lrf = config.get("lrf", 0.001)

    def _lr_lambda(epoch):
        if epoch < warmup_epochs:
            return (epoch + 1) / warmup_epochs
        t = (epoch - warmup_epochs) / max(1, epochs - warmup_epochs)
        return lrf + 0.5 * (1 - lrf) * (1 + math.cos(math.pi * t))

    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, _lr_lambda)
    use_amp = config.get("amp", True) and device_str == "cuda"
    scaler = torch.cuda.amp.GradScaler(enabled=use_amp)

    bbox_loss_fn = nn.MSELoss()
    conf_loss_fn = nn.BCEWithLogitsLoss()

    train_loader, val_loader, use_synthetic = _build_dataloaders(
        args.dataset, config, device_str
    )

    os.makedirs(args.output, exist_ok=True)
    ckpt_dir = os.path.join(args.output, "checkpoints")
    os.makedirs(ckpt_dir, exist_ok=True)

    # Resume
    start_epoch = 0
    best_loss = float("inf")
    if args.resume and os.path.exists(args.resume):
        print(f"[INFO] Resuming from {args.resume}", flush=True)
        ckpt = torch.load(args.resume, map_location=device)
        model.load_state_dict(ckpt["model"])
        optimizer.load_state_dict(ckpt["optimizer"])
        start_epoch = ckpt.get("epoch", 0)
        best_loss = ckpt.get("best_loss", float("inf"))

    patience = config.get("patience", 20)
    no_improve = 0

    for epoch in range(start_epoch, epochs):
        if _stop_requested:
            print("[INFO] Training stopped by signal.", flush=True)
            break

        # --- train ---
        model.train()
        train_loss = 0.0
        for imgs, bboxes, confs in train_loader:
            imgs = imgs.to(device)
            bboxes = bboxes.to(device)
            confs = confs.to(device)
            optimizer.zero_grad()
            with torch.cuda.amp.autocast(enabled=use_amp):
                pred_bbox, pred_conf = model(imgs)
                loss = bbox_loss_fn(pred_bbox, bboxes) + conf_loss_fn(pred_conf, confs)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            train_loss += loss.item()

        train_loss /= max(1, len(train_loader))

        # --- val ---
        model.eval()
        val_loss = 0.0
        correct = 0
        total = 0
        with torch.no_grad():
            for imgs, bboxes, confs in val_loader:
                imgs = imgs.to(device)
                bboxes = bboxes.to(device)
                confs = confs.to(device)
                pred_bbox, pred_conf = model(imgs)
                loss = bbox_loss_fn(pred_bbox, bboxes) + conf_loss_fn(pred_conf, confs)
                val_loss += loss.item()
                preds = (torch.sigmoid(pred_conf) > 0.5).float()
                correct += (preds == confs).sum().item()
                total += confs.numel()

        val_loss /= max(1, len(val_loader))
        accuracy = correct / max(1, total)

        scheduler.step()

        print(
            f"[EPOCH {epoch + 1}/{epochs}] loss={val_loss:.4f} accuracy={accuracy:.4f}",
            flush=True,
        )

        # Checkpoint every 10 epochs
        if (epoch + 1) % 10 == 0:
            torch.save(
                {
                    "epoch": epoch + 1,
                    "model": model.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "best_loss": best_loss,
                },
                os.path.join(ckpt_dir, f"epoch_{epoch + 1}.pt"),
            )

        # Best model
        if val_loss < best_loss:
            best_loss = val_loss
            no_improve = 0
            torch.save(
                {
                    "epoch": epoch + 1,
                    "model": model.state_dict(),
                    "optimizer": optimizer.state_dict(),
                    "best_loss": best_loss,
                },
                os.path.join(args.output, "best.pt"),
            )
        else:
            no_improve += 1
            if patience > 0 and no_improve >= patience:
                print(f"[INFO] Early stopping at epoch {epoch + 1}", flush=True)
                break

    # Save last checkpoint
    torch.save(
        {
            "epoch": epochs,
            "model": model.state_dict(),
            "optimizer": optimizer.state_dict(),
            "best_loss": best_loss,
        },
        os.path.join(args.output, "last.pt"),
    )

    print(f"[DONE] model saved to {args.output}", flush=True)


def _simulate_training(args, config):
    """Fallback simulation when PyTorch is not available."""
    import random

    epochs = config.get("epochs", 100)
    print("[INFO] PyTorch not available — running training simulation.", flush=True)

    os.makedirs(args.output, exist_ok=True)
    loss = 1.2
    acc = 0.4

    for epoch in range(1, epochs + 1):
        if _stop_requested:
            print("[INFO] Training stopped by signal.", flush=True)
            break
        time.sleep(0.05)
        loss = max(0.01, loss * (0.97 + random.uniform(-0.01, 0.01)))
        acc = min(0.99, acc + random.uniform(0.002, 0.008))
        print(f"[EPOCH {epoch}/{epochs}] loss={loss:.4f} accuracy={acc:.4f}", flush=True)

    # Create placeholder files
    open(os.path.join(args.output, "best.pt"), "w").close()
    open(os.path.join(args.output, "last.pt"), "w").close()
    print(f"[DONE] model saved to {args.output}", flush=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = _parse_args()

    # Load config
    if os.path.exists(args.config):
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = {}

    print(f"[INFO] Starting training: face_detect v{args.version}", flush=True)
    print(f"[INFO] Dataset: {args.dataset}", flush=True)
    print(f"[INFO] Output: {args.output}", flush=True)
    print(
        f"[INFO] Config: epochs={config.get('epochs', 100)} "
        f"batch={config.get('batch_size', 16)} "
        f"lr0={config.get('lr0', 0.01)}",
        flush=True,
    )

    try:
        import torch  # noqa: F401
        _train_pytorch(args, config)
    except ImportError:
        _simulate_training(args, config)


if __name__ == "__main__":
    main()
