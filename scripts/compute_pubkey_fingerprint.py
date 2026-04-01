#!/usr/bin/env python3
"""Compute SHA-256 fingerprint of a PEM public key file.

The resulting hex string is used as the TRUSTED_PUBKEY_SHA256 compile-time
constant when building libai_runtime.so for a specific customer.

Usage:
    python3 scripts/compute_pubkey_fingerprint.py /path/to/pubkey.pem

Output:
    Prints the lowercase hex SHA-256 hash to stdout (64 characters).

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import hashlib
import sys


def compute_fingerprint(pem_path: str) -> str:
    """Read a PEM file and return its SHA-256 hex digest."""
    with open(pem_path, "rb") as f:
        data = f.read()
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <pubkey.pem>", file=sys.stderr)
        sys.exit(1)

    pem_path = sys.argv[1]
    try:
        fingerprint = compute_fingerprint(pem_path)
    except FileNotFoundError:
        print(f"Error: file not found: {pem_path}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    print(fingerprint)


if __name__ == "__main__":
    main()
