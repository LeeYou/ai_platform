from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
CPU_BUILDER_DOCKERFILE = REPO_ROOT / "build" / "Dockerfile.linux_x86"
GPU_BUILDER_DOCKERFILE = REPO_ROOT / "build" / "Dockerfile.linux_x86_gpu"
COMPOSE_FILE = REPO_ROOT / "deploy" / "docker-compose.yml"


class BuildDockerAssetsTests(unittest.TestCase):
    def test_cpu_builder_dockerfile_uses_cpu_onnxruntime_package(self):
        content = CPU_BUILDER_DOCKERFILE.read_text(encoding="utf-8")

        self.assertIn("FROM ubuntu:22.04", content)
        self.assertIn("ARG ONNXRUNTIME_PACKAGE=onnxruntime-linux-x64", content)
        self.assertIn("BUILDER_TOOLCHAIN_PROFILE=cpu-ort", content)

    def test_gpu_builder_dockerfile_uses_cuda_devel_and_gpu_onnxruntime(self):
        content = GPU_BUILDER_DOCKERFILE.read_text(encoding="utf-8")

        self.assertIn("FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04", content)
        self.assertIn("ARG ONNXRUNTIME_PACKAGE=onnxruntime-linux-x64-gpu", content)
        self.assertIn("libnvinfer-dev", content)
        self.assertIn("libnvinfer-plugin-dev", content)
        self.assertNotIn("libnvonnxparsers-dev", content)
        self.assertNotIn("libnvparsers-dev", content)
        self.assertIn("ARG GITHUB_HTTPS_PROXY=", content)
        self.assertIn("CUDA_HOME=/usr/local/cuda", content)
        self.assertIn("NvInfer.h", content)
        self.assertIn("libonnxruntime_providers_cuda.so", content)
        self.assertIn("BUILDER_TOOLCHAIN_PROFILE=cuda11.8-cudnn8", content)

    def test_compose_declares_gpu_builder_profile_and_runtime(self):
        content = COMPOSE_FILE.read_text(encoding="utf-8")

        self.assertIn("build-gpu:", content)
        self.assertIn('profiles: ["gpu-build"]', content)
        self.assertIn("dockerfile: build/Dockerfile.linux_x86_gpu", content)
        self.assertIn('- "8007:8004"', content)
        self.assertIn("driver: nvidia", content)
        self.assertIn("capabilities: [gpu]", content)
