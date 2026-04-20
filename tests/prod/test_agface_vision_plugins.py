from __future__ import annotations

import ctypes
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

PLUGINS = {
    "agface_barehead": "AGFACE_BAREHEAD_SO_PATH",
    "agface_fake_photo": "AGFACE_FAKE_PHOTO_SO_PATH",
    "agface_face_property": "AGFACE_FACE_PROPERTY_SO_PATH",
}


def _find_plugin_so(name: str, env_var: str) -> Path | None:
    override = os.environ.get(env_var, "").strip()
    if override:
        p = Path(override)
        return p if p.is_file() else None

    repo_root = Path(__file__).resolve().parents[2]
    candidates = [
        repo_root / "cpp" / "build" / "lib" / f"lib{name}.so",
        repo_root / "build" / "cpp" / "lib" / f"lib{name}.so",
        Path(f"/mnt/ai_platform/libs/{name}/current/lib/lib{name}.so"),
        Path(f"/app/libs/{name}/lib/lib{name}.so"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def _load_abi(so_path: Path) -> ctypes.CDLL:
    lib = ctypes.CDLL(str(so_path))
    lib.AiGetAbiVersion.restype = ctypes.c_int32
    lib.AiGetAbiVersion.argtypes = []
    lib.AiCreate.restype = ctypes.c_void_p
    lib.AiCreate.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    lib.AiDestroy.restype = None
    lib.AiDestroy.argtypes = [ctypes.c_void_p]
    lib.AiGetInfo.restype = ctypes.c_int32
    lib.AiGetInfo.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int32]
    return lib


@unittest.skipUnless(sys.platform.startswith("linux"), "agface vision SOs are built for Linux only")
class AgfaceVisionPluginAbiTests(unittest.TestCase):

    def setUp(self) -> None:
        self.pairs = []
        for name, env in PLUGINS.items():
            so_path = _find_plugin_so(name, env)
            if so_path is not None:
                self.pairs.append((name, _load_abi(so_path)))
        if not self.pairs:
            self.skipTest("no agface vision plugin SOs found")

    def test_abi_version(self) -> None:
        for name, lib in self.pairs:
            with self.subTest(plugin=name):
                self.assertEqual(lib.AiGetAbiVersion(), 10000)

    def test_create_with_null_model_dir(self) -> None:
        for name, lib in self.pairs:
            with self.subTest(plugin=name):
                self.assertIsNone(lib.AiCreate(None, None))
                self.assertIsNone(lib.AiCreate(b"", None))

    def test_create_with_bogus_manifest(self) -> None:
        for name, lib in self.pairs:
            with self.subTest(plugin=name):
                with tempfile.TemporaryDirectory() as tmp:
                    (Path(tmp) / "manifest.json").write_text(
                        json.dumps({"name": name, "backend": "ncnn"}),
                        encoding="utf-8",
                    )
                    handle = lib.AiCreate(tmp.encode("utf-8"), None)
                    self.assertIsNone(handle)

    def test_get_info_on_null_handle(self) -> None:
        for name, lib in self.pairs:
            with self.subTest(plugin=name):
                rc = lib.AiGetInfo(None, None, 0)
                self.assertLess(rc, 0)


if __name__ == "__main__":
    unittest.main()
