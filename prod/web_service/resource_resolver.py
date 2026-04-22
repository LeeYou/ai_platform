"""Resource path resolver — mountpoint > built-in priority logic.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import hashlib
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


def _manifest_version(manifest: dict) -> str:
    version = manifest.get("model_version") or manifest.get("version") or "unknown"
    return str(version).strip() or "unknown"


def resolve_model_dir(capability: str) -> str | None:
    """Return model 'current' dir — mount takes priority over built-in."""
    for base in (MOUNT_ROOT, BUILTIN_ROOT):
        path = os.path.join(base, "models", capability, "current")
        if os.path.isdir(path) and os.path.exists(os.path.join(path, "manifest.json")):
            return path
    return None


def resolve_lib_path(capability: str) -> str | None:
    """Return path to libcapability.so — mount takes priority over built-in.

    Supports four directory structures:
    1. Flat: /libs/lib<capability>.so
    2. Nested (from builder): /libs/linux_x86_64/<capability>/lib/lib<capability>.so
    3. Flattened mount (docker-compose.prod.yml): /libs/<capability>/lib/lib<capability>.so
    4. Current symlink/dir: /libs/<capability>/current/lib/lib<capability>.so
    """
    for base in (MOUNT_ROOT, BUILTIN_ROOT):
        # Try nested structure first (from ai-builder output)
        nested_path = os.path.join(base, "libs", "linux_x86_64", capability, "lib", f"lib{capability}.so")
        if os.path.exists(nested_path):
            return nested_path

        # Try flattened mount structure (linux_x86_64 already at mount root)
        flattened_path = os.path.join(base, "libs", capability, "lib", f"lib{capability}.so")
        if os.path.exists(flattened_path):
            return flattened_path

        current_path = os.path.join(base, "libs", capability, "current", "lib", f"lib{capability}.so")
        if os.path.exists(current_path):
            return current_path

        # Try flat structure
        flat_path = os.path.join(base, "libs", f"lib{capability}.so")
        if os.path.exists(flat_path):
            return flat_path

    return None


def _dedupe_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        normalized = os.path.normpath(path)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(path)
    return result


def _iter_runtime_so_candidates_for_base(base: str) -> list[str]:
    candidates: list[str] = []

    nested_root = os.path.join(base, "libs", "linux_x86_64")
    if os.path.isdir(nested_root):
        for entry in sorted(os.listdir(nested_root)):
            entry_path = os.path.join(nested_root, entry)
            if not os.path.isdir(entry_path):
                continue
            current_path = os.path.join(entry_path, "current", "lib", "libai_runtime.so")
            direct_path = os.path.join(entry_path, "lib", "libai_runtime.so")
            if os.path.exists(current_path):
                candidates.append(current_path)
            if os.path.exists(direct_path):
                candidates.append(direct_path)

    libs_root = os.path.join(base, "libs")
    if os.path.isdir(libs_root):
        for entry in sorted(os.listdir(libs_root)):
            if entry == "linux_x86_64":
                continue
            entry_path = os.path.join(libs_root, entry)
            if not os.path.isdir(entry_path):
                continue
            current_path = os.path.join(entry_path, "current", "lib", "libai_runtime.so")
            direct_path = os.path.join(entry_path, "lib", "libai_runtime.so")
            if os.path.exists(current_path):
                candidates.append(current_path)
            if os.path.exists(direct_path):
                candidates.append(direct_path)

        flat_path = os.path.join(libs_root, "libai_runtime.so")
        if os.path.exists(flat_path):
            candidates.append(flat_path)

    return _dedupe_paths(candidates)


def list_runtime_so_candidates() -> list[str]:
    env_path = os.getenv("AI_RUNTIME_SO_PATH", "").strip()
    if env_path and os.path.exists(env_path):
        return [env_path]

    candidates: list[str] = []
    for base in (MOUNT_ROOT, BUILTIN_ROOT):
        candidates.extend(_iter_runtime_so_candidates_for_base(base))
    return _dedupe_paths(candidates)


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_runtime_so_path() -> str | None:
    """Return path to libai_runtime.so — mount takes priority over built-in.

    Supports four directory structures:
    1. Flat: /libs/libai_runtime.so
    2. Nested (from builder): /libs/linux_x86_64/<capability>/lib/libai_runtime.so
    3. Flattened mount (docker-compose.prod.yml): /libs/<capability>/lib/libai_runtime.so
    4. Current symlink/dir: /libs/<capability>/current/lib/libai_runtime.so
    """
    candidates = list_runtime_so_candidates()
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    hash_counts: dict[str, int] = {}
    candidate_hashes: dict[str, str] = {}
    for path in candidates:
        try:
            file_hash = _sha256_file(path)
        except OSError:
            file_hash = f"missing:{path}"
        candidate_hashes[path] = file_hash
        hash_counts[file_hash] = hash_counts.get(file_hash, 0) + 1

    def _score(path: str) -> tuple[int, int, float, str]:
        normalized = os.path.normpath(path)
        current_bonus = 1 if f"{os.sep}current{os.sep}" in normalized else 0
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            mtime = 0.0
        return (
            hash_counts.get(candidate_hashes[path], 0),
            current_bonus,
            mtime,
            normalized,
        )

    return sorted(candidates, key=_score, reverse=True)[0]


def resolve_libs_dir() -> str:
    """Return libs directory path — mount takes priority over built-in.

    For nested structure, returns the linux_x86_64 directory containing capability subdirs.
    For flattened mount structure, returns the libs directory (which already contains capability subdirs).
    For flat structure, returns the libs directory directly.
    """
    for base in (MOUNT_ROOT, BUILTIN_ROOT):
        # Try nested structure first (builder output: libs/linux_x86_64/<capability>/)
        nested_libs = os.path.join(base, "libs", "linux_x86_64")
        if os.path.isdir(nested_libs):
            return nested_libs

        # For flattened mount or flat structure, return libs directory
        # (docker-compose.prod.yml mounts linux_x86_64 directly to /mnt/ai_platform/libs)
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
            real_model_dir = os.path.realpath(model_dir)
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    manifest = json.load(f)
            except Exception:
                manifest = {}
            preprocess = {}
            preprocess_path = os.path.join(model_dir, "preprocess.json")
            try:
                with open(preprocess_path, encoding="utf-8") as f:
                    preprocess = json.load(f)
            except Exception:
                preprocess = {}
            seen.add(cap)
            results.append({
                "capability":    cap,
                "version":       _manifest_version(manifest),
                "model_dir":     model_dir,
                "real_model_dir": real_model_dir,
                "source":        "mount" if base == MOUNT_ROOT else "builtin",
                "manifest":      manifest,
                "preprocess":    preprocess,
            })

    return results
