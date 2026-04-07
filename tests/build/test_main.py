import importlib.util
import json
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


class DesktopRecaptureExportTests(unittest.TestCase):
    def test_export_preprocess_json_uses_numeric_resize_dimensions(self):
        export_path = (
            Path(__file__).resolve().parents[2]
            / "train"
            / "scripts"
            / "desktop_recapture_detect"
            / "export.py"
        )
        spec = importlib.util.spec_from_file_location("desktop_recapture_export", export_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as temp_dir:
            module._write_preprocess_json(temp_dir)
            payload = json.loads(Path(temp_dir, "preprocess.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["resize"]["width"], 224)
        self.assertEqual(payload["resize"]["height"], 224)
        self.assertIsInstance(payload["resize"]["width"], int)
        self.assertIsInstance(payload["resize"]["height"], int)

    def test_export_manifest_json_uses_model_version_field(self):
        export_path = (
            Path(__file__).resolve().parents[2]
            / "train"
            / "scripts"
            / "desktop_recapture_detect"
            / "export.py"
        )
        spec = importlib.util.spec_from_file_location("desktop_recapture_export", export_path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)

        with tempfile.TemporaryDirectory() as temp_dir:
            module._write_manifest_json(temp_dir, "v9.9.9")
            payload = json.loads(Path(temp_dir, "manifest.json").read_text(encoding="utf-8"))

        self.assertEqual(payload["model_version"], "v9.9.9")
        self.assertNotIn("version", payload)


class BuildGpuProfileTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.original_cpp_source_dir = build_main.CPP_SOURCE_DIR
        build_main.CPP_SOURCE_DIR = str(Path(self.tempdir.name) / "cpp")

        runtime_gpu_dir = Path(build_main.CPP_SOURCE_DIR) / "capabilities" / "desktop_recapture_detect"
        runtime_gpu_dir.mkdir(parents=True, exist_ok=True)
        (runtime_gpu_dir / "desktop_recapture_detect.cpp").write_text(
            "OrtCUDAProviderOptions opts; session.AppendExecutionProvider_CUDA(opts);\n",
            encoding="utf-8",
        )

        compile_gpu_dir = Path(build_main.CPP_SOURCE_DIR) / "capabilities" / "cuda_kernel_cap"
        compile_gpu_dir.mkdir(parents=True, exist_ok=True)
        (compile_gpu_dir / "kernel.cu").write_text("__global__ void kernel() {}\n", encoding="utf-8")

        cpu_dir = Path(build_main.CPP_SOURCE_DIR) / "capabilities" / "cpu_only"
        cpu_dir.mkdir(parents=True, exist_ok=True)
        (cpu_dir / "cpu_only.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")

    def tearDown(self):
        build_main.CPP_SOURCE_DIR = self.original_cpp_source_dir
        self.tempdir.cleanup()

    def test_build_gpu_profile_marks_runtime_only_capability(self):
        profile = build_main._build_gpu_profile("desktop_recapture_detect", ["-DBUILD_GPU=ON"])

        self.assertTrue(profile["runtime_gpu_capable"])
        self.assertEqual(profile["compile_gpu_mode"], "runtime_only")
        self.assertFalse(profile["compile_time_gpu_required"])
        self.assertTrue(profile["legacy_build_gpu_requested"])
        self.assertEqual(profile["compile_gpu_features"], [])

    def test_build_gpu_profile_marks_compile_time_gpu_capability(self):
        profile = build_main._build_gpu_profile("cuda_kernel_cap", [])

        self.assertFalse(profile["runtime_gpu_capable"])
        self.assertEqual(profile["compile_gpu_mode"], "cuda_toolchain_required")
        self.assertTrue(profile["compile_time_gpu_required"])

    def test_validate_build_environment_rejects_missing_gpu_builder_dependencies(self):
        original_probe = build_main._probe_builder_environment
        build_main._probe_builder_environment = lambda: {
            "builder_image": "cpu-builder",
            "builder_toolchain_profile": "cpu-ort",
            "cmake_version": "cmake version 3.22.1",
            "compiler": "g++ 12.3.0",
            "cuda_home": "/usr/local/cuda",
            "cuda_home_exists": False,
            "cuda_toolkit_available": False,
            "nvcc_path": "",
            "tensorrt_available": False,
            "tensorrt_include": "",
            "tensorrt_library": "",
            "onnxruntime_root": "/usr/local",
            "onnxruntime_package": "cpu",
            "onnxruntime_cuda_provider_library": "",
            "supports_compile_time_gpu_features": [],
        }
        try:
            with self.assertRaises(build_main.HTTPException) as ctx:
                build_main._validate_build_environment(
                    "desktop_recapture_detect",
                    ["-DENABLE_TENSORRT=ON"],
                )
        finally:
            build_main._probe_builder_environment = original_probe

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("TensorRT", ctx.exception.detail)
        self.assertIn("GPU builder", ctx.exception.detail)

    def test_write_build_info_records_builder_and_gpu_contract(self):
        original_probe = build_main._probe_builder_environment
        original_run_command_output = build_main._run_command_output
        build_main._probe_builder_environment = lambda: {
            "builder_image": "agilestar/ai-builder-linux-x86-gpu:latest",
            "builder_toolchain_profile": "cuda11.8-cudnn8",
            "cmake_version": "cmake version 3.27.0",
            "compiler": "g++ 12.3.0",
            "cuda_home": "/usr/local/cuda",
            "cuda_home_exists": True,
            "cuda_toolkit_available": True,
            "nvcc_path": "/usr/local/cuda/bin/nvcc",
            "tensorrt_available": False,
            "tensorrt_include": "",
            "tensorrt_library": "",
            "onnxruntime_root": "/usr/local",
            "onnxruntime_package": "gpu",
            "onnxruntime_cuda_provider_library": "/usr/local/lib/libonnxruntime_providers_cuda.so",
            "supports_compile_time_gpu_features": ["ENABLE_CUDA_KERNELS"],
        }
        build_main._run_command_output = lambda args, cwd=None: "abc1234" if args[:3] == ["git", "rev-parse", "--short"] else ""

        try:
            with tempfile.TemporaryDirectory() as artifact_dir:
                job = {
                    "job_id": "job-1",
                    "capability": "desktop_recapture_detect",
                    "model_version": "v1.2.3",
                    "trusted_pubkey_sha256": "f" * 64,
                }
                req = build_main.BuildRequest(capability="desktop_recapture_detect")
                build_main._write_build_info(job, req, artifact_dir)
                payload = json.loads(Path(artifact_dir, "build_info.json").read_text(encoding="utf-8"))
        finally:
            build_main._probe_builder_environment = original_probe
            build_main._run_command_output = original_run_command_output

        self.assertTrue(payload["gpu_enabled"])
        self.assertTrue(payload["runtime_gpu_capable"])
        self.assertEqual(payload["compile_gpu_mode"], "runtime_only")
        self.assertEqual(payload["builder_image"], "agilestar/ai-builder-linux-x86-gpu:latest")
        self.assertEqual(payload["builder_toolchain_profile"], "cuda11.8-cudnn8")
        self.assertEqual(payload["onnxruntime_package"], "gpu")
        self.assertTrue(payload["cuda_toolkit_available"])
        self.assertFalse(payload["tensorrt_available"])
