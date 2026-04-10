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

    def test_execute_pipeline_returns_none_for_invalid_final_output_expression(self):
        pipeline = {
            "pipeline_id": "pipe_final_output_error",
            "name": "Final output error",
            "steps": [
                {
                    "step_id": "s1",
                    "capability": "face_detect",
                    "output_mapping": {"label": "$.label"},
                }
            ],
            "final_output": {"invalid_check": "${s1.label} > 1"},
        }

        result = pipeline_engine.execute_pipeline(
            pipeline,
            b"image-bytes",
            lambda capability, image_bytes, options: {"label": "abc"},
        )

        self.assertEqual(result["steps"][0]["status"], "success")
        self.assertEqual(result["final_result"], {"invalid_check": None})

    def test_execute_pipeline_condition_error_with_skip_continues_downstream(self):
        pipeline = {
            "pipeline_id": "pipe_condition_error_skip",
            "name": "Condition error skip",
            "steps": [
                {
                    "step_id": "s1",
                    "capability": "face_detect",
                    "output_mapping": {"label": "$.label"},
                },
                {
                    "step_id": "s2",
                    "capability": "second_cap",
                    "condition": "${s1.label} > 1",
                    "on_failure": "skip",
                },
                {"step_id": "s3", "capability": "third_cap"},
            ],
        }

        calls = []

        def fake_infer(capability, image_bytes, options):
            calls.append(capability)
            if capability == "face_detect":
                return {"label": "abc"}
            return {"capability": capability}

        result = pipeline_engine.execute_pipeline(
            pipeline,
            b"image-bytes",
            fake_infer,
        )

        self.assertEqual(calls, ["face_detect", "third_cap"])
        self.assertEqual([step["status"] for step in result["steps"]], ["success", "error", "success"])
        self.assertEqual(result["steps"][1]["error"], "Condition evaluation error")

    def test_execute_pipeline_global_options_override_step_options(self):
        pipeline = {
            "pipeline_id": "pipe_global_options",
            "name": "Global options override",
            "steps": [
                {
                    "step_id": "s1",
                    "capability": "face_detect",
                    "options": {"threshold": 0.2, "mode": "default"},
                }
            ],
        }

        seen_options = {}

        def fake_infer(capability, image_bytes, options):
            seen_options.update(options)
            return {"ok": True}

        result = pipeline_engine.execute_pipeline(
            pipeline,
            b"image-bytes",
            fake_infer,
            global_options={"s1": {"threshold": 0.8}},
        )

        self.assertEqual(result["steps"][0]["status"], "success")
        self.assertEqual(seen_options, {"threshold": 0.8, "mode": "default"})


if __name__ == "__main__":
    unittest.main()
