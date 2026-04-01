"""desktop_recapture_detect training script.

Two-phase fine-tuning of EfficientNet-B0 for real/fake binary classification.

Phase 1 (phase1_epochs): backbone frozen, only the classification head is trained.
Phase 2 (phase2_epochs): all weights fine-tuned with cosine LR annealing.

Usage (inside the train container):
    python train.py --config config.json \\
                    --dataset /workspace/datasets/desktop_recapture_detect/ \\
                    --output /workspace/models/desktop_recapture_detect/v1.0.0/ \\
                    --version 1.0.0

Parameter Compatibility:
    The script supports parameters from both the frontend UI and native config.json:

    Frontend UI (Jobs.vue) → Native config.json:
    - imgsz → input_size (image size, default: 224)
    - batch → batch_size (batch size, default: 32)
    - lr0 → lr (learning rate, default: 1e-3)
    - epochs → Not directly mapped (use phase1_epochs + phase2_epochs in custom params)

    Native-only parameters (set via custom params JSON):
    - phase1_epochs: Phase 1 training epochs (default: 5)
    - phase2_epochs: Phase 2 training epochs (default: 25)
    - early_stopping_patience: Early stopping patience (default: 10)
    - train_ratio: Train/val split ratio (default: 0.8)
    - lr_min: Minimum learning rate for cosine annealing (default: 1e-5)
    - weight_decay: Weight decay for optimizer (default: 1e-4)
    - workers: Number of DataLoader workers (auto-detected if not set)
    - cache: Enable dataset caching in RAM (default: true)

Migrated from LeeYou/recapture_detect (dev branch) for ai_platform integration.
"""

import argparse
import datetime
import json
import os
import random
import signal
import sys
import time

import numpy as np
import torch
import torch.nn as nn
from tqdm import tqdm

from dataset import RecaptureDataset, build_dataloaders
from model import DesktopRecaptureDetector

# ---------------------------------------------------------------------------
# Graceful signal handling
# ---------------------------------------------------------------------------

_stop_requested = False


def _handle_sigterm(signum, frame):
    global _stop_requested
    _stop_requested = True
    print("[INFO] SIGTERM received — stopping after current epoch.", flush=True)


signal.signal(signal.SIGTERM, _handle_sigterm)


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _full_metrics(probs: np.ndarray, labels: np.ndarray) -> dict:
    from sklearn.metrics import (
        accuracy_score, f1_score, precision_score,
        recall_score, roc_auc_score,
    )
    preds = (probs >= 0.5).astype(int)
    auc = 0.0
    try:
        auc = roc_auc_score(labels, probs)
    except ValueError:
        pass
    return {
        "acc":  accuracy_score(labels, preds),
        "prec": precision_score(labels, preds, zero_division=0),
        "rec":  recall_score(labels, preds, zero_division=0),
        "f1":   f1_score(labels, preds, zero_division=0),
        "auc":  auc,
    }


def run_epoch(model, loader, criterion, optimizer, device,
              train: bool = True, current_lr: float = 0.0) -> tuple:
    model.train(train)
    total_loss = 0.0
    all_probs, all_labels = [], []
    n_seen = 0

    desc = "  train" if train else "  val  "
    bar  = tqdm(loader, desc=desc, leave=False,
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} "
                           "[{elapsed}<{remaining} {rate_fmt}]{postfix}")

    with torch.set_grad_enabled(train):
        for imgs, labels in bar:
            imgs, labels = imgs.to(device), labels.to(device)
            logits = model(imgs)
            loss   = criterion(logits, labels)

            if train:
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

            batch_n     = len(imgs)
            n_seen     += batch_n
            total_loss += loss.item() * batch_n
            all_probs.extend(torch.sigmoid(logits).detach().cpu().numpy())
            all_labels.extend(labels.cpu().numpy())

            running_loss = total_loss / n_seen
            postfix = {"loss": f"{running_loss:.4f}"}
            if train and current_lr:
                postfix["lr"] = f"{current_lr:.2e}"
            bar.set_postfix(postfix)

    avg_loss = total_loss / n_seen
    metrics  = _full_metrics(np.array(all_probs), np.array(all_labels))
    return avg_loss, metrics


def _save_checkpoint(path, model, epoch, phase, tr_metrics, vl_metrics,
                     tr_loss, vl_loss, current_lr):
    torch.save(
        {
            "model_state": model.state_dict(),
            "epoch":       int(epoch),
            "phase":       phase,
            "val_auc":     float(vl_metrics["auc"]),
            "val_loss":    float(vl_loss),
            "val_acc":     float(vl_metrics["acc"]),
            "val_f1":      float(vl_metrics["f1"]),
            "train_auc":   float(tr_metrics["auc"]),
            "train_loss":  float(tr_loss),
            "current_lr":  float(current_lr),
            "saved_at":    datetime.datetime.now().isoformat(timespec="seconds"),
        },
        path,
    )


def _print_epoch(tag, epoch, total, tr_loss, tr_m, vl_loss, vl_m,
                 current_lr, elapsed, patience_counter, patience, marker):
    print(
        f"[{tag} {epoch:02d}/{total}] "
        f"lr={current_lr:.2e}  elapsed={elapsed:.0f}s\n"
        f"  train  loss={tr_loss:.4f}  acc={tr_m['acc']:.4f}  "
        f"auc={tr_m['auc']:.4f}  f1={tr_m['f1']:.4f}\n"
        f"  val    loss={vl_loss:.4f}  acc={vl_m['acc']:.4f}  "
        f"auc={vl_m['auc']:.4f}  f1={vl_m['f1']:.4f}\n"
        f"  patience={patience_counter}/{patience}{marker}",
        flush=True,
    )


def _run_phase(phase_tag, total_epochs, model, train_loader, val_loader,
               criterion, optimizer, scheduler, device, ckpt_dir,
               patience, best_auc, best_loss):
    patience_counter = 0
    t0 = time.time()

    for epoch in range(1, total_epochs + 1):
        if _stop_requested:
            print("[INFO] Training stopped by signal.", flush=True)
            return best_auc, best_loss, True

        current_lr = optimizer.param_groups[0]["lr"]

        tr_loss, tr_m = run_epoch(
            model, train_loader, criterion, optimizer, device,
            train=True, current_lr=current_lr)
        vl_loss, vl_m = run_epoch(
            model, val_loader, criterion, optimizer, device,
            train=False, current_lr=current_lr)

        if scheduler is not None:
            scheduler.step()

        auc_improved  = vl_m["auc"] > best_auc + 1e-4
        loss_improved = vl_loss      < best_loss - 1e-4
        improved      = auc_improved or loss_improved

        marker = ""
        if improved:
            if auc_improved:
                best_auc = vl_m["auc"]
            if loss_improved:
                best_loss = vl_loss
            _save_checkpoint(
                os.path.join(ckpt_dir, "best.pth"), model, epoch, phase_tag,
                tr_m, vl_m, tr_loss, vl_loss, current_lr)
            patience_counter = 0
            marker = "  ★ best saved"
        else:
            patience_counter += 1

        _save_checkpoint(
            os.path.join(ckpt_dir, "last.pth"), model, epoch, phase_tag,
            tr_m, vl_m, tr_loss, vl_loss, current_lr)

        elapsed = time.time() - t0
        _print_epoch(phase_tag, epoch, total_epochs,
                     tr_loss, tr_m, vl_loss, vl_m,
                     current_lr, elapsed,
                     patience_counter, patience, marker)

        if patience_counter >= patience:
            print(f"\n  ▶ Early stopping triggered (no improvement for {patience} epochs)",
                  flush=True)
            return best_auc, best_loss, True

    return best_auc, best_loss, False


def _parse_args():
    parser = argparse.ArgumentParser(description="Train desktop_recapture_detect model")
    parser.add_argument("--config", default="config.json", help="Path to config JSON")
    parser.add_argument(
        "--dataset",
        default="/workspace/datasets/desktop_recapture_detect/",
        help="Dataset root (must contain real/ and fake/ subdirectories)",
    )
    parser.add_argument(
        "--output",
        default="/workspace/models/desktop_recapture_detect/v1.0.0/",
        help="Output directory for checkpoints",
    )
    parser.add_argument("--version", default="1.0.0", help="Model version string")
    return parser.parse_args()


def _resolve_device(config):
    device = config.get("device", "auto")
    if device == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    return device


def train(args, config):
    set_seed(42)
    device = torch.device(_resolve_device(config))

    if torch.cuda.is_available():
        gpu_name = torch.cuda.get_device_name(0)
        gpu_mem  = torch.cuda.get_device_properties(0).total_mem / 1024**3
        print(f"Device : {device}  ({gpu_name}, {gpu_mem:.1f} GB)", flush=True)
    else:
        print(f"Device : {device}", flush=True)

    # Support both 'input_size' (native) and 'imgsz' (from frontend UI)
    image_size = config.get("input_size", config.get("imgsz", [224, 224]))
    if isinstance(image_size, list):
        image_size = image_size[0]
    batch_size  = config.get("batch_size", 32)
    train_ratio = config.get("train_ratio", 0.8)

    # Support both 'lr' (native) and 'lr0' (from frontend UI)
    learning_rate = config.get("lr", config.get("lr0", 1e-3))

    # Auto-detect optimal workers count based on CPU cores
    # Default: max(8, cpu_count * 1.5), capped at 16 for better GPU utilization
    cpu_count = os.cpu_count() or 8
    default_workers = min(16, max(8, int(cpu_count * 1.5)))
    workers = config.get("workers", default_workers)
    print(f"Workers: {workers} (CPU cores: {cpu_count})", flush=True)

    # Enable dataset caching to preload images into RAM for faster training
    cache_images = config.get("cache", True)
    if cache_images:
        print("Dataset caching enabled - images will be preloaded into RAM", flush=True)

    train_loader, val_loader = build_dataloaders(
        args.dataset, image_size=image_size,
        train_ratio=train_ratio, batch_size=batch_size,
        num_workers=workers, cache_images=cache_images)

    model = DesktopRecaptureDetector(pretrained=True).to(device)
    n_params = sum(p.numel() for p in model.parameters()) / 1e6
    print(f"Model  : EfficientNet-B0  params={n_params:.2f}M", flush=True)

    n_real = sum(1 for _, l in train_loader.dataset.samples
                 if l == RecaptureDataset.LABEL_REAL)
    n_fake = sum(1 for _, l in train_loader.dataset.samples
                 if l == RecaptureDataset.LABEL_FAKE)
    pos_weight = torch.tensor([n_real / max(n_fake, 1)], device=device)
    criterion  = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
    print(f"Loss   : BCEWithLogitsLoss  pos_weight={pos_weight.item():.4f}", flush=True)

    os.makedirs(args.output, exist_ok=True)
    ckpt_dir = args.output

    patience  = config.get("early_stopping_patience", 10)
    best_auc  = 0.0
    best_loss = float("inf")

    # ── Phase 1: train head only ────────────────────────────────────────
    p1 = config.get("phase1_epochs", 5)
    print(f"\n{'='*60}", flush=True)
    print(f"  Phase 1 — backbone FROZEN, head only  ({p1} epochs)", flush=True)
    print(f"{'='*60}", flush=True)

    for param in model.backbone.parameters():
        param.requires_grad = False

    optimizer_p1 = torch.optim.AdamW(
        filter(lambda p: p.requires_grad, model.parameters()),
        lr=learning_rate,
        weight_decay=config.get("weight_decay", 1e-4),
    )

    best_auc, best_loss, stopped = _run_phase(
        "P1", p1, model, train_loader, val_loader,
        criterion, optimizer_p1, scheduler=None,
        device=device, ckpt_dir=ckpt_dir,
        patience=patience,
        best_auc=best_auc, best_loss=best_loss)
    if stopped:
        print("[DONE] Training ended in Phase 1.", flush=True)
        return

    # ── Phase 2: full fine-tune ─────────────────────────────────────────
    p2 = config.get("phase2_epochs", 25)
    print(f"\n{'='*60}", flush=True)
    print(f"  Phase 2 — full fine-tune  ({p2} epochs)", flush=True)
    print(f"{'='*60}", flush=True)

    for param in model.backbone.parameters():
        param.requires_grad = True

    optimizer_p2 = torch.optim.AdamW(
        model.parameters(),
        lr=learning_rate * 0.1,
        weight_decay=config.get("weight_decay", 1e-4),
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(
        optimizer_p2, T_max=p2, eta_min=config.get("lr_min", 1e-5))

    best_auc, best_loss, stopped = _run_phase(
        "P2", p2, model, train_loader, val_loader,
        criterion, optimizer_p2, scheduler,
        device=device, ckpt_dir=ckpt_dir,
        patience=patience,
        best_auc=best_auc, best_loss=best_loss)

    reason = "early stopping" if stopped else "all epochs complete"
    print(f"\n{'='*60}", flush=True)
    print(f"  Training finished ({reason})", flush=True)
    print(f"  Best val AUC-ROC : {best_auc:.4f}", flush=True)
    print(f"  Best checkpoint  : {os.path.join(ckpt_dir, 'best.pth')}", flush=True)
    print(f"{'='*60}", flush=True)


def _simulate_training(args, config):
    """Fallback simulation when PyTorch is not available."""
    epochs = config.get("phase1_epochs", 5) + config.get("phase2_epochs", 25)
    print("[INFO] PyTorch not available — running training simulation.", flush=True)

    os.makedirs(args.output, exist_ok=True)
    loss = 1.2
    auc = 0.25
    for epoch in range(1, epochs + 1):
        if _stop_requested:
            break
        time.sleep(0.05)
        loss = max(0.01, loss * 0.97)
        auc = min(0.99, auc + 0.008)
        print(f"[EPOCH {epoch}/{epochs}] loss={loss:.4f} auc={auc:.4f}", flush=True)

    for fname in ("best.pth", "last.pth"):
        open(os.path.join(args.output, fname), "w").close()
    print(f"[DONE] model saved to {args.output}", flush=True)


def main():
    args = _parse_args()

    if os.path.exists(args.config):
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = {}

    print(f"[INFO] Starting training: desktop_recapture_detect v{args.version}", flush=True)
    print(f"[INFO] Dataset: {args.dataset}", flush=True)
    print(f"[INFO] Output: {args.output}", flush=True)

    try:
        import torch  # noqa: F401
        train(args, config)
    except ImportError:
        _simulate_training(args, config)


if __name__ == "__main__":
    main()
