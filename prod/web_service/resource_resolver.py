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
    """Return path to libcapability.so — mount takes priority over built-in.

    Supports two directory structures:
    1. Flat: /libs/lib<capability>.so
    2. Nested (from builder): /libs/linux_x86_64/<capability>/lib/lib<capability>.so
    """
    for base in (MOUNT_ROOT, BUILTIN_ROOT):
        # Try nested structure first (from ai-builder output)
        nested_path = os.path.join(base, "libs", "linux_x86_64", capability, "lib", f"lib{capability}.so")
        if os.path.exists(nested_path):
            return nested_path

        # Try flat structure
        flat_path = os.path.join(base, "libs", f"lib{capability}.so")
        if os.path.exists(flat_path):
            return flat_path

    return None


def resolve_runtime_so_path() -> str | None:
    """Return path to libai_runtime.so — mount takes priority over built-in.

    Supports two directory structures:
    1. Flat: /libs/libai_runtime.so
    2. Nested (from builder): /libs/linux_x86_64/<capability>/lib/libai_runtime.so
    """
    for base in (MOUNT_ROOT, BUILTIN_ROOT):
        # Try to find libai_runtime.so in any capability's lib directory
        # (builder outputs libai_runtime.so alongside each capability SO)
        libs_x86_64 = os.path.join(base, "libs", "linux_x86_64")
        if os.path.isdir(libs_x86_64):
            for cap_dir in os.listdir(libs_x86_64):
                nested_path = os.path.join(libs_x86_64, cap_dir, "lib", "libai_runtime.so")
                if os.path.exists(nested_path):
                    return nested_path

        # Try flat structure
        flat_path = os.path.join(base, "libs", "libai_runtime.so")
        if os.path.exists(flat_path):
            return flat_path

    return None


def resolve_libs_dir() -> str:
    """Return libs directory path — mount takes priority over built-in.

    For nested structure, returns the linux_x86_64 directory containing capability subdirs.
    For flat structure, returns the libs directory directly.
    """
    for base in (MOUNT_ROOT, BUILTIN_ROOT):
        # Try nested structure first (builder output)
        nested_libs = os.path.join(base, "libs", "linux_x86_64")
        if os.path.isdir(nested_libs):
            return nested_libs

        # Try flat structure
        flat_libs = os.path.join(base, "libs")
        if os.path.isdir(flat_libs):
            return flat_libs

    # Fallback to built-in flat structure even if directory doesn't exist
    return os.path.join(BUILTIN_ROOT, "libs")


def resolve_models_dir() -> str:
    """Return models directory path — mount takes priority over built-in."""
    for base in (MOUNT_ROOT, BUILTIN_ROOT):
        models_dir = os.path.join(base, "models")
        if os.path.isdir(models_dir):
            return models_dir
    # Fallback to built-in even if directory doesn't exist
    return os.path.join(BUILTIN_ROOT, "models")


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
