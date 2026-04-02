import json
from pathlib import Path
import sys
import tempfile
import unittest


PROD_DIR = Path(__file__).resolve().parents[2] / "prod" / "web_service"
if str(PROD_DIR) not in sys.path:
    sys.path.insert(0, str(PROD_DIR))

import pipeline_engine  # noqa: E402


class PipelineEngineTests(unittest.TestCase):
    def test_validate_pipeline_reports_unknown_capability(self):
        pipeline = {
            "pipeline_id": "demo",
            "name": "Demo Pipeline",
            "steps": [{"step_id": "s1", "capability": "missing_cap"}],
        }
        errors = pipeline_engine.validate_pipeline(pipeline, ["face_detect"])
        self.assertTrue(any("missing_cap" in err for err in errors))

    def test_pipeline_file_crud_uses_configured_directory(self):
        pipeline = {
            "pipeline_id": "pipe_a",
            "name": "Pipeline A",
            "steps": [{"step_id": "s1", "capability": "face_detect"}],
        }
        with tempfile.TemporaryDirectory() as tmpdir:
            original_dir = pipeline_engine.PIPELINE_DIR
            pipeline_engine.PIPELINE_DIR = tmpdir
            try:
                pipeline_engine.save_pipeline(pipeline)
                loaded = pipeline_engine.get_pipeline("pipe_a")
                self.assertEqual(loaded["name"], "Pipeline A")
                listed = pipeline_engine.list_pipelines()
                self.assertEqual(len(listed), 1)
                self.assertTrue(pipeline_engine.delete_pipeline_file("pipe_a"))
                self.assertIsNone(pipeline_engine.get_pipeline("pipe_a"))
            finally:
                pipeline_engine.PIPELINE_DIR = original_dir


if __name__ == "__main__":
    unittest.main()
