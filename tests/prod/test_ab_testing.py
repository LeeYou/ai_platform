import json
import sys
import tempfile
import unittest
from pathlib import Path


PROD_DIR = Path(__file__).resolve().parents[2] / "prod" / "web_service"
if str(PROD_DIR) not in sys.path:
    sys.path.insert(0, str(PROD_DIR))

from ab_testing import ABTestManager  # noqa: E402


class ABTestingTests(unittest.TestCase):
    def test_sticky_session_selection_is_deterministic(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "face_detect.json"
            config_path.write_text(
                json.dumps(
                    {
                        "capability": "face_detect",
                        "strategy": "sticky_session",
                        "enabled": True,
                        "variants": [
                            {"version": "v1.0.0", "weight": 50},
                            {"version": "v2.0.0", "weight": 50},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            manager = ABTestManager(tmpdir)
            v1 = manager.get_version_for_request("face_detect", "same-session")
            v2 = manager.get_version_for_request("face_detect", "same-session")
            self.assertEqual(v1, v2)


if __name__ == "__main__":
    unittest.main()
