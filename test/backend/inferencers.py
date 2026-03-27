"""Capability-specific inferencer implementations.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

from typing import Any

import numpy as np

from inferencer import BaseInferencer


class RecaptureDetectInferencer(BaseInferencer):
    """翻拍检测 — 二分类（genuine / recaptured）."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out = outputs[0].flatten()
        if len(out) >= 2:
            # Two-class softmax
            exp = np.exp(out - out.max())
            prob = exp / exp.sum()
            score_genuine    = float(prob[0])
            score_recaptured = float(prob[1])
        elif len(out) == 1:
            score_recaptured = float(1 / (1 + np.exp(-out[0])))
            score_genuine    = 1.0 - score_recaptured
        else:
            score_genuine = score_recaptured = 0.5

        is_recaptured = score_recaptured > 0.5
        return {
            "is_recaptured": is_recaptured,
            "label": "recaptured" if is_recaptured else "genuine",
            "score_genuine": round(score_genuine, 4),
            "score_recaptured": round(score_recaptured, 4),
        }


class FaceDetectInferencer(BaseInferencer):
    """人脸检测 — bounding box + confidence."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        bbox   = outputs[0].flatten().tolist() if len(outputs) > 0 else [0, 0, 1, 1]
        conf_raw = outputs[1].flatten() if len(outputs) > 1 else np.array([0.9])
        conf   = float(1 / (1 + np.exp(-conf_raw[0])))
        face_detected = conf > 0.5

        detections = []
        if face_detected and len(bbox) >= 4:
            detections.append({
                "bbox": [round(v, 4) for v in bbox[:4]],
                "confidence": round(conf, 4),
                "label": "face",
            })
        return {
            "face_detected": face_detected,
            "detections": detections,
            "count": len(detections),
        }


class BinaryClassifyInferencer(BaseInferencer):
    """Generic binary classification inferencer (handwriting, id_card, etc.)."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out   = outputs[0].flatten()
        exp   = np.exp(out - out.max())
        prob  = (exp / exp.sum()).tolist()
        top_k = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {
            "top_class": top_k[0][0],
            "top_score": round(top_k[0][1], 4),
            "all_scores": [round(p, 4) for p in prob],
        }


# Registry: capability_name → inferencer class
_REGISTRY: dict[str, type[BaseInferencer]] = {
    "recapture_detect":  RecaptureDetectInferencer,
    "face_detect":       FaceDetectInferencer,
    "handwriting_reco":  BinaryClassifyInferencer,
    "id_card_classify":  BinaryClassifyInferencer,
}


def get_inferencer(capability: str, model_dir: str) -> BaseInferencer:
    cls = _REGISTRY.get(capability, BinaryClassifyInferencer)
    return cls(model_dir)
