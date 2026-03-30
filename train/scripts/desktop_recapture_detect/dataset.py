"""PyTorch Dataset and DataLoader builder for real/fake binary classification.

Labels: 0 = real portrait, 1 = fake (desktop screenshot)

Migrated from LeeYou/recapture_detect (dev branch) for ai_platform integration.
"""

import random
from pathlib import Path
from typing import Dict, List, Tuple

import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import transforms

IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD  = [0.229, 0.224, 0.225]

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


class RecaptureDataset(Dataset):
    LABEL_REAL = 0
    LABEL_FAKE = 1

    def __init__(self, samples: List[Tuple[str, int]], transform=None):
        self.samples   = samples   # [(path_str, label_int), ...]
        self.transform = transform

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int):
        path, label = self.samples[idx]
        img = Image.open(path).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, torch.tensor(label, dtype=torch.float32)


def _infer_group_id(path: Path, label: int) -> str:
    """Infer source identity to avoid train/val leakage.

    - Real image: group by its stem.
    - Auto-generated fake: names are like <real_stem>_fake_<mode>_<v>.jpg,
      so group by the prefix before '_fake_'.
    - Manual fake: group by filename stem itself.
    """
    stem = path.stem
    if label == RecaptureDataset.LABEL_REAL:
        return f"real:{stem}"
    if "_fake_" in stem:
        return f"src:{stem.split('_fake_')[0]}"
    return f"fake:{stem}"


def collect_samples(dataset_root: str, real_dir: str = "real",
                    fake_dir: str = "fake") -> List[Tuple[str, int]]:
    root    = Path(dataset_root)
    samples = []
    for p in (root / real_dir).iterdir():
        if p.suffix.lower() in IMAGE_EXTS:
            samples.append((str(p), RecaptureDataset.LABEL_REAL))
    for p in (root / fake_dir).iterdir():
        if p.suffix.lower() in IMAGE_EXTS:
            samples.append((str(p), RecaptureDataset.LABEL_FAKE))
    return samples


def group_split_samples(samples: List[Tuple[str, int]], train_ratio: float,
                        seed: int = 42) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]:
    grouped: Dict[str, List[Tuple[str, int]]] = {}
    for path_str, label in samples:
        group_id = _infer_group_id(Path(path_str), label)
        grouped.setdefault(group_id, []).append((path_str, label))

    group_ids = list(grouped.keys())
    rng = random.Random(seed)
    rng.shuffle(group_ids)

    n_train_groups = int(len(group_ids) * train_ratio)
    train_group_ids = set(group_ids[:n_train_groups])

    train_samples, val_samples = [], []
    for gid, group_samples in grouped.items():
        if gid in train_group_ids:
            train_samples.extend(group_samples)
        else:
            val_samples.extend(group_samples)

    rng.shuffle(train_samples)
    rng.shuffle(val_samples)
    return train_samples, val_samples


def build_dataloaders(dataset_root: str, image_size: int = 224,
                      train_ratio: float = 0.8, batch_size: int = 32,
                      real_dir: str = "real", fake_dir: str = "fake",
                      num_workers: int = 0) -> Tuple[DataLoader, DataLoader]:
    """Build train and val dataloaders from a dataset directory."""

    # Docker containers with small /dev/shm frequently crash with bus errors
    if num_workers > 0:
        try:
            shm_stats = Path("/dev/shm").stat().st_size
            if shm_stats < 1024 * 1024 * 1024:
                print("[WARN] /dev/shm appears small; forcing num_workers=0")
                num_workers = 0
        except Exception:
            pass

    persistent_workers = num_workers > 0

    samples = collect_samples(dataset_root, real_dir, fake_dir)
    train_samples, val_samples = group_split_samples(samples, train_ratio, seed=42)

    train_tf = transforms.Compose([
        transforms.RandomResizedCrop(image_size, scale=(0.7, 1.0)),
        transforms.RandomHorizontalFlip(),
        transforms.RandomRotation(10),
        transforms.ColorJitter(brightness=0.3, contrast=0.3,
                               saturation=0.2, hue=0.05),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    val_tf = transforms.Compose([
        transforms.Resize((image_size, image_size)),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])

    train_ds = RecaptureDataset(train_samples, transform=train_tf)
    val_ds   = RecaptureDataset(val_samples,   transform=val_tf)

    loader_kwargs = dict(
        batch_size=batch_size,
        num_workers=num_workers,
        pin_memory=True,
        persistent_workers=persistent_workers,
    )

    train_loader = DataLoader(train_ds, shuffle=True, **loader_kwargs)
    val_loader   = DataLoader(val_ds, shuffle=False, **loader_kwargs)

    real_tr = sum(1 for _, l in train_samples if l == RecaptureDataset.LABEL_REAL)
    fake_tr = sum(1 for _, l in train_samples if l == RecaptureDataset.LABEL_FAKE)
    real_vl = sum(1 for _, l in val_samples   if l == RecaptureDataset.LABEL_REAL)
    fake_vl = sum(1 for _, l in val_samples   if l == RecaptureDataset.LABEL_FAKE)
    print(f"Dataset  total={len(samples)}  train={len(train_ds)} val={len(val_ds)}")
    print(f"  Train  real={real_tr}  fake={fake_tr}")
    print(f"  Val    real={real_vl}  fake={fake_vl}")
    print("  Split  group-aware by source identity (reduces leakage)")

    return train_loader, val_loader
