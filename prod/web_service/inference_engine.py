"""Production inference engine — Python layer wrapping ORT (and optionally C runtime).

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

import numpy as np


class ProdInferenceEngine:
    """Python-level inference engine using ONNXRuntime.

    Used when libai_runtime.so is not available (pure Python fallback).
    Production deployments with compiled SO use the C Runtime path.
    """

    def __init__(self, capability: str, model_dir: str) -> None:
        self.capability = capability
        self.model_dir  = model_dir

        manifest_path = os.path.join(model_dir, "manifest.json")
        with open(manifest_path, encoding="utf-8") as f:
            self.manifest = json.load(f)
        self.version = self.manifest.get("model_version", "unknown")

        preprocess_path = os.path.join(model_dir, "preprocess.json")
        self._preprocess_cfg: dict = {}
        if os.path.exists(preprocess_path):
            with open(preprocess_path, encoding="utf-8") as f:
                self._preprocess_cfg = json.load(f)

        model_path = os.path.join(model_dir, "model.onnx")
        self._session = None
        if os.path.exists(model_path):
            try:
                import onnxruntime as ort  # type: ignore

                backend = os.getenv("AI_BACKEND", "auto")
                if backend in ("onnxruntime-gpu", "auto"):
                    providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
                else:
                    providers = ["CPUExecutionProvider"]
                avail = ort.get_available_providers()
                providers = [p for p in providers if p in avail]
                self._session = ort.InferenceSession(model_path, providers=providers)
                self._input_name = self._session.get_inputs()[0].name
            except Exception as exc:
                import sys
                print(f"[{capability}] ORT load failed: {exc}", file=sys.stderr)

    def _preprocess(self, bgr_image: np.ndarray) -> np.ndarray:
        import cv2  # type: ignore

        cfg = self._preprocess_cfg.get("resize", {})
        w   = int(cfg.get("width", 224))
        h   = int(cfg.get("height", 224))
        img = cv2.resize(bgr_image, (w, h))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        mean = np.array(self._preprocess_cfg.get("mean", [0.485, 0.456, 0.406]), dtype=np.float32).reshape(1,1,3)
        std  = np.array(self._preprocess_cfg.get("std",  [0.229, 0.224, 0.225]), dtype=np.float32).reshape(1,1,3)
        img  = (img - mean) / std
        return img.transpose(2, 0, 1)[np.newaxis]  # NCHW

    def infer(self, bgr_image: np.ndarray, options: dict | None = None) -> dict[str, Any]:
        t0 = time.perf_counter()

        if self._session is None:
            # Stub result
            return {
                "is_recaptured": False,
                "score_genuine": 0.9,
                "score_recaptured": 0.1,
                "note": "stub_no_model",
                "infer_time_ms": 0.0,
            }

        tensor = self._preprocess(bgr_image)
        outputs = self._session.run(None, {self._input_name: tensor})
        elapsed = (time.perf_counter() - t0) * 1000.0

        result = self._postprocess(outputs, options or {})
        result["infer_time_ms"] = round(elapsed, 2)
        return result

    def _postprocess(self, outputs: list[np.ndarray], options: dict) -> dict[str, Any]:
        threshold = float(options.get("threshold", self.manifest.get("threshold", 0.5)))
        cap = self.capability

        if cap == "recapture_detect":
            out = outputs[0].flatten()
            if len(out) >= 2:
                exp  = np.exp(out - out.max())
                prob = exp / exp.sum()
                sg, sr = float(prob[0]), float(prob[1])
            else:
                sr = float(1 / (1 + np.exp(-out[0])))
                sg = 1.0 - sr
            is_recap = sr > threshold
            return {
                "is_recaptured":    is_recap,
                "label":            "recaptured" if is_recap else "genuine",
                "score_genuine":    round(sg, 4),
                "score_recaptured": round(sr, 4),
            }

        elif cap == "face_detect":
            bbox = outputs[0].flatten().tolist() if len(outputs) > 0 else [0,0,1,1]
            conf_raw = outputs[1].flatten() if len(outputs) > 1 else np.array([0.9])
            conf = float(1 / (1 + np.exp(-conf_raw[0])))
            dets = []
            if conf > threshold and len(bbox) >= 4:
                dets.append({
                    "label": "face",
                    "confidence": round(conf, 4),
                    "bbox": {"x1": round(bbox[0], 4), "y1": round(bbox[1], 4),
                             "x2": round(bbox[2], 4), "y2": round(bbox[3], 4)},
                })
            return {"face_detected": bool(dets), "detections": dets, "count": len(dets)}

        else:
            # Generic classification
            out  = outputs[0].flatten()
            exp  = np.exp(out - out.max())
            prob = (exp / exp.sum()).tolist()
            top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
            return {
                "top_class": top[0][0],
                "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob],
            }
