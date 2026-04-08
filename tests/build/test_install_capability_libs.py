import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "install_capability_libs.sh"
PACKAGE_SCRIPT = REPO_ROOT / "scripts" / "package_delivery.sh"


class InstallCapabilityLibsTests(unittest.TestCase):
    def test_install_script_replaces_current_libs_and_keeps_backup(self):
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = Path(tempdir)
            host_root = temp_path / "host"
            target_dir = host_root / "libs" / "linux_x86_64" / "desktop_recapture_detect" / "current" / "lib"
            target_dir.mkdir(parents=True, exist_ok=True)
            (target_dir / "libai_runtime.so").write_text("old-runtime", encoding="utf-8")
            (target_dir / "libdesktop_recapture_detect.so").write_text("old-capability", encoding="utf-8")

            artifact_root = temp_path / "artifact_src" / "desktop_recapture_detect" / "1.0.0" / "job-1" / "lib"
            artifact_root.mkdir(parents=True, exist_ok=True)
            (artifact_root.parent / "build_info.json").write_text(
                '{"onnxruntime_package":"gpu","builder_toolchain_profile":"cuda11.8-cudnn8"}',
                encoding="utf-8",
            )
            (artifact_root / "libai_runtime.so").write_text("new-runtime", encoding="utf-8")
            (artifact_root / "libdesktop_recapture_detect.so").write_text("new-capability", encoding="utf-8")
            artifact_tar = temp_path / "artifact.tar.gz"
            with tarfile.open(artifact_tar, "w:gz") as tf:
                tf.add(temp_path / "artifact_src", arcname="artifact")

            subprocess.run(
                [str(SCRIPT), str(artifact_tar), "desktop_recapture_detect", "linux_x86_64", str(host_root)],
                check=True,
                capture_output=True,
                text=True,
            )

            self.assertEqual((target_dir / "libai_runtime.so").read_text(encoding="utf-8"), "new-runtime")
            self.assertEqual(
                (target_dir / "libdesktop_recapture_detect.so").read_text(encoding="utf-8"),
                "new-capability",
            )
            self.assertIn(
                '"onnxruntime_package":"gpu"',
                (target_dir.parent / "build_info.json").read_text(encoding="utf-8"),
            )

            backup_root = host_root / "backup"
            backups = list(backup_root.glob("*/desktop_recapture_detect"))
            self.assertEqual(len(backups), 1)
            self.assertEqual((backups[0] / "libai_runtime.so").read_text(encoding="utf-8"), "old-runtime")
            self.assertEqual(
                (backups[0] / "libdesktop_recapture_detect.so").read_text(encoding="utf-8"),
                "old-capability",
            )

    def test_install_script_requires_existing_current_lib_dir(self):
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = Path(tempdir)
            artifact_root = temp_path / "artifact_src" / "desktop_recapture_detect" / "1.0.0" / "job-1" / "lib"
            artifact_root.mkdir(parents=True, exist_ok=True)
            (artifact_root / "libai_runtime.so").write_text("new-runtime", encoding="utf-8")
            (artifact_root / "libdesktop_recapture_detect.so").write_text("new-capability", encoding="utf-8")
            artifact_tar = temp_path / "artifact.tar.gz"
            with tarfile.open(artifact_tar, "w:gz") as tf:
                tf.add(temp_path / "artifact_src", arcname="artifact")

            proc = subprocess.run(
                [str(SCRIPT), str(artifact_tar), "desktop_recapture_detect", "linux_x86_64", str(temp_path / "host")],
                check=False,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("Target directory does not exist", proc.stderr)


class PackageDeliveryScriptTests(unittest.TestCase):
    def test_package_delivery_includes_install_helper_and_manifest_hint(self):
        content = PACKAGE_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('scripts/install_capability_libs.sh', content)
        self.assertIn('tools/install_capability_libs.sh <artifact.tar.gz> <capability>', content)
