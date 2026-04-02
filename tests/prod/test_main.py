import asyncio
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

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


class _FakeABManager:
    def __init__(self):
        self.reload_called = False

    def get_version_for_request(self, capability, session_id=None):
        return "v2.0.0"

    def get_test_info(self, capability):
        return {
            "enabled": True,
            "strategy": "sticky_session",
            "variants": [
                {"version": "v1.2.3", "weight": 80, "weight_pct": 80.0},
                {"version": "v2.0.0", "weight": 20, "weight_pct": 20.0},
            ],
        }

    def list_active_tests(self):
        return {
            "face_detect": {
                "enabled": True,
                "strategy": "sticky_session",
                "variants": [
                    {"version": "v1.2.3", "weight": 80, "weight_pct": 80.0},
                    {"version": "v2.0.0", "weight": 20, "weight_pct": 20.0},
                ],
            }
        }

    def reload(self):
        self.reload_called = True


class _FakeJsonRequest:
    def __init__(self, body=None, headers=None):
        self._body = body or {}
        self.headers = headers or {}

    async def json(self):
        return self._body


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
        self.original_ab_manager = prod_main.ab_manager
        self.original_admin_token = prod_main.ADMIN_TOKEN
        self.original_resolve_model_dir = prod_main.resolve_model_dir
        self.original_resolve_models_dir = prod_main.resolve_models_dir
        self.original_resolve_libs_dir = prod_main.resolve_libs_dir
        self.original_resolve_runtime_so_path = prod_main.resolve_runtime_so_path
        self.original_list_available_capabilities = prod_main.list_available_capabilities
        self.original_resource_resolve_model_dir = resource_resolver.resolve_model_dir
        self.original_exists = prod_main.os.path.exists
        self.original_license_path = prod_main.LICENSE_PATH
        self.original_pubkey_path = prod_main.PUBKEY_PATH
        self.original_runtime_bootstrap = prod_main._init_runtime
        self.original_runtime_init = prod_main.init_runtime
        self.original_get_runtime = prod_main.get_runtime
        self.original_verify_license_signature = prod_main._verify_license_signature
        self.original_check_license = prod_main._check_license
        self.original_infer_for_pipeline = prod_main._infer_for_pipeline
        self.original_subprocess_run = prod_main.subprocess.run
        self.original_ai_pubkey_env = os.environ.get("AI_PUBKEY_PATH")
        self.libs_dir = Path(self.tempdir.name) / "libs" / "linux_x86_64" / "face_detect" / "lib"
        self.libs_dir.mkdir(parents=True, exist_ok=True)
        (self.libs_dir / "libface_detect.so").write_bytes(b"fake")
        (self.libs_dir / "libai_runtime.so").write_bytes(b"fake")

        resource_resolver.resolve_model_dir = lambda capability: str(self.model_dir)
        prod_main.resolve_model_dir = lambda capability: str(self.model_dir)
        prod_main.resolve_models_dir = lambda: str(Path(self.tempdir.name) / "models")
        prod_main.resolve_libs_dir = lambda: str(Path(self.tempdir.name) / "libs")
        prod_main.resolve_runtime_so_path = lambda: str(self.libs_dir / "libai_runtime.so")
        prod_main.list_available_capabilities = lambda: [
            {
                "capability": "face_detect",
                "version": "v1.2.3",
                "model_dir": str(self.model_dir),
                "source": "mount",
            }
        ]
        prod_main._init_runtime = lambda: True
        prod_main.destroy_runtime = lambda: None
        prod_main.get_runtime = lambda: self.fake_runtime
        prod_main._check_license = lambda capability: None
        prod_main._decode_image = lambda data: _FakeImage()
        prod_main.ab_manager = _FakeABManager()
        prod_main.ADMIN_TOKEN = "test-token"
        prod_main.LICENSE_PATH = str(Path(self.tempdir.name) / "license.json")

    def tearDown(self):
        pipeline_engine.PIPELINE_DIR = self.original_pipeline_dir
        prod_main.MAX_UPLOAD_BYTES = self.original_max_upload
        prod_main.INFER_CONCURRENCY_TIMEOUT_SECONDS = self.original_timeout
        prod_main._infer_request_semaphore = self.original_semaphore
        prod_main.ab_manager = self.original_ab_manager
        prod_main.ADMIN_TOKEN = self.original_admin_token
        prod_main.resolve_model_dir = self.original_resolve_model_dir
        prod_main.resolve_models_dir = self.original_resolve_models_dir
        prod_main.resolve_libs_dir = self.original_resolve_libs_dir
        prod_main.resolve_runtime_so_path = self.original_resolve_runtime_so_path
        prod_main.list_available_capabilities = self.original_list_available_capabilities
        resource_resolver.resolve_model_dir = self.original_resource_resolve_model_dir
        prod_main.os.path.exists = self.original_exists
        prod_main.LICENSE_PATH = self.original_license_path
        prod_main.PUBKEY_PATH = self.original_pubkey_path
        prod_main._init_runtime = self.original_runtime_bootstrap
        prod_main.init_runtime = self.original_runtime_init
        prod_main.get_runtime = self.original_get_runtime
        prod_main._verify_license_signature = self.original_verify_license_signature
        prod_main._check_license = self.original_check_license
        prod_main._infer_for_pipeline = self.original_infer_for_pipeline
        prod_main.subprocess.run = self.original_subprocess_run
        prod_main._cleanup_runtime_libs_stage_dir()
        if self.original_ai_pubkey_env is None:
            os.environ.pop("AI_PUBKEY_PATH", None)
        else:
            os.environ["AI_PUBKEY_PATH"] = self.original_ai_pubkey_env
        self.tempdir.cleanup()

    def _write_license(self, **overrides):
        payload = {
            "license_id": "lic-test",
            "valid_from": (datetime.now(prod_main.CST) - timedelta(days=1)).isoformat(),
            "valid_until": (datetime.now(prod_main.CST) + timedelta(days=7)).isoformat(),
            "capabilities": ["face_detect"],
            "signature": "fake-signature",
        }
        payload.update(overrides)
        Path(prod_main.LICENSE_PATH).write_text(json.dumps(payload), encoding="utf-8")
        return payload

    def test_health_endpoint_uses_runtime_status(self):
        body = prod_main.health()
        self.assertEqual(body["license"]["status"], "active")
        self.assertEqual(body["capabilities"][0]["capability"], "face_detect")
        self.assertEqual(body["status"], "healthy")

    def test_health_endpoint_reports_gpu_when_nvidia_device_exists(self):
        prod_main.os.path.exists = lambda path: (
            path == "/dev/nvidia0" or self.original_exists(path)
        )
        body = prod_main.health()
        self.assertTrue(body["gpu_available"])

    def test_health_endpoint_reports_gpu_when_nvidia_smi_succeeds(self):
        prod_main.os.path.exists = lambda path: False
        prod_main.subprocess.run = lambda *args, **kwargs: SimpleNamespace(returncode=0)
        body = prod_main.health()
        self.assertTrue(body["gpu_available"])

    def test_health_endpoint_reports_no_gpu_when_detection_fails(self):
        prod_main.os.path.exists = lambda path: False

        def _raise_file_not_found(*args, **kwargs):
            raise FileNotFoundError("nvidia-smi not found")

        prod_main.subprocess.run = _raise_file_not_found
        body = prod_main.health()
        self.assertFalse(body["gpu_available"])

    def test_prepare_runtime_libs_dir_stages_nested_shared_objects(self):
        source_root = str(Path(self.tempdir.name) / "libs")
        staged_dir = prod_main._prepare_runtime_libs_dir(source_root)

        self.assertNotEqual(staged_dir, source_root)
        self.assertTrue(Path(staged_dir, "libface_detect.so").exists())
        self.assertTrue(Path(staged_dir, "libai_runtime.so").exists())
        self.assertTrue(prod_main._is_shared_library_filename("libface_detect.so.1"))
        self.assertFalse(prod_main._is_shared_library_filename("libface_detect.so.bak"))

    def test_init_runtime_uses_staged_loader_dir_and_sets_pubkey_env(self):
        records = {}
        pubkey_path = Path(self.tempdir.name) / "licenses" / "pubkey.pem"
        pubkey_path.parent.mkdir(parents=True, exist_ok=True)
        pubkey_path.write_text("fake-pubkey", encoding="utf-8")
        prod_main.PUBKEY_PATH = str(pubkey_path)
        prod_main.resolve_libs_dir = lambda: str(Path(self.tempdir.name) / "libs")
        prod_main.init_runtime = (
            lambda runtime_so, libs_dir, models_dir, license_path: records.update({
                "runtime_so": runtime_so,
                "libs_dir": libs_dir,
                "models_dir": models_dir,
                "license_path": license_path,
            }) or True
        )
        prod_main.get_runtime = lambda: self.fake_runtime

        self.assertTrue(self.original_runtime_bootstrap())
        self.assertNotEqual(records["libs_dir"], str(Path(self.tempdir.name) / "libs"))
        self.assertTrue(Path(records["libs_dir"], "libface_detect.so").exists())
        self.assertEqual(prod_main.PUBKEY_PATH, str(pubkey_path))

    def test_capabilities_endpoint_includes_manifest_metadata(self):
        body = prod_main.list_capabilities()
        self.assertEqual(body["capabilities"][0]["version"], "v1.2.3")
        self.assertEqual(body["capabilities"][0]["manifest"]["model_version"], "v1.2.3")

    def test_capabilities_endpoint_returns_empty_without_runtime(self):
        prod_main.get_runtime = lambda: None
        body = prod_main.list_capabilities()
        self.assertEqual(body, {"capabilities": []})

    def test_capability_diagnostics_reports_paths_and_discovered_models(self):
        body = prod_main.capability_diagnostics()
        self.assertTrue(body["runtime_initialized"])
        self.assertTrue(body["runtime_so_found"])
        self.assertTrue(body["models_dir_exists"])
        self.assertTrue(body["libs_dir_exists"])
        self.assertIn("face_detect", body["loaded_capabilities"])
        self.assertIn("face_detect", body["discovered_model_capabilities"])

    def test_license_status_endpoint_reports_missing_when_no_file(self):
        body = prod_main.license_status()
        self.assertEqual(body["status"], "missing")
        self.assertEqual(body["capabilities"], [])

    def test_license_status_endpoint_reports_signature_invalid(self):
        self._write_license()
        prod_main._verify_license_signature = lambda raw: False
        body = prod_main.license_status()
        self.assertEqual(body["status"], "signature_invalid")
        self.assertEqual(body["license_id"], "lic-test")

    def test_license_status_endpoint_reports_expired(self):
        self._write_license(valid_until=(datetime.now(prod_main.CST) - timedelta(days=1)).isoformat())
        prod_main._verify_license_signature = lambda raw: True
        body = prod_main.license_status()
        self.assertEqual(body["status"], "expired")
        self.assertEqual(body["days_remaining"], 0)

    def test_license_status_endpoint_reports_not_yet_valid(self):
        self._write_license(
            valid_from=(datetime.now(prod_main.CST) + timedelta(days=2)).isoformat(),
            valid_until=(datetime.now(prod_main.CST) + timedelta(days=10)).isoformat(),
        )
        prod_main._verify_license_signature = lambda raw: True
        body = prod_main.license_status()
        self.assertEqual(body["status"], "not_yet_valid")
        self.assertLess(body["days_remaining"], 0)

    def test_license_status_endpoint_reports_invalid_for_malformed_json(self):
        Path(prod_main.LICENSE_PATH).write_text("{bad json", encoding="utf-8")
        body = prod_main.license_status()
        self.assertEqual(body["status"], "invalid")

    def test_check_license_allows_missing_license_in_dev_mode(self):
        prod_main._check_license = self.original_check_license
        prod_main._check_license("face_detect")

    def test_check_license_rejects_unlicensed_capability(self):
        self._write_license(capabilities=["other_cap"])
        prod_main._verify_license_signature = lambda raw: True
        prod_main._check_license = self.original_check_license
        with self.assertRaises(HTTPException) as ctx:
            prod_main._check_license("face_detect")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail["code"], 4004)

    def test_check_license_rejects_not_yet_valid_license(self):
        self._write_license(
            valid_from=(datetime.now(prod_main.CST) + timedelta(days=2)).isoformat(),
            valid_until=(datetime.now(prod_main.CST) + timedelta(days=10)).isoformat(),
        )
        prod_main._verify_license_signature = lambda raw: True
        prod_main._check_license = self.original_check_license
        with self.assertRaises(HTTPException) as ctx:
            prod_main._check_license("face_detect")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail["code"], 4003)

    def test_check_license_allows_wildcard_capability(self):
        self._write_license(capabilities=["*"])
        prod_main._verify_license_signature = lambda raw: True
        prod_main._check_license = self.original_check_license
        prod_main._check_license("arbitrary_capability")

    def test_infer_endpoint_returns_expired_license_before_runtime(self):
        self._write_license(valid_until=(datetime.now(prod_main.CST) - timedelta(days=1)).isoformat())
        prod_main._verify_license_signature = lambda raw: True
        prod_main._check_license = self.original_check_license
        runtime_calls = []
        self.fake_runtime.acquire = lambda capability, timeout_ms=30000: runtime_calls.append(capability)
        upload = UploadFile(file=io.BytesIO(b"ok"), filename="x.bin")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(prod_main.infer("face_detect", SimpleNamespace(headers={}), upload))
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail["code"], 4002)
        self.assertEqual(runtime_calls, [])

    def test_infer_endpoint_rejects_large_payload(self):
        prod_main.MAX_UPLOAD_BYTES = 1
        upload = UploadFile(file=io.BytesIO(b"12"), filename="x.bin")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(prod_main.infer("face_detect", SimpleNamespace(headers={}), upload))
        self.assertEqual(ctx.exception.status_code, 413)

    def test_infer_endpoint_returns_busy_when_concurrency_limit_hit(self):
        prod_main.INFER_CONCURRENCY_TIMEOUT_SECONDS = 1
        prod_main._infer_request_semaphore = asyncio.Semaphore(0)
        upload = UploadFile(file=io.BytesIO(b"ok"), filename="x.bin")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(prod_main.infer("face_detect", SimpleNamespace(headers={}), upload))
        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail["code"], 3002)

    def test_infer_endpoint_returns_ab_test_metadata(self):
        upload = UploadFile(file=io.BytesIO(b"ok"), filename="x.bin")
        body = asyncio.run(
            prod_main.infer(
                "face_detect",
                SimpleNamespace(headers={"X-Session-ID": "session-1"}),
                upload,
            )
        )
        self.assertEqual(body["model_version"], "v1.2.3")
        self.assertEqual(body["ab_test"]["selected_version"], "v2.0.0")
        self.assertEqual(body["ab_test"]["applied_version"], "v1.2.3")
        self.assertFalse(body["ab_test"]["selection_matches_runtime"])

    def test_admin_ab_tests_endpoint_requires_token_and_returns_data(self):
        body = prod_main.list_ab_tests(SimpleNamespace(headers={"Authorization": "Bearer test-token"}))
        self.assertIn("face_detect", body["ab_tests"])

    def test_admin_ab_tests_reload_endpoint_reloads_manager(self):
        body = asyncio.run(
            prod_main.reload_ab_tests(SimpleNamespace(headers={"Authorization": "Bearer test-token"}))
        )
        self.assertEqual(body["status"], "reloaded")
        self.assertTrue(prod_main.ab_manager.reload_called)

    def test_admin_reload_endpoint_rejects_invalid_token(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(prod_main.reload_all(SimpleNamespace(headers={"Authorization": "Bearer wrong"})))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_admin_reload_endpoint_rejects_missing_token(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(prod_main.reload_all(SimpleNamespace(headers={})))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_admin_reload_capability_returns_current_version(self):
        body = asyncio.run(
            prod_main.reload_capability(
                "face_detect",
                SimpleNamespace(headers={"Authorization": "Bearer test-token"}),
            )
        )
        self.assertEqual(body["reloaded"], "face_detect")
        self.assertEqual(body["version"], "v1.2.3")

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

    def test_create_pipeline_endpoint_requires_admin_token(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(prod_main.create_pipeline_endpoint(_FakeJsonRequest({"pipeline_id": "p1"})))
        self.assertEqual(ctx.exception.status_code, 401)

    def test_create_pipeline_endpoint_rejects_missing_pipeline_id(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                prod_main.create_pipeline_endpoint(
                    _FakeJsonRequest({"name": "missing id"}, headers={"Authorization": "Bearer test-token"})
                )
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_create_pipeline_endpoint_rejects_duplicate_pipeline_id(self):
        pipeline = {"pipeline_id": "pipe_dup", "name": "Dup", "steps": [{"step_id": "s1", "capability": "face_detect"}]}
        (self.pipeline_dir / "pipe_dup.json").write_text(json.dumps(pipeline), encoding="utf-8")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                prod_main.create_pipeline_endpoint(
                    _FakeJsonRequest(pipeline, headers={"Authorization": "Bearer test-token"})
                )
            )
        self.assertEqual(ctx.exception.status_code, 409)

    def test_get_pipeline_endpoint_returns_not_found(self):
        with self.assertRaises(HTTPException) as ctx:
            prod_main.get_pipeline_endpoint("missing")
        self.assertEqual(ctx.exception.status_code, 404)

    def test_update_pipeline_endpoint_saves_pipeline_definition(self):
        body = asyncio.run(
            prod_main.update_pipeline_endpoint(
                "pipe_updated",
                _FakeJsonRequest(
                    {"name": "Updated", "steps": [{"step_id": "s1", "capability": "face_detect"}]},
                    headers={"Authorization": "Bearer test-token"},
                ),
            )
        )
        self.assertEqual(body["status"], "updated")
        saved = json.loads((self.pipeline_dir / "pipe_updated.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["pipeline_id"], "pipe_updated")
        self.assertEqual(saved["name"], "Updated")

    def test_delete_pipeline_endpoint_returns_not_found(self):
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(
                prod_main.delete_pipeline_endpoint(
                    "missing",
                    SimpleNamespace(headers={"Authorization": "Bearer test-token"}),
                )
            )
        self.assertEqual(ctx.exception.status_code, 404)

    def test_run_pipeline_endpoint_returns_not_found(self):
        upload = UploadFile(file=io.BytesIO(b"ok"), filename="x.bin")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(prod_main.run_pipeline_endpoint("missing", upload))
        self.assertEqual(ctx.exception.status_code, 404)

    def test_run_pipeline_endpoint_rejects_disabled_pipeline(self):
        pipeline = {
            "pipeline_id": "pipe_disabled",
            "name": "Disabled",
            "enabled": False,
            "steps": [{"step_id": "s1", "capability": "face_detect"}],
        }
        (self.pipeline_dir / "pipe_disabled.json").write_text(json.dumps(pipeline), encoding="utf-8")
        upload = UploadFile(file=io.BytesIO(b"ok"), filename="x.bin")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(prod_main.run_pipeline_endpoint("pipe_disabled", upload))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_run_pipeline_endpoint_stops_after_license_failure(self):
        pipeline = {
            "pipeline_id": "pipe_license",
            "name": "License stop",
            "steps": [
                {"step_id": "s1", "capability": "face_detect", "output_mapping": {"ok": "$.ok"}},
                {"step_id": "s2", "capability": "second_cap", "on_failure": "abort"},
            ],
        }
        (self.pipeline_dir / "pipe_license.json").write_text(json.dumps(pipeline), encoding="utf-8")

        calls = []

        def fake_infer(capability, image_bytes, options):
            calls.append(capability)
            return {"ok": True}

        def fake_check_license(capability):
            if capability == "second_cap":
                raise HTTPException(status_code=403, detail={"code": 4004})

        prod_main._infer_for_pipeline = fake_infer
        prod_main._check_license = fake_check_license

        upload = UploadFile(file=io.BytesIO(b"ok"), filename="x.bin")
        body = asyncio.run(prod_main.run_pipeline_endpoint("pipe_license", upload))
        self.assertEqual(calls, ["face_detect"])
        self.assertEqual(body["steps"][0]["status"], "success")
        self.assertEqual(body["steps"][1]["status"], "error")
        self.assertEqual(body["steps"][1]["error"], "License check failed")

    def test_run_pipeline_endpoint_skips_step_when_condition_not_met(self):
        pipeline = {
            "pipeline_id": "pipe_condition",
            "name": "Condition skip",
            "steps": [
                {
                    "step_id": "s1",
                    "capability": "face_detect",
                    "output_mapping": {"count": "$.count"},
                },
                {
                    "step_id": "s2",
                    "capability": "second_cap",
                    "condition": "${s1.count} > 5",
                },
            ],
        }
        (self.pipeline_dir / "pipe_condition.json").write_text(json.dumps(pipeline), encoding="utf-8")

        calls = []

        def fake_infer(capability, image_bytes, options):
            calls.append(capability)
            return {"count": 1}

        prod_main._infer_for_pipeline = fake_infer

        upload = UploadFile(file=io.BytesIO(b"ok"), filename="x.bin")
        body = asyncio.run(prod_main.run_pipeline_endpoint("pipe_condition", upload))
        self.assertEqual(calls, ["face_detect"])
        self.assertEqual(body["steps"][0]["status"], "success")
        self.assertEqual(body["steps"][1]["status"], "skipped")
        self.assertEqual(body["steps"][1]["reason"], "condition not met")

    def test_run_pipeline_endpoint_continues_after_step_failure_with_skip(self):
        pipeline = {
            "pipeline_id": "pipe_continue",
            "name": "Continue after failure",
            "steps": [
                {"step_id": "s1", "capability": "face_detect"},
                {"step_id": "s2", "capability": "second_cap", "on_failure": "skip"},
                {"step_id": "s3", "capability": "third_cap"},
            ],
        }
        (self.pipeline_dir / "pipe_continue.json").write_text(json.dumps(pipeline), encoding="utf-8")

        calls = []

        def fake_infer(capability, image_bytes, options):
            calls.append(capability)
            if capability == "second_cap":
                raise RuntimeError("boom")
            return {"ok": capability}

        prod_main._infer_for_pipeline = fake_infer

        upload = UploadFile(file=io.BytesIO(b"ok"), filename="x.bin")
        body = asyncio.run(prod_main.run_pipeline_endpoint("pipe_continue", upload))
        self.assertEqual(calls, ["face_detect", "second_cap", "third_cap"])
        self.assertEqual([step["status"] for step in body["steps"]], ["success", "error", "success"])

    def test_run_pipeline_endpoint_returns_final_output_from_step_context(self):
        pipeline = {
            "pipeline_id": "pipe_final_output",
            "name": "Final output mapping",
            "steps": [
                {
                    "step_id": "s1",
                    "capability": "face_detect",
                    "output_mapping": {
                        "passed": "$.passed",
                        "score": "$.score",
                    },
                }
            ],
            "final_output": {
                "passed": "${s1.passed}",
                "score_ok": "${s1.score} >= 0.5",
            },
        }
        (self.pipeline_dir / "pipe_final_output.json").write_text(json.dumps(pipeline), encoding="utf-8")

        prod_main._infer_for_pipeline = lambda capability, image_bytes, options: {
            "passed": True,
            "score": 0.75,
        }

        upload = UploadFile(file=io.BytesIO(b"ok"), filename="x.bin")
        body = asyncio.run(prod_main.run_pipeline_endpoint("pipe_final_output", upload))
        self.assertEqual(body["steps"][0]["status"], "success")
        self.assertEqual(body["final_result"], {"passed": True, "score_ok": True})

    def test_run_pipeline_endpoint_stops_after_condition_evaluation_error(self):
        pipeline = {
            "pipeline_id": "pipe_condition_error",
            "name": "Condition error",
            "steps": [
                {"step_id": "s1", "capability": "face_detect", "output_mapping": {"label": "$.label"}},
                {"step_id": "s2", "capability": "second_cap", "condition": "${s1.label} > 1"},
                {"step_id": "s3", "capability": "third_cap"},
            ],
        }
        (self.pipeline_dir / "pipe_condition_error.json").write_text(json.dumps(pipeline), encoding="utf-8")

        calls = []

        def fake_infer(capability, image_bytes, options):
            calls.append(capability)
            return {"label": "abc"}

        prod_main._infer_for_pipeline = fake_infer

        upload = UploadFile(file=io.BytesIO(b"ok"), filename="x.bin")
        body = asyncio.run(prod_main.run_pipeline_endpoint("pipe_condition_error", upload))
        self.assertEqual(calls, ["face_detect"])
        self.assertEqual(body["steps"][0]["status"], "success")
        self.assertEqual(body["steps"][1]["status"], "error")
        self.assertEqual(body["steps"][1]["error"], "Condition evaluation error")
        self.assertEqual(len(body["steps"]), 2)


if __name__ == "__main__":
    unittest.main()
