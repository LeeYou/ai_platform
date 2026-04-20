"""Smoke test for the `agface_face_detect` capability plugin.

What this test covers (no HTTP, no runtime layer — direct ctypes to the SO):
  1. `AiGetAbiVersion()` returns the expected SDK version number.
  2. `AiCreate()` against a synthesized model dir with a minimal manifest.json
     fails gracefully (returns NULL) because the NCNN weights are missing,
     but not by crashing.
  3. `AiGetInfo()` on a NULL handle returns a negative error code.

These assertions can run on the build server without the real NCNN weights or
the NCNN runtime installed in the test environment; they simply verify that
the SO exports the required C ABI symbols with the correct signatures.

When the real migrated model + ncnn runtime is available (prod container), a
separate integration test in `docs/design/agface_migration.md §6.3` covers the
end-to-end inference path.
"""

from __future__ import annotations

import ctypes
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SO_ENV_VAR = "AGFACE_FACE_DETECT_SO_PATH"


def _find_plugin_so() -> Path | None:
    """Locate libagface_face_detect.so, honouring env var and common build paths."""
    override = os.environ.get(SO_ENV_VAR, "").strip()
    if override:
        p = Path(override)
        return p if p.is_file() else None

    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "cpp" / "build" / "lib" / "libagface_face_detect.so",
        repo_root / "build" / "cpp" / "lib" / "libagface_face_detect.so",
        Path("/mnt/ai_platform/libs/agface_face_detect/current/lib/libagface_face_detect.so"),
        Path("/app/libs/agface_face_detect/lib/libagface_face_detect.so"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


@unittest.skipUnless(sys.platform.startswith("linux"),
                     "agface_face_detect SO is built for Linux only")
class AgfaceFaceDetectPluginTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        so_path = _find_plugin_so()
        if so_path is None:
            raise unittest.SkipTest(
                "libagface_face_detect.so not found. Build with "
                "-DBUILD_CAP_AGFACE_FACE_DETECT=ON or set "
                f"{SO_ENV_VAR}=/path/to/libagface_face_detect.so"
            )
        cls.lib = ctypes.CDLL(str(so_path))

        cls.lib.AiGetAbiVersion.restype  = ctypes.c_int32
        cls.lib.AiGetAbiVersion.argtypes = []

        cls.lib.AiCreate.restype  = ctypes.c_void_p
        cls.lib.AiCreate.argtypes = [ctypes.c_char_p, ctypes.c_char_p]

        cls.lib.AiDestroy.restype  = None
        cls.lib.AiDestroy.argtypes = [ctypes.c_void_p]

        cls.lib.AiGetInfo.restype  = ctypes.c_int32
        cls.lib.AiGetInfo.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int32]

    def test_abi_version_matches_sdk(self) -> None:
        """ABI version must equal AI_ABI_VERSION (v1.0.0 → 10000)."""
        self.assertEqual(self.lib.AiGetAbiVersion(), 10000)

    def test_create_fails_without_model_dir(self) -> None:
        """NULL / empty model_dir → AiCreate returns NULL instead of crashing."""
        self.assertIsNone(self.lib.AiCreate(None, None))
        self.assertIsNone(self.lib.AiCreate(b"", None))

    def test_create_fails_on_bogus_manifest(self) -> None:
        """A manifest missing param/bin fields yields NULL gracefully."""
        with tempfile.TemporaryDirectory() as tmp:
            manifest = {
                "name": "agface_face_detect",
                "version": "1.0.0",
                "backend": "ncnn",
                # intentionally missing param_file / bin_file
            }
            (Path(tmp) / "manifest.json").write_text(
                json.dumps(manifest), encoding="utf-8")
            handle = self.lib.AiCreate(tmp.encode("utf-8"), None)
            self.assertIsNone(handle)

    def test_get_info_on_null_handle_returns_negative(self) -> None:
        """AiGetInfo(NULL) must return a negative error code, not segfault."""
        rc = self.lib.AiGetInfo(None, None, 0)
        self.assertLess(rc, 0)


if __name__ == "__main__":
    unittest.main()
