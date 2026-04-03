from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]
PROD_DOCKERFILE = REPO_ROOT / "prod" / "Dockerfile"


class ProdDockerAssetsTests(unittest.TestCase):
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
        self.assertIn("LD_LIBRARY_PATH=/usr/local/lib:${LD_LIBRARY_PATH}", content)
