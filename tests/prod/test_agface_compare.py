"""Unit tests for `prod.web_service.agface_compare`.

Covers the pure-Python helpers (cosine / score mapping / bbox picker /
compare_faces orchestration with a mock infer_fn) without touching any
C++ runtime.
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

PROD_DIR = Path(__file__).resolve().parents[2] / "prod" / "web_service"
if str(PROD_DIR) not in sys.path:
    sys.path.insert(0, str(PROD_DIR))

from agface_compare import (  # noqa: E402
    ALLOWED_FEATURE_CAPABILITIES,
    calibrate_score,
    compare_faces,
    cosine_similarity,
    pick_largest_face_bbox,
)


class CosineTests(unittest.TestCase):

    def test_identical_vectors(self) -> None:
        v = [0.1, 0.2, 0.3, 0.4]
        self.assertAlmostEqual(cosine_similarity(v, v), 1.0, places=6)

    def test_orthogonal_vectors(self) -> None:
        self.assertAlmostEqual(
            cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0, places=6
        )

    def test_opposite_vectors(self) -> None:
        self.assertAlmostEqual(
            cosine_similarity([1.0, 2.0, 3.0], [-1.0, -2.0, -3.0]),
            -1.0,
            places=6,
        )

    def test_zero_norm_guard(self) -> None:
        self.assertEqual(cosine_similarity([0.0, 0.0], [0.0, 0.0]), 0.0)

    def test_dimension_mismatch_raises(self) -> None:
        with self.assertRaises(ValueError):
            cosine_similarity([1.0, 2.0], [1.0, 2.0, 3.0])


class CalibrateScoreTests(unittest.TestCase):
    """Piecewise-linear anchor checks — values match old SimilarityCalculator."""

    def test_anchor_points(self) -> None:
        cases = [
            (-1.0,   0.0),
            ( 0.0,  10.0),
            ( 0.3,  30.0),
            ( 0.5,  60.0),
            ( 0.7,  85.0),
            ( 1.0, 100.0),
        ]
        for cos, expected in cases:
            with self.subTest(cos=cos):
                self.assertAlmostEqual(calibrate_score(cos), expected, places=4)

    def test_monotonic_increasing(self) -> None:
        xs = [-1.0, -0.5, -0.1, 0.0, 0.1, 0.3, 0.4, 0.5, 0.6, 0.7, 0.85, 1.0]
        ys = [calibrate_score(x) for x in xs]
        for a, b in zip(ys, ys[1:]):
            self.assertLessEqual(a, b + 1e-9)

    def test_clamped_to_range(self) -> None:
        self.assertEqual(calibrate_score(-2.0), 0.0)
        self.assertEqual(calibrate_score(2.0), 100.0)


class PickLargestBboxTests(unittest.TestCase):

    def test_empty(self) -> None:
        self.assertIsNone(pick_largest_face_bbox({}))
        self.assertIsNone(pick_largest_face_bbox({"faces": []}))

    def test_picks_largest_area(self) -> None:
        det = {
            "faces": [
                {"bbox": [10, 10, 30, 30], "confidence": 0.9},  # area 900
                {"bbox": [50, 50, 80, 80], "confidence": 0.8},  # area 6400
                {"bbox": [0, 0, 20, 100], "confidence": 0.7},   # area 2000
            ]
        }
        self.assertEqual(pick_largest_face_bbox(det), [50, 50, 80, 80])

    def test_ignores_malformed(self) -> None:
        det = {"faces": [{"bbox": None}, {"bbox": [1, 2, 3]}]}
        self.assertIsNone(pick_largest_face_bbox(det))


class CompareFacesOrchestrationTests(unittest.TestCase):
    """Exercise compare_faces with an in-memory mock infer_fn."""

    def test_rejects_unknown_capability(self) -> None:
        with self.assertRaises(ValueError):
            compare_faces(
                b"x", b"y",
                infer_fn=lambda *_args, **_kw: {},
                feature_capability="not_a_capability",
                detector_capability=None,
            )

    def test_skip_detector_flow(self) -> None:
        unit = [1.0 / math.sqrt(3)] * 3

        def fake_infer(cap: str, _data: bytes, _opts: dict) -> dict:
            assert cap in ALLOWED_FEATURE_CAPABILITIES
            return {"feature": unit, "dim": 3, "l2_normalized": True}

        out = compare_faces(
            b"a", b"b",
            infer_fn=fake_infer,
            feature_capability="agface_face_feature_glint512",
            detector_capability=None,
        )
        self.assertAlmostEqual(out["cosine"], 1.0, places=5)
        self.assertAlmostEqual(out["score"], 100.0, places=1)
        self.assertEqual(out["dim"], 3)
        self.assertEqual(out["faces"], {"image_a": 0, "image_b": 0})
        self.assertIsNone(out["detector_capability"])

    def test_detector_crops_bbox(self) -> None:
        calls: list[tuple[str, int]] = []

        # Minimal fake decoder: treat bytes length as both w and h of a 1ch "image"
        class FakeNdArray(list):
            def __init__(self, h: int, w: int) -> None:
                self.shape = (h, w, 3)

            def __getitem__(self, sl):
                # ignore slice, return a smaller fake with unchanged metadata shape
                if isinstance(sl, tuple):
                    return FakeNdArray(10, 10)
                return super().__getitem__(sl)

            def copy(self) -> "FakeNdArray":
                return FakeNdArray(self.shape[0], self.shape[1])

        def fake_decode(data: bytes):
            return FakeNdArray(200, 200)

        def fake_encode(img) -> bytes:
            return b"cropped-" + bytes([img.shape[0] & 0xFF])

        def fake_infer(cap: str, data: bytes, _opts: dict) -> dict:
            calls.append((cap, len(data)))
            if cap == "agface_face_detect":
                return {
                    "faces": [{"bbox": [50, 50, 80, 80], "confidence": 0.9}],
                    "image_size": [200, 200],
                }
            # feature extractor — return a unit vector
            v = [1.0] + [0.0] * 3
            return {"feature": v, "dim": 4, "l2_normalized": True}

        result = compare_faces(
            b"aaaa", b"bbbb",
            infer_fn=fake_infer,
            feature_capability="agface_face_feature_residual256",
            detector_capability="agface_face_detect",
            decode_fn=fake_decode,
            encode_fn=fake_encode,
            margin_ratio=0.1,
        )

        # detector called twice, then feature called twice on "cropped-*" bytes
        caps_used = [c[0] for c in calls]
        self.assertEqual(caps_used,
                         ["agface_face_detect", "agface_face_detect",
                          "agface_face_feature_residual256",
                          "agface_face_feature_residual256"])
        self.assertEqual(result["faces"], {"image_a": 1, "image_b": 1})
        self.assertAlmostEqual(result["cosine"], 1.0, places=5)
        self.assertEqual(result["dim"], 4)


if __name__ == "__main__":
    unittest.main()
