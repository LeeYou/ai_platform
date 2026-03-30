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


class DesktopRecaptureDetectInferencer(BaseInferencer):
    """桌面翻拍检测 — EfficientNet-B0 二分类（real / fake）."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out = outputs[0].flatten()
        if len(out) >= 1:
            # Single logit → sigmoid = P(fake)
            score_fake = float(1 / (1 + np.exp(-out[0])))
            score_real = 1.0 - score_fake
        else:
            score_real = score_fake = 0.5

        is_fake = score_fake > 0.5
        return {
            "is_fake": is_fake,
            "label": "fake" if is_fake else "real",
            "score_real": round(score_real, 4),
            "score_fake": round(score_fake, 4),
        }


class FaceDetectInferencer(BaseInferencer):
    """人脸检测 — YOLOv8 multi-face detection with NMS."""

    LABELS = ["face", "occluded_face"]
    CONF_THRESHOLD = 0.25
    IOU_THRESHOLD = 0.45

    def _preprocess(self, bgr_image: np.ndarray) -> np.ndarray:
        """Letterbox resize to 640×640, /255.0, NCHW."""
        import cv2  # type: ignore

        w, h = self.input_size
        ih, iw = bgr_image.shape[:2]
        scale = min(w / iw, h / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        resized = cv2.resize(bgr_image, (nw, nh))
        canvas = np.full((h, w, 3), 114, dtype=np.uint8)
        dx, dy = (w - nw) // 2, (h - nh) // 2
        canvas[dy:dy + nh, dx:dx + nw] = resized
        img = cv2.cvtColor(canvas, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        # Store letterbox params for coordinate mapping
        self._lb_scale = scale
        self._lb_dx = dx
        self._lb_dy = dy
        return img.transpose(2, 0, 1)[np.newaxis]  # NCHW

    @staticmethod
    def _iou(box_a: np.ndarray, box_b: np.ndarray) -> float:
        x1 = max(box_a[0], box_b[0])
        y1 = max(box_a[1], box_b[1])
        x2 = min(box_a[2], box_b[2])
        y2 = min(box_a[3], box_b[3])
        inter = max(0, x2 - x1) * max(0, y2 - y1)
        area_a = (box_a[2] - box_a[0]) * (box_a[3] - box_a[1])
        area_b = (box_b[2] - box_b[0]) * (box_b[3] - box_b[1])
        union = area_a + area_b - inter
        return inter / union if union > 0 else 0.0

    def _nms(self, boxes: np.ndarray, scores: np.ndarray) -> list[int]:
        """Greedy NMS, returns kept indices."""
        order = scores.argsort()[::-1]
        keep: list[int] = []
        while len(order) > 0:
            i = order[0]
            keep.append(int(i))
            if len(order) == 1:
                break
            remaining = order[1:]
            ious = np.array([self._iou(boxes[i], boxes[j]) for j in remaining])
            order = remaining[ious < self.IOU_THRESHOLD]
        return keep

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # YOLOv8 output: [1, num_classes+4, 8400] or [1, 8400, num_classes+4]
        raw = outputs[0]
        if raw.ndim == 3:
            raw = raw[0]  # remove batch dim → [C+4, 8400] or [8400, C+4]

        # Detect layout: if shape[0] < shape[1], it's [C+4, 8400], transpose
        if raw.shape[0] < raw.shape[1]:
            raw = raw.T  # → [8400, C+4]

        num_det = raw.shape[0]
        num_classes = raw.shape[1] - 4
        if num_classes < 1:
            num_classes = 2

        # Parse cx, cy, w, h and class scores
        cx = raw[:, 0]
        cy = raw[:, 1]
        w = raw[:, 2]
        h = raw[:, 3]
        class_scores = raw[:, 4:4 + num_classes]

        # Convert to x1, y1, x2, y2 (in model input space 640×640)
        x1 = cx - w / 2
        y1 = cy - h / 2
        x2 = cx + w / 2
        y2 = cy + h / 2
        boxes = np.stack([x1, y1, x2, y2], axis=1)

        # Get best class per detection
        class_ids = class_scores.argmax(axis=1)
        max_scores = class_scores.max(axis=1)

        # Filter by confidence
        mask = max_scores > self.CONF_THRESHOLD
        boxes = boxes[mask]
        max_scores = max_scores[mask]
        class_ids = class_ids[mask]

        # NMS
        if len(boxes) > 0:
            keep = self._nms(boxes, max_scores)
            boxes = boxes[keep]
            max_scores = max_scores[keep]
            class_ids = class_ids[keep]

        # Map back to original image coordinates
        scale = getattr(self, "_lb_scale", 1.0)
        dx = getattr(self, "_lb_dx", 0)
        dy = getattr(self, "_lb_dy", 0)

        detections = []
        for i in range(len(boxes)):
            bx1 = (float(boxes[i][0]) - dx) / scale
            by1 = (float(boxes[i][1]) - dy) / scale
            bx2 = (float(boxes[i][2]) - dx) / scale
            by2 = (float(boxes[i][3]) - dy) / scale
            cid = int(class_ids[i])
            label = self.LABELS[cid] if cid < len(self.LABELS) else f"class_{cid}"
            detections.append({
                "bbox": [round(bx1, 2), round(by1, 2), round(bx2, 2), round(by2, 2)],
                "confidence": round(float(max_scores[i]), 4),
                "label": label,
                "class_id": cid,
            })

        return {
            "face_detected": len(detections) > 0,
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



# ── Auto-generated capability inferencer stubs ─────────────────────────────

class FaceRecognitionInferencer(BaseInferencer):
    """face_recognition — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        vec = outputs[0].flatten().tolist()
        norm = float(np.linalg.norm(outputs[0]))
        if norm > 1e-8:
            vec = (outputs[0].flatten() / norm).tolist()
        return {"embedding": [round(v, 6) for v in vec], "dim": len(vec)}


class FaceVerifyInferencer(BaseInferencer):
    """face_verify — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        score = float(outputs[0].flatten()[0])
        score = float(1 / (1 + np.exp(-score))) if abs(score) > 1 else max(0.0, min(1.0, score))
        return {"score": round(score, 4), "label": "positive" if score > 0.5 else "negative"}


class FaceLivenessSilentInferencer(BaseInferencer):
    """face_liveness_silent — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out = outputs[0].flatten()
        if len(out) >= 2:
            exp = np.exp(out - out.max()); prob = exp / exp.sum()
            s0, s1 = float(prob[0]), float(prob[1])
        else:
            s1 = float(1 / (1 + np.exp(-out[0]))); s0 = 1.0 - s1
        return {"is_positive": s1 > 0.5, "score_positive": round(s1, 4), "score_negative": round(s0, 4)}


class FaceLivenessActionInferencer(BaseInferencer):
    """face_liveness_action — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class FaceQualityInferencer(BaseInferencer):
    """face_quality — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        score = float(outputs[0].flatten()[0])
        score = float(1 / (1 + np.exp(-score))) if abs(score) > 1 else max(0.0, min(1.0, score))
        return {"score": round(score, 4), "label": "positive" if score > 0.5 else "negative"}


class FaceLandmarkInferencer(BaseInferencer):
    """face_landmark — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        pts = outputs[0].reshape(-1, 3) if outputs[0].ndim >= 2 else outputs[0].reshape(-1, 2)
        keypoints = []
        for row in pts:
            kp = {"x": round(float(row[0]), 4), "y": round(float(row[1]), 4)}
            if row.shape[0] > 2:
                kp["conf"] = round(float(row[2]), 4)
            keypoints.append(kp)
        return {"keypoints": keypoints, "count": len(keypoints)}


class FaceAttributeInferencer(BaseInferencer):
    """face_attribute — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class FaceBeautifyInferencer(BaseInferencer):
    """face_beautify — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: return processed image as base64 when integrated
        shape = list(outputs[0].shape) if outputs else []
        return {"output_shape": shape, "note": "enhancement stub — real output is image tensor"}


class FaceSwapInferencer(BaseInferencer):
    """face_swap — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: return processed image as base64 when integrated
        shape = list(outputs[0].shape) if outputs else []
        return {"output_shape": shape, "note": "enhancement stub — real output is image tensor"}


class FaceDesensitizeInferencer(BaseInferencer):
    """face_desensitize — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: return processed image as base64 when integrated
        shape = list(outputs[0].shape) if outputs else []
        return {"output_shape": shape, "note": "enhancement stub — real output is image tensor"}


class DeepfakeDetectInferencer(BaseInferencer):
    """deepfake_detect — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out = outputs[0].flatten()
        if len(out) >= 2:
            exp = np.exp(out - out.max()); prob = exp / exp.sum()
            s0, s1 = float(prob[0]), float(prob[1])
        else:
            s1 = float(1 / (1 + np.exp(-out[0]))); s0 = 1.0 - s1
        return {"is_positive": s1 > 0.5, "score_positive": round(s1, 4), "score_negative": round(s0, 4)}


class Face3dReconstructInferencer(BaseInferencer):
    """face_3d_reconstruct — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: return processed image as base64 when integrated
        shape = list(outputs[0].shape) if outputs else []
        return {"output_shape": shape, "note": "enhancement stub — real output is image tensor"}


class PersonDetectInferencer(BaseInferencer):
    """person_detect — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        raw = outputs[0].flatten()
        detections = []
        if len(raw) >= 5:
            for i in range(0, len(raw) - 4, 5):
                conf = float(1 / (1 + np.exp(-raw[i + 4])))
                if conf > 0.5:
                    detections.append({"label": "object", "confidence": round(conf, 4),
                                       "bbox": [round(float(v), 4) for v in raw[i:i+4]]})
        return {"count": len(detections), "detections": detections}


class PoseEstimateInferencer(BaseInferencer):
    """pose_estimate — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        pts = outputs[0].reshape(-1, 3) if outputs[0].ndim >= 2 else outputs[0].reshape(-1, 2)
        keypoints = []
        for row in pts:
            kp = {"x": round(float(row[0]), 4), "y": round(float(row[1]), 4)}
            if row.shape[0] > 2:
                kp["conf"] = round(float(row[2]), 4)
            keypoints.append(kp)
        return {"keypoints": keypoints, "count": len(keypoints)}


class PersonReidInferencer(BaseInferencer):
    """person_reid — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        vec = outputs[0].flatten().tolist()
        norm = float(np.linalg.norm(outputs[0]))
        if norm > 1e-8:
            vec = (outputs[0].flatten() / norm).tolist()
        return {"embedding": [round(v, 6) for v in vec], "dim": len(vec)}


class ActionRecognizeInferencer(BaseInferencer):
    """action_recognize — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class CrowdCountInferencer(BaseInferencer):
    """crowd_count — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        score = float(outputs[0].flatten()[0])
        score = float(1 / (1 + np.exp(-score))) if abs(score) > 1 else max(0.0, min(1.0, score))
        return {"score": round(score, 4), "label": "positive" if score > 0.5 else "negative"}


class GestureRecognizeInferencer(BaseInferencer):
    """gesture_recognize — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class BodyActionRecognizeInferencer(BaseInferencer):
    """body_action_recognize — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class ImageClassifyInferencer(BaseInferencer):
    """image_classify — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class ObjectDetectInferencer(BaseInferencer):
    """object_detect — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        raw = outputs[0].flatten()
        detections = []
        if len(raw) >= 5:
            for i in range(0, len(raw) - 4, 5):
                conf = float(1 / (1 + np.exp(-raw[i + 4])))
                if conf > 0.5:
                    detections.append({"label": "object", "confidence": round(conf, 4),
                                       "bbox": [round(float(v), 4) for v in raw[i:i+4]]})
        return {"count": len(detections), "detections": detections}


class SemanticSegmentInferencer(BaseInferencer):
    """semantic_segment — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        mask = outputs[0]
        if mask.ndim >= 3:
            pred = int(np.argmax(mask, axis=0).flatten()[0]) if mask.shape[0] > 1 else 0
        else:
            pred = int(mask.flatten()[0])
        return {"dominant_class": pred, "mask_shape": list(mask.shape)}


class InstanceSegmentInferencer(BaseInferencer):
    """instance_segment — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        mask = outputs[0]
        if mask.ndim >= 3:
            pred = int(np.argmax(mask, axis=0).flatten()[0]) if mask.shape[0] > 1 else 0
        else:
            pred = int(mask.flatten()[0])
        return {"dominant_class": pred, "mask_shape": list(mask.shape)}


class PanopticSegmentInferencer(BaseInferencer):
    """panoptic_segment — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        mask = outputs[0]
        if mask.ndim >= 3:
            pred = int(np.argmax(mask, axis=0).flatten()[0]) if mask.shape[0] > 1 else 0
        else:
            pred = int(mask.flatten()[0])
        return {"dominant_class": pred, "mask_shape": list(mask.shape)}


class ImageSuperResInferencer(BaseInferencer):
    """image_super_res — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: return processed image as base64 when integrated
        shape = list(outputs[0].shape) if outputs else []
        return {"output_shape": shape, "note": "enhancement stub — real output is image tensor"}


class ImageDehazeInferencer(BaseInferencer):
    """image_dehaze — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: return processed image as base64 when integrated
        shape = list(outputs[0].shape) if outputs else []
        return {"output_shape": shape, "note": "enhancement stub — real output is image tensor"}


class ImageDenoiseInferencer(BaseInferencer):
    """image_denoise — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: return processed image as base64 when integrated
        shape = list(outputs[0].shape) if outputs else []
        return {"output_shape": shape, "note": "enhancement stub — real output is image tensor"}


class ImageInpaintInferencer(BaseInferencer):
    """image_inpaint — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: return processed image as base64 when integrated
        shape = list(outputs[0].shape) if outputs else []
        return {"output_shape": shape, "note": "enhancement stub — real output is image tensor"}


class ImageEnhanceInferencer(BaseInferencer):
    """image_enhance — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: return processed image as base64 when integrated
        shape = list(outputs[0].shape) if outputs else []
        return {"output_shape": shape, "note": "enhancement stub — real output is image tensor"}


class WatermarkExtractInferencer(BaseInferencer):
    """watermark_extract — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: return processed image as base64 when integrated
        shape = list(outputs[0].shape) if outputs else []
        return {"output_shape": shape, "note": "enhancement stub — real output is image tensor"}


class ImageRetrievalInferencer(BaseInferencer):
    """image_retrieval — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        vec = outputs[0].flatten().tolist()
        norm = float(np.linalg.norm(outputs[0]))
        if norm > 1e-8:
            vec = (outputs[0].flatten() / norm).tolist()
        return {"embedding": [round(v, 6) for v in vec], "dim": len(vec)}


class ImageTamperDetectInferencer(BaseInferencer):
    """image_tamper_detect — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out = outputs[0].flatten()
        if len(out) >= 2:
            exp = np.exp(out - out.max()); prob = exp / exp.sum()
            s0, s1 = float(prob[0]), float(prob[1])
        else:
            s1 = float(1 / (1 + np.exp(-out[0]))); s0 = 1.0 - s1
        return {"is_positive": s1 > 0.5, "score_positive": round(s1, 4), "score_negative": round(s0, 4)}


class SceneTextDetectInferencer(BaseInferencer):
    """scene_text_detect — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        raw = outputs[0].flatten()
        detections = []
        if len(raw) >= 5:
            for i in range(0, len(raw) - 4, 5):
                conf = float(1 / (1 + np.exp(-raw[i + 4])))
                if conf > 0.5:
                    detections.append({"label": "object", "confidence": round(conf, 4),
                                       "bbox": [round(float(v), 4) for v in raw[i:i+4]]})
        return {"count": len(detections), "detections": detections}


class LogoRecognizeInferencer(BaseInferencer):
    """logo_recognize — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class ProductRecognizeInferencer(BaseInferencer):
    """product_recognize — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class VehicleDetectInferencer(BaseInferencer):
    """vehicle_detect — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        raw = outputs[0].flatten()
        detections = []
        if len(raw) >= 5:
            for i in range(0, len(raw) - 4, 5):
                conf = float(1 / (1 + np.exp(-raw[i + 4])))
                if conf > 0.5:
                    detections.append({"label": "object", "confidence": round(conf, 4),
                                       "bbox": [round(float(v), 4) for v in raw[i:i+4]]})
        return {"count": len(detections), "detections": detections}


class PlateRecognizeInferencer(BaseInferencer):
    """plate_recognize — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class VehicleAttributeInferencer(BaseInferencer):
    """vehicle_attribute — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class OcrGeneralInferencer(BaseInferencer):
    """ocr_general — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class OcrPrintInferencer(BaseInferencer):
    """ocr_print — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class OcrHandwritingInferencer(BaseInferencer):
    """ocr_handwriting — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class OcrSignatureInferencer(BaseInferencer):
    """ocr_signature — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class OcrTableInferencer(BaseInferencer):
    """ocr_table — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class OcrInvoiceInferencer(BaseInferencer):
    """ocr_invoice — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class OcrBankCardInferencer(BaseInferencer):
    """ocr_bank_card — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class OcrBusinessLicenseInferencer(BaseInferencer):
    """ocr_business_license — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class OcrVehicleLicenseInferencer(BaseInferencer):
    """ocr_vehicle_license — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class OcrDriverLicenseInferencer(BaseInferencer):
    """ocr_driver_license — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class IdCardFrontDetectInferencer(BaseInferencer):
    """id_card_front_detect — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        raw = outputs[0].flatten()
        detections = []
        if len(raw) >= 5:
            for i in range(0, len(raw) - 4, 5):
                conf = float(1 / (1 + np.exp(-raw[i + 4])))
                if conf > 0.5:
                    detections.append({"label": "object", "confidence": round(conf, 4),
                                       "bbox": [round(float(v), 4) for v in raw[i:i+4]]})
        return {"count": len(detections), "detections": detections}


class IdCardBackDetectInferencer(BaseInferencer):
    """id_card_back_detect — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        raw = outputs[0].flatten()
        detections = []
        if len(raw) >= 5:
            for i in range(0, len(raw) - 4, 5):
                conf = float(1 / (1 + np.exp(-raw[i + 4])))
                if conf > 0.5:
                    detections.append({"label": "object", "confidence": round(conf, 4),
                                       "bbox": [round(float(v), 4) for v in raw[i:i+4]]})
        return {"count": len(detections), "detections": detections}


class IdCardOcrInferencer(BaseInferencer):
    """id_card_ocr — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class DocClassifyInferencer(BaseInferencer):
    """doc_classify — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class PassportCnOcrInferencer(BaseInferencer):
    """passport_cn_ocr — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class PassportIntlOcrInferencer(BaseInferencer):
    """passport_intl_ocr — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class HouseholdRegisterOcrInferencer(BaseInferencer):
    """household_register_ocr — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class SocialSecurityOcrInferencer(BaseInferencer):
    """social_security_ocr — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class HkMacaoPermitOcrInferencer(BaseInferencer):
    """hk_macao_permit_ocr — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class DocRectifyInferencer(BaseInferencer):
    """doc_rectify — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: return processed image as base64 when integrated
        shape = list(outputs[0].shape) if outputs else []
        return {"output_shape": shape, "note": "enhancement stub — real output is image tensor"}


class SealRecognizeInferencer(BaseInferencer):
    """seal_recognize — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        raw = outputs[0].flatten()
        detections = []
        if len(raw) >= 5:
            for i in range(0, len(raw) - 4, 5):
                conf = float(1 / (1 + np.exp(-raw[i + 4])))
                if conf > 0.5:
                    detections.append({"label": "object", "confidence": round(conf, 4),
                                       "bbox": [round(float(v), 4) for v in raw[i:i+4]]})
        return {"count": len(detections), "detections": detections}


class AsrInferencer(BaseInferencer):
    """asr — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real speech decoder / text output
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class TtsInferencer(BaseInferencer):
    """tts — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real speech decoder / text output
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class VoiceprintVerifyInferencer(BaseInferencer):
    """voiceprint_verify — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        score = float(outputs[0].flatten()[0])
        score = float(1 / (1 + np.exp(-score))) if abs(score) > 1 else max(0.0, min(1.0, score))
        return {"score": round(score, 4), "label": "positive" if score > 0.5 else "negative"}


class VoiceprintSearchInferencer(BaseInferencer):
    """voiceprint_search — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        vec = outputs[0].flatten().tolist()
        norm = float(np.linalg.norm(outputs[0]))
        if norm > 1e-8:
            vec = (outputs[0].flatten() / norm).tolist()
        return {"embedding": [round(v, 6) for v in vec], "dim": len(vec)}


class VoiceLivenessInferencer(BaseInferencer):
    """voice_liveness — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out = outputs[0].flatten()
        if len(out) >= 2:
            exp = np.exp(out - out.max()); prob = exp / exp.sum()
            s0, s1 = float(prob[0]), float(prob[1])
        else:
            s1 = float(1 / (1 + np.exp(-out[0]))); s0 = 1.0 - s1
        return {"is_positive": s1 > 0.5, "score_positive": round(s1, 4), "score_negative": round(s0, 4)}


class AudioDenoiseInferencer(BaseInferencer):
    """audio_denoise — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real speech decoder / text output
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class VocalSeparateInferencer(BaseInferencer):
    """vocal_separate — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real speech decoder / text output
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class LanguageIdentifyInferencer(BaseInferencer):
    """language_identify — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class SpeechEmotionInferencer(BaseInferencer):
    """speech_emotion — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class AudioFingerprintInferencer(BaseInferencer):
    """audio_fingerprint — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        vec = outputs[0].flatten().tolist()
        norm = float(np.linalg.norm(outputs[0]))
        if norm > 1e-8:
            vec = (outputs[0].flatten() / norm).tolist()
        return {"embedding": [round(v, 6) for v in vec], "dim": len(vec)}


class AsrPunctRestoreInferencer(BaseInferencer):
    """asr_punct_restore — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real speech decoder / text output
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class SpeakerDiarizeInferencer(BaseInferencer):
    """speaker_diarize — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real speech decoder / text output
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class TextSegmentInferencer(BaseInferencer):
    """text_segment — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real text decoder
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class PosTagInferencer(BaseInferencer):
    """pos_tag — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real text decoder
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class NerInferencer(BaseInferencer):
    """ner — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real text decoder
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class SentimentAnalyzeInferencer(BaseInferencer):
    """sentiment_analyze — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class TextClassifyInferencer(BaseInferencer):
    """text_classify — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class TextSimilarityInferencer(BaseInferencer):
    """text_similarity — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        score = float(outputs[0].flatten()[0])
        score = float(1 / (1 + np.exp(-score))) if abs(score) > 1 else max(0.0, min(1.0, score))
        return {"score": round(score, 4), "label": "positive" if score > 0.5 else "negative"}


class KeywordExtractInferencer(BaseInferencer):
    """keyword_extract — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real text decoder
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class TextSummarizeInferencer(BaseInferencer):
    """text_summarize — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real text decoder
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class TextCorrectInferencer(BaseInferencer):
    """text_correct — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real text decoder
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class SensitiveDetectInferencer(BaseInferencer):
    """sensitive_detect — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class ContentComplianceInferencer(BaseInferencer):
    """content_compliance — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class IntentRecognizeInferencer(BaseInferencer):
    """intent_recognize — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class SlotFillInferencer(BaseInferencer):
    """slot_fill — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real text decoder
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class EntityLinkInferencer(BaseInferencer):
    """entity_link — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        vec = outputs[0].flatten().tolist()
        norm = float(np.linalg.norm(outputs[0]))
        if norm > 1e-8:
            vec = (outputs[0].flatten() / norm).tolist()
        return {"embedding": [round(v, 6) for v in vec], "dim": len(vec)}


class TextExtractInferencer(BaseInferencer):
    """text_extract — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real text decoder
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class FormExtractInferencer(BaseInferencer):
    """form_extract — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real CTC/attention decoder
        raw = outputs[0].flatten().tolist()
        return {"text_blocks": [{"text": "TODO", "confidence": round(float(max(raw)) if raw else 0.0, 4)}],
                "raw_output_len": len(raw)}


class ContractExtractInferencer(BaseInferencer):
    """contract_extract — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real text decoder
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class DocClassifyRpaInferencer(BaseInferencer):
    """doc_classify_rpa — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class EsealDetectInferencer(BaseInferencer):
    """eseal_detect — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        raw = outputs[0].flatten()
        detections = []
        if len(raw) >= 5:
            for i in range(0, len(raw) - 4, 5):
                conf = float(1 / (1 + np.exp(-raw[i + 4])))
                if conf > 0.5:
                    detections.append({"label": "object", "confidence": round(conf, 4),
                                       "bbox": [round(float(v), 4) for v in raw[i:i+4]]})
        return {"count": len(detections), "detections": detections}


class EsealVerifyInferencer(BaseInferencer):
    """eseal_verify — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out = outputs[0].flatten()
        if len(out) >= 2:
            exp = np.exp(out - out.max()); prob = exp / exp.sum()
            s0, s1 = float(prob[0]), float(prob[1])
        else:
            s1 = float(1 / (1 + np.exp(-out[0]))); s0 = 1.0 - s1
        return {"is_positive": s1 > 0.5, "score_positive": round(s1, 4), "score_negative": round(s0, 4)}


class SignatureCompareInferencer(BaseInferencer):
    """signature_compare — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        score = float(outputs[0].flatten()[0])
        score = float(1 / (1 + np.exp(-score))) if abs(score) > 1 else max(0.0, min(1.0, score))
        return {"score": round(score, 4), "label": "positive" if score > 0.5 else "negative"}


class BillVerifyInferencer(BaseInferencer):
    """bill_verify — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out = outputs[0].flatten()
        if len(out) >= 2:
            exp = np.exp(out - out.max()); prob = exp / exp.sum()
            s0, s1 = float(prob[0]), float(prob[1])
        else:
            s1 = float(1 / (1 + np.exp(-out[0]))); s0 = 1.0 - s1
        return {"is_positive": s1 > 0.5, "score_positive": round(s1, 4), "score_negative": round(s0, 4)}


class LivenessAntiAttackInferencer(BaseInferencer):
    """liveness_anti_attack — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out  = outputs[0].flatten()
        exp  = np.exp(out - out.max()); prob = (exp / exp.sum()).tolist()
        top  = sorted(enumerate(prob), key=lambda x: x[1], reverse=True)
        return {"top_class": top[0][0], "top_score": round(top[0][1], 4),
                "all_scores": [round(p, 4) for p in prob]}


class VideoFrameExtractInferencer(BaseInferencer):
    """video_frame_extract — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        return {"result": "TODO", "note": "video capability — provide frame tensors via batch API"}


class VideoTrackInferencer(BaseInferencer):
    """video_track — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        return {"result": "TODO", "note": "video capability — provide frame tensors via batch API"}


class VideoCondenseInferencer(BaseInferencer):
    """video_condense — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        return {"result": "TODO", "note": "video capability — provide frame tensors via batch API"}


class VideoSummarizeInferencer(BaseInferencer):
    """video_summarize — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        return {"result": "TODO", "note": "video capability — provide frame tensors via batch API"}


class VideoTamperDetectInferencer(BaseInferencer):
    """video_tamper_detect — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        out = outputs[0].flatten()
        if len(out) >= 2:
            exp = np.exp(out - out.max()); prob = exp / exp.sum()
            s0, s1 = float(prob[0]), float(prob[1])
        else:
            s1 = float(1 / (1 + np.exp(-out[0]))); s0 = 1.0 - s1
        return {"is_positive": s1 > 0.5, "score_positive": round(s1, 4), "score_negative": round(s0, 4)}


class ContractSummaryInferencer(BaseInferencer):
    """contract_summary — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real text decoder
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class ContractSignLocateInferencer(BaseInferencer):
    """contract_sign_locate — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        raw = outputs[0].flatten()
        detections = []
        if len(raw) >= 5:
            for i in range(0, len(raw) - 4, 5):
                conf = float(1 / (1 + np.exp(-raw[i + 4])))
                if conf > 0.5:
                    detections.append({"label": "object", "confidence": round(conf, 4),
                                       "bbox": [round(float(v), 4) for v in raw[i:i+4]]})
        return {"count": len(detections), "detections": detections}


class ContractAmountInferencer(BaseInferencer):
    """contract_amount — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real text decoder
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class ContractPartyInferencer(BaseInferencer):
    """contract_party — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        # TODO: replace with real text decoder
        return {"result": "TODO", "raw_output_len": int(outputs[0].size) if outputs else 0}


class ContractSealDetectInferencer(BaseInferencer):
    """contract_seal_detect — stub inferencer."""

    def _postprocess(self, outputs: list[np.ndarray]) -> dict[str, Any]:
        raw = outputs[0].flatten()
        detections = []
        if len(raw) >= 5:
            for i in range(0, len(raw) - 4, 5):
                conf = float(1 / (1 + np.exp(-raw[i + 4])))
                if conf > 0.5:
                    detections.append({"label": "object", "confidence": round(conf, 4),
                                       "bbox": [round(float(v), 4) for v in raw[i:i+4]]})
        return {"count": len(detections), "detections": detections}


# Registry: capability_name → inferencer class
_REGISTRY: dict[str, type[BaseInferencer]] = {
    "recapture_detect":  RecaptureDetectInferencer,
    "desktop_recapture_detect": DesktopRecaptureDetectInferencer,
    "face_detect":       FaceDetectInferencer,
    "handwriting_reco":  BinaryClassifyInferencer,
    "id_card_classify":  BinaryClassifyInferencer,

    # Auto-generated entries
    "face_recognition": FaceRecognitionInferencer,
    "face_verify": FaceVerifyInferencer,
    "face_liveness_silent": FaceLivenessSilentInferencer,
    "face_liveness_action": FaceLivenessActionInferencer,
    "face_quality": FaceQualityInferencer,
    "face_landmark": FaceLandmarkInferencer,
    "face_attribute": FaceAttributeInferencer,
    "face_beautify": FaceBeautifyInferencer,
    "face_swap": FaceSwapInferencer,
    "face_desensitize": FaceDesensitizeInferencer,
    "deepfake_detect": DeepfakeDetectInferencer,
    "face_3d_reconstruct": Face3dReconstructInferencer,
    "person_detect": PersonDetectInferencer,
    "pose_estimate": PoseEstimateInferencer,
    "person_reid": PersonReidInferencer,
    "action_recognize": ActionRecognizeInferencer,
    "crowd_count": CrowdCountInferencer,
    "gesture_recognize": GestureRecognizeInferencer,
    "body_action_recognize": BodyActionRecognizeInferencer,
    "image_classify": ImageClassifyInferencer,
    "object_detect": ObjectDetectInferencer,
    "semantic_segment": SemanticSegmentInferencer,
    "instance_segment": InstanceSegmentInferencer,
    "panoptic_segment": PanopticSegmentInferencer,
    "image_super_res": ImageSuperResInferencer,
    "image_dehaze": ImageDehazeInferencer,
    "image_denoise": ImageDenoiseInferencer,
    "image_inpaint": ImageInpaintInferencer,
    "image_enhance": ImageEnhanceInferencer,
    "watermark_extract": WatermarkExtractInferencer,
    "image_retrieval": ImageRetrievalInferencer,
    "image_tamper_detect": ImageTamperDetectInferencer,
    "scene_text_detect": SceneTextDetectInferencer,
    "logo_recognize": LogoRecognizeInferencer,
    "product_recognize": ProductRecognizeInferencer,
    "vehicle_detect": VehicleDetectInferencer,
    "plate_recognize": PlateRecognizeInferencer,
    "vehicle_attribute": VehicleAttributeInferencer,
    "ocr_general": OcrGeneralInferencer,
    "ocr_print": OcrPrintInferencer,
    "ocr_handwriting": OcrHandwritingInferencer,
    "ocr_signature": OcrSignatureInferencer,
    "ocr_table": OcrTableInferencer,
    "ocr_invoice": OcrInvoiceInferencer,
    "ocr_bank_card": OcrBankCardInferencer,
    "ocr_business_license": OcrBusinessLicenseInferencer,
    "ocr_vehicle_license": OcrVehicleLicenseInferencer,
    "ocr_driver_license": OcrDriverLicenseInferencer,
    "id_card_front_detect": IdCardFrontDetectInferencer,
    "id_card_back_detect": IdCardBackDetectInferencer,
    "id_card_ocr": IdCardOcrInferencer,
    "doc_classify": DocClassifyInferencer,
    "passport_cn_ocr": PassportCnOcrInferencer,
    "passport_intl_ocr": PassportIntlOcrInferencer,
    "household_register_ocr": HouseholdRegisterOcrInferencer,
    "social_security_ocr": SocialSecurityOcrInferencer,
    "hk_macao_permit_ocr": HkMacaoPermitOcrInferencer,
    "doc_rectify": DocRectifyInferencer,
    "seal_recognize": SealRecognizeInferencer,
    "asr": AsrInferencer,
    "tts": TtsInferencer,
    "voiceprint_verify": VoiceprintVerifyInferencer,
    "voiceprint_search": VoiceprintSearchInferencer,
    "voice_liveness": VoiceLivenessInferencer,
    "audio_denoise": AudioDenoiseInferencer,
    "vocal_separate": VocalSeparateInferencer,
    "language_identify": LanguageIdentifyInferencer,
    "speech_emotion": SpeechEmotionInferencer,
    "audio_fingerprint": AudioFingerprintInferencer,
    "asr_punct_restore": AsrPunctRestoreInferencer,
    "speaker_diarize": SpeakerDiarizeInferencer,
    "text_segment": TextSegmentInferencer,
    "pos_tag": PosTagInferencer,
    "ner": NerInferencer,
    "sentiment_analyze": SentimentAnalyzeInferencer,
    "text_classify": TextClassifyInferencer,
    "text_similarity": TextSimilarityInferencer,
    "keyword_extract": KeywordExtractInferencer,
    "text_summarize": TextSummarizeInferencer,
    "text_correct": TextCorrectInferencer,
    "sensitive_detect": SensitiveDetectInferencer,
    "content_compliance": ContentComplianceInferencer,
    "intent_recognize": IntentRecognizeInferencer,
    "slot_fill": SlotFillInferencer,
    "entity_link": EntityLinkInferencer,
    "text_extract": TextExtractInferencer,
    "form_extract": FormExtractInferencer,
    "contract_extract": ContractExtractInferencer,
    "doc_classify_rpa": DocClassifyRpaInferencer,
    "eseal_detect": EsealDetectInferencer,
    "eseal_verify": EsealVerifyInferencer,
    "signature_compare": SignatureCompareInferencer,
    "bill_verify": BillVerifyInferencer,
    "liveness_anti_attack": LivenessAntiAttackInferencer,
    "video_frame_extract": VideoFrameExtractInferencer,
    "video_track": VideoTrackInferencer,
    "video_condense": VideoCondenseInferencer,
    "video_summarize": VideoSummarizeInferencer,
    "video_tamper_detect": VideoTamperDetectInferencer,
    "contract_summary": ContractSummaryInferencer,
    "contract_sign_locate": ContractSignLocateInferencer,
    "contract_amount": ContractAmountInferencer,
    "contract_party": ContractPartyInferencer,
    "contract_seal_detect": ContractSealDetectInferencer,
}


def get_inferencer(capability: str, model_dir: str) -> BaseInferencer:
    cls = _REGISTRY.get(capability, BinaryClassifyInferencer)
    return cls(model_dir)
