import asyncio
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException
from starlette.datastructures import UploadFile


PROD_DIR = Path(__file__).resolve().parents[2] / "prod" / "web_service"
if str(PROD_DIR) not in sys.path:
    sys.path.insert(0, str(PROD_DIR))
os.environ.setdefault("LOG_DIR", "/tmp/ai_platform_test_logs")

import main as prod_main  # noqa: E402
import pipeline_engine  # noqa: E402
import resource_resolver  # noqa: E402


class _FakeRuntime:
    def get_capabilities(self):
        return [{"name": "face_detect", "version": "v1.2.3", "status": "loaded"}]

    def get_license_status(self):
        return {"status": "active", "capabilities": ["face_detect"]}

    def acquire(self, capability, timeout_ms=30000):
        return object()

    def infer(self, handle, image_data, width, height, channels):
        return {"error_code": 0, "result": {"face_detected": True, "count": 1}}

    def release(self, handle):
        return None

    def reload(self, capability):
        return 0


class _FakeImage:
    shape = (2, 2, 3)

    def tobytes(self):
        return b"\x00" * 12


class ProdMainTests(unittest.TestCase):
    def setUp(self):
        self.fake_runtime = _FakeRuntime()
        self.tempdir = tempfile.TemporaryDirectory()
        self.model_dir = Path(self.tempdir.name) / "models" / "face_detect" / "current"
        self.model_dir.mkdir(parents=True, exist_ok=True)
        (self.model_dir / "manifest.json").write_text(
            json.dumps({"capability": "face_detect", "model_version": "v1.2.3"}),
            encoding="utf-8",
        )
        self.pipeline_dir = Path(self.tempdir.name) / "pipelines"
        self.pipeline_dir.mkdir(parents=True, exist_ok=True)

        self.original_pipeline_dir = pipeline_engine.PIPELINE_DIR
        pipeline_engine.PIPELINE_DIR = str(self.pipeline_dir)
        self.original_max_upload = prod_main.MAX_UPLOAD_BYTES
        self.original_timeout = prod_main.INFER_CONCURRENCY_TIMEOUT_SECONDS
        self.original_semaphore = prod_main._infer_request_semaphore

        resource_resolver.resolve_model_dir = lambda capability: str(self.model_dir)
        prod_main._init_runtime = lambda: True
        prod_main.destroy_runtime = lambda: None
        prod_main.get_runtime = lambda: self.fake_runtime
        prod_main._check_license = lambda capability: None
        prod_main._decode_image = lambda data: _FakeImage()

    def tearDown(self):
        pipeline_engine.PIPELINE_DIR = self.original_pipeline_dir
        prod_main.MAX_UPLOAD_BYTES = self.original_max_upload
        prod_main.INFER_CONCURRENCY_TIMEOUT_SECONDS = self.original_timeout
        prod_main._infer_request_semaphore = self.original_semaphore
        self.tempdir.cleanup()

    def test_health_endpoint_uses_runtime_status(self):
        body = prod_main.health()
        self.assertEqual(body["license"]["status"], "active")
        self.assertEqual(body["capabilities"][0]["capability"], "face_detect")

    def test_infer_endpoint_rejects_large_payload(self):
        prod_main.MAX_UPLOAD_BYTES = 1
        upload = UploadFile(file=io.BytesIO(b"12"), filename="x.bin")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(prod_main.infer("face_detect", upload))
        self.assertEqual(ctx.exception.status_code, 413)

    def test_infer_endpoint_returns_busy_when_concurrency_limit_hit(self):
        prod_main.INFER_CONCURRENCY_TIMEOUT_SECONDS = 1
        prod_main._infer_request_semaphore = asyncio.Semaphore(0)
        upload = UploadFile(file=io.BytesIO(b"ok"), filename="x.bin")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(prod_main.infer("face_detect", upload))
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail["code"], 3002)

    def test_pipeline_validate_endpoint_returns_valid(self):
        pipeline = {
            "pipeline_id": "pipe_ok",
            "name": "Pipeline OK",
            "steps": [{"step_id": "s1", "capability": "face_detect"}],
        }
        (self.pipeline_dir / "pipe_ok.json").write_text(json.dumps(pipeline), encoding="utf-8")
        body = prod_main.validate_pipeline_endpoint("pipe_ok")
        self.assertTrue(body["valid"])
        self.assertEqual(body["errors"], [])


if __name__ == "__main__":
    unittest.main()
