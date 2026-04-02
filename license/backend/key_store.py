"""Server-controlled private key storage helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path


PRIVATE_KEYS_DIR = Path(os.getenv("PRIVATE_KEYS_DIR", "./data/private_keys")).resolve()


def ensure_private_keys_dir() -> Path:
    PRIVATE_KEYS_DIR.mkdir(parents=True, exist_ok=True)
    return PRIVATE_KEYS_DIR


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "_", name).strip("_")
    return slug or "key"


def private_key_path_for(key_pair) -> Path:
    base_dir = ensure_private_keys_dir()
    return base_dir / f"{key_pair.id}_{_slugify(key_pair.name)}.pem"


def write_private_key(key_pair, private_key_pem: str) -> str:
    path = private_key_path_for(key_pair)
    path.write_text(private_key_pem, encoding="utf-8")
    os.chmod(path, 0o600)
    return str(path)


def read_private_key(key_pair) -> str:
    path = private_key_path_for(key_pair)
    return path.read_text(encoding="utf-8")
