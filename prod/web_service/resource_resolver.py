"""Resource path resolver — mountpoint > built-in priority logic.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import json
import os


# Paths injected at container start via env vars
MOUNT_ROOT   = os.getenv("MOUNT_ROOT",   "/mnt/ai_platform")
BUILTIN_ROOT = os.getenv("BUILTIN_ROOT", "/app")

# License file path
LICENSE_PATH = os.getenv("AI_LICENSE_PATH",
                          os.path.join(MOUNT_ROOT, "licenses", "license.bin"))

# Public key path for license signature verification
PUBKEY_PATH = os.getenv("AI_PUBKEY_PATH",
                         os.path.join(MOUNT_ROOT, "licenses", "pubkey.pem"))

# Trusted public key SHA-256 fingerprint (hex, 64 chars).
# Set via env var at image build time or in docker-compose.
# When set, _verify_license_signature() will reject any pubkey.pem
# whose SHA-256 does not match — preventing key-pair forgery attacks.
TRUSTED_PUBKEY_SHA256 = os.getenv("TRUSTED_PUBKEY_SHA256", "")


def resolve_model_dir(capability: str) -> str | None:
    """Return model 'current' dir — mount takes priority over built-in."""
    for base in (MOUNT_ROOT, BUILTIN_ROOT):
        path = os.path.join(base, "models", capability, "current")
        if os.path.isdir(path) and os.path.exists(os.path.join(path, "manifest.json")):
            return path
    return None


def resolve_lib_path(capability: str) -> str | None:
    """Return path to libcapability.so — mount takes priority over built-in."""
    for base in (MOUNT_ROOT, BUILTIN_ROOT):
        path = os.path.join(base, "libs", f"lib{capability}.so")
        if os.path.exists(path):
            return path
    return None


def list_available_capabilities() -> list[dict]:
    """Scan models directories (mount + built-in) and return capability metadata."""
    seen: set[str] = set()
    results: list[dict] = []

    for base in (MOUNT_ROOT, BUILTIN_ROOT):
        models_root = os.path.join(base, "models")
        if not os.path.isdir(models_root):
            continue
        for cap in sorted(os.listdir(models_root)):
            if cap in seen:
                continue
            model_dir = os.path.join(models_root, cap, "current")
            manifest_path = os.path.join(model_dir, "manifest.json")
            if not os.path.isdir(model_dir) or not os.path.exists(manifest_path):
                continue
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:
                manifest = {}
            seen.add(cap)
            results.append({
                "capability":    cap,
                "version":       manifest.get("model_version", "unknown"),
                "model_dir":     model_dir,
                "source":        "mount" if base == MOUNT_ROOT else "builtin",
                "manifest":      manifest,
            })

    return results
