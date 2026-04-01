"""Base inferencer and ONNXRuntime session helper.

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from typing import Any

import numpy as np


def _load_manifest(model_dir: str) -> dict:
    path = os.path.join(model_dir, "manifest.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_preprocess(model_dir: str) -> dict:
    path = os.path.join(model_dir, "preprocess.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class OrtSession:
    """Thin wrapper around onnxruntime.InferenceSession."""

    def __init__(self, model_path: str) -> None:
        try:
            import onnxruntime as ort  # type: ignore

            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
            available = ort.get_available_providers()
            providers = [p for p in providers if p in available]
            self._session = ort.InferenceSession(model_path, providers=providers)
            self._input_name = self._session.get_inputs()[0].name
        except ImportError:
            self._session = None
            self._input_name = "input"

    def run(self, tensor: np.ndarray) -> list[np.ndarray]:
        if self._session is None:
            # Stub: return random output
            return [np.random.rand(1, 2).astype(np.float32)]
        return self._session.run(None, {self._input_name: tensor})


class BaseInferencer(ABC):
    """Abstract base class for all AI capability inferencers."""

    def __init__(self, model_dir: str) -> None:
        self.model_dir = model_dir
        self.manifest = _load_manifest(model_dir)
        self.preprocess_cfg = _load_preprocess(model_dir)
        model_path = os.path.join(model_dir, "model.onnx")
        self._session = OrtSession(model_path) if os.path.exists(model_path) else None

    @property
    def capability(self) -> str:
        return self.manifest.get("capability", "unknown")

    @property
    def version(self) -> str:
        return self.manifest.get("model_version", "unknown")

    @property
    def input_size(self) -> tuple[int, int]:
        cfg = self.preprocess_cfg.get("resize", {})
        w = cfg.get("width", 224)
        h = cfg.get("height", 224)
        return int(w), int(h)

    @property
    def mean(self) -> list[float]:
        return self.preprocess_cfg.get("mean", [0.485, 0.456, 0.406])

    @property
    def std(self) -> list[float]:
        return self.preprocess_cfg.get("std", [0.229, 0.224, 0.225])

    def _preprocess(self, bgr_image: np.ndarray) -> np.ndarray:
        """Resize, convert BGR→RGB, normalise, NCHW float32."""
        import cv2  # type: ignore

        w, h = self.input_size
        img = cv2.resize(bgr_image, (w, h))
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        mean = np.array(self.mean, dtype=np.float32).reshape(1, 1, 3)
        std  = np.array(self.std,  dtype=np.float32).reshape(1, 1, 3)
        img  = (img - mean) / std
        return img.transpose(2, 0, 1)[np.newaxis]  # NCHW

    def infer(self, bgr_image: np.ndarray) -> dict[str, Any]:
        """Run inference and return structured result dict."""
        t0 = time.perf_counter()
        tensor = self._preprocess(bgr_image)
        outputs = self._session.run(tensor) if self._session else [np.random.rand(1, 2).astype(np.float32)]
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        result = self._postprocess(outputs)
        result["infer_time_ms"] = round(elapsed_ms, 2)
        return result

    @abstractmethod
    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        """Convert raw ORT output tensors to structured result."""
