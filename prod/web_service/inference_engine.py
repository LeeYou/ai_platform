"""Production inference engine — Python layer wrapping ORT (and optionally C runtime).

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import json
import os
import hashlib
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

        # Validate model checksum if checksum.sha256 exists
        self._validate_model_checksum()

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

    def _validate_model_checksum(self) -> None:
        """Validate model.onnx checksum against checksum.sha256 file.

        Raises RuntimeError if checksum file exists but validation fails.
        This prevents loading corrupted or tampered models.
        """
        checksum_path = os.path.join(self.model_dir, "checksum.sha256")
        model_path = os.path.join(self.model_dir, "model.onnx")

        if not os.path.exists(checksum_path):
            # No checksum file = skip validation (dev/test mode)
            return

        if not os.path.exists(model_path):
            raise RuntimeError(
                f"[{self.capability}] checksum.sha256 exists but model.onnx not found"
            )

        # Read expected checksum
        with open(checksum_path, encoding="utf-8") as f:
            expected_hash = f.read().strip().split()[0]  # Format: "hash  filename"

        # Compute actual checksum
        sha256 = hashlib.sha256()
        with open(model_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                sha256.update(chunk)
        actual_hash = sha256.hexdigest()

        # Verify match
        if actual_hash != expected_hash:
            raise RuntimeError(
                f"[{self.capability}] Model checksum MISMATCH — possible corruption/tampering!\n"
                f"  Expected: {expected_hash}\n"
                f"  Actual:   {actual_hash}\n"
                f"  Model:    {model_path}"
            )

        import sys
        print(f"[{self.capability}] Model checksum verified: {actual_hash[:16]}...", file=sys.stderr)


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
        """Perform inference with detailed performance profiling.

        Returns result dict with added performance metrics:
        - infer_time_ms: Total inference time
        - preprocess_ms: Preprocessing time
        - inference_ms: Model inference time
        - postprocess_ms: Postprocessing time
        """
        t_start = time.perf_counter()

        if self._session is None:
            # Stub result
            return {
                "is_recaptured": False,
                "score_genuine": 0.9,
                "score_recaptured": 0.1,
                "note": "stub_no_model",
                "infer_time_ms": 0.0,
            }

        # Preprocessing
        t_preprocess_start = time.perf_counter()
        tensor = self._preprocess(bgr_image)
        t_preprocess_end = time.perf_counter()
        preprocess_ms = (t_preprocess_end - t_preprocess_start) * 1000.0

        # Inference
        t_inference_start = time.perf_counter()
        outputs = self._session.run(None, {self._input_name: tensor})
        t_inference_end = time.perf_counter()
        inference_ms = (t_inference_end - t_inference_start) * 1000.0

        # Postprocessing
        t_postprocess_start = time.perf_counter()
        result = self._postprocess(outputs, options or {})
        t_postprocess_end = time.perf_counter()
        postprocess_ms = (t_postprocess_end - t_postprocess_start) * 1000.0

        # Add performance metrics
        total_ms = (time.perf_counter() - t_start) * 1000.0
        result["infer_time_ms"] = round(total_ms, 2)
        result["performance"] = {
            "preprocess_ms": round(preprocess_ms, 2),
            "inference_ms": round(inference_ms, 2),
            "postprocess_ms": round(postprocess_ms, 2),
        }

        return result

    def _postprocess(self, outputs: list[np.ndarray], options: dict) -> dict[str, Any]:
        threshold = float(options.get("threshold", self.manifest.get("threshold", 0.5)))
        cap = self.capability

        if cap == "desktop_recapture_detect":
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

        # ── Auto-generated capability postprocessing stubs ──────────────────────────

        elif cap == "face_liveness_silent" or cap == "deepfake_detect" or cap == "image_tamper_detect" or cap == "voice_liveness" or cap == "eseal_verify" or cap == "bill_verify" or cap == "video_tamper_detect":
            out = outputs[0].flatten()
            if len(out) >= 2:
                exp = np.exp(out - out.max()); prob = exp / exp.sum()
                s0, s1 = float(prob[0]), float(prob[1])
            else:
                s1 = float(1 / (1 + np.exp(-out[0]))); s0 = 1.0 - s1
            return {"is_positive": s1 > threshold, "score_positive": round(s1, 4), "score_negative": round(s0, 4)}

        elif cap == "face_verify" or cap == "face_quality" or cap == "crowd_count" or cap == "voiceprint_verify" or cap == "text_similarity" or cap == "signature_compare":
            raw = float(outputs[0].flatten()[0])
            score = float(1 / (1 + np.exp(-raw))) if abs(raw) > 1 else max(0.0, min(1.0, raw))
            return {"score": round(score, 4), "label": "positive" if score > threshold else "negative"}

        elif cap == "face_recognition" or cap == "person_reid" or cap == "image_retrieval" or cap == "voiceprint_search" or cap == "audio_fingerprint" or cap == "entity_link":
            vec = outputs[0].flatten()
            norm = float(np.linalg.norm(vec))
            if norm > 1e-8:
                vec = vec / norm
            return {"embedding": [round(float(v), 6) for v in vec.tolist()], "dim": len(vec)}

        elif cap == "face_landmark" or cap == "pose_estimate":
            pts = outputs[0].reshape(-1, 3) if outputs[0].ndim >= 2 else outputs[0].reshape(-1, 2)
            kps = [{"x": round(float(r[0]),4), "y": round(float(r[1]),4),
                    **({"conf": round(float(r[2]),4)} if r.shape[0]>2 else {})} for r in pts]
            return {"keypoints": kps, "count": len(kps)}

        elif cap == "person_detect" or cap == "object_detect" or cap == "scene_text_detect" or cap == "vehicle_detect" or cap == "id_card_front_detect" or cap == "id_card_back_detect" or cap == "seal_recognize" or cap == "eseal_detect" or cap == "contract_sign_locate" or cap == "contract_seal_detect":
            raw = outputs[0].flatten()
            dets = []
            for i in range(0, len(raw) - 4, 5):
                conf = float(1 / (1 + np.exp(-raw[i + 4])))
                if conf > threshold:
                    dets.append({"label": "object", "confidence": round(conf, 4),
                                 "bbox": [round(float(v), 4) for v in raw[i:i+4]]})
            return {"count": len(dets), "detections": dets}

        elif cap == "plate_recognize" or cap == "ocr_general" or cap == "ocr_print" or cap == "ocr_handwriting" or cap == "ocr_signature" or cap == "ocr_table" or cap == "ocr_invoice" or cap == "ocr_bank_card" or cap == "ocr_business_license" or cap == "ocr_vehicle_license" or cap == "ocr_driver_license" or cap == "id_card_ocr" or cap == "passport_cn_ocr" or cap == "passport_intl_ocr" or cap == "household_register_ocr" or cap == "social_security_ocr" or cap == "hk_macao_permit_ocr" or cap == "form_extract":
            raw = outputs[0].flatten().tolist()
            return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}]}

        elif cap == "semantic_segment" or cap == "instance_segment" or cap == "panoptic_segment":
            mask = outputs[0]
            pred = int(np.argmax(mask, axis=0).flatten()[0]) if mask.ndim>=3 and mask.shape[0]>1 else 0
            return {"dominant_class": pred, "mask_shape": list(mask.shape)}

        elif cap == "face_beautify" or cap == "face_swap" or cap == "face_desensitize" or cap == "face_3d_reconstruct" or cap == "image_super_res" or cap == "image_dehaze" or cap == "image_denoise" or cap == "image_inpaint" or cap == "image_enhance" or cap == "watermark_extract" or cap == "doc_rectify":
            return {"output_shape": list(outputs[0].shape), "note": "enhancement — image tensor output"}

        elif cap == "asr" or cap == "tts" or cap == "audio_denoise" or cap == "vocal_separate" or cap == "asr_punct_restore" or cap == "speaker_diarize":
            return {"result": "TODO", "note": "audio capability stub"}

        elif cap == "face_liveness_action" or cap == "face_attribute" or cap == "action_recognize" or cap == "gesture_recognize" or cap == "body_action_recognize" or cap == "image_classify" or cap == "logo_recognize" or cap == "product_recognize" or cap == "vehicle_attribute" or cap == "doc_classify" or cap == "language_identify" or cap == "speech_emotion" or cap == "text_segment" or cap == "pos_tag" or cap == "ner" or cap == "sentiment_analyze" or cap == "text_classify" or cap == "keyword_extract" or cap == "text_summarize" or cap == "text_correct" or cap == "sensitive_detect" or cap == "content_compliance" or cap == "intent_recognize" or cap == "slot_fill" or cap == "text_extract" or cap == "contract_extract" or cap == "doc_classify_rpa" or cap == "liveness_anti_attack" or cap == "video_frame_extract" or cap == "video_track" or cap == "video_condense" or cap == "video_summarize" or cap == "contract_summary" or cap == "contract_amount" or cap == "contract_party":
            out  = outputs[0].flatten()
            exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
            top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
            return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                    "all_scores": [round(p, 4) for p in prob]}

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
