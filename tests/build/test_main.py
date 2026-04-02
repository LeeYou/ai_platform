import os
import sys
import tempfile
import unittest
from pathlib import Path

import httpx


BUILD_DIR = Path(__file__).resolve().parents[2] / "build" / "backend"
if str(BUILD_DIR) not in sys.path:
    sys.path.insert(0, str(BUILD_DIR))
os.environ.setdefault("LOG_DIR", "/tmp/ai_platform_build_test_logs")

import main as build_main  # noqa: E402


class _FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.request = httpx.Request("GET", "http://train:8001")

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"status={self.status_code}",
                request=self.request,
                response=httpx.Response(self.status_code, request=self.request),
            )


class BuildCapabilityDiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_cpp_source_dir = build_main.CPP_SOURCE_DIR
        self.original_models_root = build_main.MODELS_ROOT
        self.original_async_client = build_main.httpx.AsyncClient

        cpp_root = Path(self.tempdir.name) / "cpp" / "capabilities"
        cpp_root.mkdir(parents=True, exist_ok=True)
        (cpp_root / "face_detect").mkdir()
        (cpp_root / "desktop_recapture_detect").mkdir()

        models_root = Path(self.tempdir.name) / "models"
        models_root.mkdir(parents=True, exist_ok=True)

        build_main.CPP_SOURCE_DIR = str(Path(self.tempdir.name) / "cpp")
        build_main.MODELS_ROOT = str(models_root)

    def tearDown(self):
        build_main.CPP_SOURCE_DIR = self.original_cpp_source_dir
        build_main.MODELS_ROOT = self.original_models_root
        build_main.httpx.AsyncClient = self.original_async_client
        self.tempdir.cleanup()

    async def test_capability_diagnostics_uses_trailing_slash_fallback(self):
        calls = []

        class _FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, follow_redirects=False):
                calls.append((url, follow_redirects))
                if url.endswith("/api/v1/capabilities/"):
                    return _FakeResponse(200, [{"name": "face_detect"}])
                return _FakeResponse(404, None)

        build_main.httpx.AsyncClient = _FakeAsyncClient

        body = await build_main.capability_diagnostics()

        self.assertTrue(body["train_service_reachable"])
        self.assertEqual(body["train_capabilities"], ["face_detect"])
        self.assertEqual(body["available_capabilities"], ["face_detect"])
        self.assertEqual(calls[0], ("http://train:8001/api/v1/capabilities/", True))

    async def test_capability_diagnostics_retries_without_trailing_slash(self):
        calls = []

        class _FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def get(self, url, follow_redirects=False):
                calls.append(url)
                if url.endswith("/api/v1/capabilities/"):
                    return _FakeResponse(404, None)
                return _FakeResponse(200, [{"name": "desktop_recapture_detect"}])

        build_main.httpx.AsyncClient = _FakeAsyncClient

        body = await build_main.capability_diagnostics()

        self.assertTrue(body["train_service_reachable"])
        self.assertEqual(
            calls,
            [
                "http://train:8001/api/v1/capabilities/",
                "http://train:8001/api/v1/capabilities",
            ],
        )
        self.assertEqual(body["available_capabilities"], ["desktop_recapture_detect"])
