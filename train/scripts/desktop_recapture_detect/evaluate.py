"""Evaluate a saved desktop_recapture_detect checkpoint on the validation split.

Prints: accuracy, precision, recall, F1, AUC-ROC, and confusion matrix.

Usage (inside the train container):
    python evaluate.py --config config.json \\
                       --dataset /workspace/datasets/desktop_recapture_detect/ \\
                       --checkpoint /workspace/models/desktop_recapture_detect/v1.0.0/best.pth

Migrated from LeeYou/recapture_detect (dev branch) for ai_platform integration.
"""

import argparse
import json
import os
import sys

import numpy as np
import torch
from torch.utils.data import DataLoader
from torchvision import transforms
from tqdm import tqdm

from dataset import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    RecaptureDataset,
    collect_samples,
    group_split_samples,
)
from model import DesktopRecaptureDetector


def _load_checkpoint(path, device):
    try:
        return torch.load(path, map_location=device, weights_only=True)
    except Exception:
        return torch.load(path, map_location=device, weights_only=False)


def _parse_args():
    parser = argparse.ArgumentParser(description="Evaluate desktop_recapture_detect model")
    parser.add_argument("--config", default="config.json")
    parser.add_argument(
        "--dataset",
        default="/workspace/datasets/desktop_recapture_detect/",
        help="Dataset root (must contain real/ and fake/)",
    )
    parser.add_argument("--checkpoint", default=None, help="Path to .pth checkpoint")
    parser.add_argument("--threshold", type=float, default=0.5)
    return parser.parse_args()


def evaluate(args, config):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    checkpoint = args.checkpoint
    if not checkpoint:
        # Try output dir
        for name in ("best.pth", "last.pth"):
            candidate = os.path.join(args.dataset, "..", "models", name)
            if os.path.isfile(candidate):
                checkpoint = candidate
                break
    if not checkpoint or not os.path.isfile(checkpoint):
        print("[ERROR] No checkpoint found. Provide --checkpoint.", file=sys.stderr)
        sys.exit(1)

    model = DesktopRecaptureDetector(pretrained=False).to(device)
    ckpt  = _load_checkpoint(checkpoint, device)
    model.load_state_dict(ckpt["model_state"])
    model.eval()

    print(f"Checkpoint : {checkpoint}")
    print(f"  epoch    : {ckpt.get('epoch', 'N/A')}")
    print(f"  val_auc  : {ckpt.get('val_auc', 'N/A')}")
    print(f"Threshold  : {args.threshold}")

    image_size = config.get("input_size", [224, 224])
    if isinstance(image_size, list):
        image_size = image_size[0]
    train_ratio = config.get("train_ratio", 0.8)

    samples = collect_samples(args.dataset)
    _, val_samples = group_split_samples(samples, train_ratio, seed=42)

    val_tf = transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    val_ds     = RecaptureDataset(val_samples, transform=val_tf)
    val_loader = DataLoader(val_ds, batch_size=32, shuffle=False, pin_memory=True)

    all_probs, all_labels = [], []
    with torch.no_grad():
        for imgs, labels in tqdm(val_loader, desc="Evaluating"):
            logits = model(imgs.to(device))
            probs  = torch.sigmoid(logits).cpu().numpy()
            all_probs.extend(probs)
            all_labels.extend(labels.numpy())

    probs  = np.array(all_probs)
    labels = np.array(all_labels)
    preds  = (probs >= args.threshold).astype(int)

    from sklearn.metrics import (
        accuracy_score, classification_report, confusion_matrix,
        f1_score, precision_score, recall_score, roc_auc_score,
    )

    print(f"\n{'='*55}")
    print(f"Samples  : {len(labels)}  "
          f"(real={int((labels==0).sum())}  fake={int((labels==1).sum())})")
    print(f"Accuracy : {accuracy_score(labels, preds):.4f}")
    print(f"Precision: {precision_score(labels, preds):.4f}")
    print(f"Recall   : {recall_score(labels, preds):.4f}")
    print(f"F1 Score : {f1_score(labels, preds):.4f}")
    print(f"AUC-ROC  : {roc_auc_score(labels, probs):.4f}")
    print(f"\nConfusion Matrix  (rows=actual  cols=predicted)")
    print(f"  Labels: 0=real  1=fake")
    print(confusion_matrix(labels, preds))
    print(f"\nClassification Report:")
    print(classification_report(labels, preds, target_names=["real", "fake"]))


def main():
    args = _parse_args()

    if os.path.exists(args.config):
        with open(args.config, encoding="utf-8") as f:
            config = json.load(f)
    else:
        config = {}

    evaluate(args, config)


if __name__ == "__main__":
    main()
