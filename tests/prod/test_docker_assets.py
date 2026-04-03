from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_DOCKERFILE = REPO_ROOT / "prod" / "Dockerfile"


class ProdDockerAssetsTests(unittest.TestCase):
    def test_prod_dockerfile_uses_cuda_11_8_runtime_base(self):
        content = PROD_DOCKERFILE.read_text(encoding="utf-8")

        self.assertIn("FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04", content)
        self.assertNotIn("CUDA_BASE_IMAGE", content)

    def test_prod_dockerfile_installs_gpu_onnxruntime_bundle(self):
        content = PROD_DOCKERFILE.read_text(encoding="utf-8")

        self.assertIn("ARG ONNXRUNTIME_PACKAGE=onnxruntime-linux-x64-gpu", content)
        self.assertIn(
            "${ONNXRUNTIME_PACKAGE}-${ONNXRUNTIME_VERSION}.tgz",
            content,
        )

    def test_prod_dockerfile_exports_onnxruntime_library_path(self):
        content = PROD_DOCKERFILE.read_text(encoding="utf-8")

        self.assertIn("ONNXRUNTIME_ROOT=/usr/local", content)
        self.assertIn("CUDA_HOME=/usr/local/cuda", content)
        self.assertIn(
            "LD_LIBRARY_PATH=/usr/local/cuda/lib64:/usr/local/nvidia/lib64:/usr/local/lib:${LD_LIBRARY_PATH}",
            content,
        )

    def test_prod_dockerfile_checks_cuda_runtime_libraries(self):
        content = PROD_DOCKERFILE.read_text(encoding="utf-8")

        self.assertIn('ldconfig -p | grep -q "libcublasLt.so.11"', content)
        self.assertIn('ldconfig -p | grep -q "libcudnn.so.8"', content)
