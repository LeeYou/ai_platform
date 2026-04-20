"""agface 人脸比对的 Python 组合层。

受限于当前 `Ai*` C ABI 只接受"单张 AiImage → AiResult"，无法在一个能力插件
调用内完成"两图 → 分数"的比对。本模块在 prod Python 层做编排：

    image_a, image_b
        │
        ├── (optional) agface_face_detect 取最大人脸的 bbox，裁剪
        │
        ├── agface_face_feature_<variant>.infer → feature_a (L2 normalized)
        ├── agface_face_feature_<variant>.infer → feature_b (L2 normalized)
        │
        └── cosine = dot(feature_a, feature_b)   (两向量已 L2 归一化)
            score  = calibrate_score(cosine)     (0~100，沿用旧 SDK 分段映射)

设计约束：
  - 不依赖 numpy（纯 Python 即可做点积），保持该模块零额外依赖。
  - detector 可选：客户端可以在上游已 crop 好人脸，此时跳过 detector 开销。
  - 所有子能力失败时以 HTTP 语义抛出 HTTPException（由 FastAPI 正确渲染）。

Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
"""

from __future__ import annotations

import logging
import math
from typing import Any, Callable, Iterable

logger = logging.getLogger("prod")

# ---------------------------------------------------------------------------
# 允许的 feature 能力白名单
# ---------------------------------------------------------------------------

ALLOWED_FEATURE_CAPABILITIES: tuple[str, ...] = (
    "agface_face_feature_residual256",
    "agface_face_feature_glint512",
    "agface_face_feature_mobilenet256",
)

# 默认 detector 能力名（可通过参数覆盖）；传 None 则不做检测，直接把整张图喂给 feature
DEFAULT_DETECTOR_CAPABILITY = "agface_face_detect"


# ---------------------------------------------------------------------------
# 分数计算
# ---------------------------------------------------------------------------

def cosine_similarity(vec1: Iterable[float], vec2: Iterable[float]) -> float:
    """Cosine similarity for two equal-length float iterables.

    Works correctly on already L2-normalized vectors (the agface feature
    plugins return L2-normalized features, so this reduces to a dot product),
    as well as on arbitrary non-normalized vectors.
    """
    v1 = list(vec1)
    v2 = list(vec2)
    if not v1 or not v2:
        return 0.0
    if len(v1) != len(v2):
        raise ValueError(
            f"feature dimension mismatch: {len(v1)} vs {len(v2)}"
        )
    dot = 0.0
    n1 = 0.0
    n2 = 0.0
    for a, b in zip(v1, v2):
        dot += a * b
        n1 += a * a
        n2 += b * b
    denom = math.sqrt(n1) * math.sqrt(n2)
    if denom < 1e-8:
        logger.warning("[agface_compare] near-zero norm detected")
        return 0.0
    return dot / denom


def calibrate_score(cosine_sim: float) -> float:
    """Piecewise-linear mapping from cosine similarity [-1, 1] to a score [0, 100].

    Matches old ai_agface SimilarityCalculator:
      (-1, 0)   → [0, 10]
      [0, 0.3)  → [10, 30]
      [0.3, 0.5) → [30, 60]
      [0.5, 0.7) → [60, 85]
      [0.7, 1]  → [85, 100]
    """
    c = cosine_sim
    if c >= 0.7:
        s = 85.0 + (c - 0.7) / 0.3 * 15.0
    elif c >= 0.5:
        s = 60.0 + (c - 0.5) / 0.2 * 25.0
    elif c >= 0.3:
        s = 30.0 + (c - 0.3) / 0.2 * 30.0
    elif c >= 0.0:
        s = 10.0 + c / 0.3 * 20.0
    else:
        # (-1, 0): linear (c+1)/1 * 10  → [0, 10]
        s = max(0.0, (c + 1.0)) * 10.0
    return max(0.0, min(100.0, s))


# ---------------------------------------------------------------------------
# Crop helper
# ---------------------------------------------------------------------------

def _clip(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


def pick_largest_face_bbox(detect_result: dict) -> list[int] | None:
    """Select the largest-area face from an agface_face_detect result dict."""
    faces = (detect_result or {}).get("faces", [])
    if not faces:
        return None
    best = None
    best_area = -1.0
    for f in faces:
        bbox = f.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        _, _, w, h = bbox
        area = float(w) * float(h)
        if area > best_area:
            best_area = area
            best = bbox
    if not best:
        return None
    # Convert to ints and return a copy
    return [int(round(v)) for v in best]


def crop_image_to_bbox(
    image_bytes: bytes,
    decode_fn: Callable[[bytes], Any],
    encode_fn: Callable[[Any], bytes],
    bbox_xywh: list[int],
    margin_ratio: float = 0.15,
) -> bytes:
    """Re-encode `image_bytes` cropped to bbox expanded by `margin_ratio`.

    Args:
        image_bytes: source image (JPEG/PNG bytes).
        decode_fn: callable bytes → np.ndarray (BGR).
        encode_fn: callable np.ndarray → bytes (JPEG).
        bbox_xywh: [x, y, w, h] in pixels of the original image.
        margin_ratio: pad each side by this fraction of the longer bbox side.
    """
    img = decode_fn(image_bytes)
    h_img, w_img = img.shape[:2]
    x, y, w, h = bbox_xywh
    pad = int(round(max(w, h) * margin_ratio))
    x1 = _clip(x - pad, 0, w_img - 1)
    y1 = _clip(y - pad, 0, h_img - 1)
    x2 = _clip(x + w + pad, 1, w_img)
    y2 = _clip(y + h + pad, 1, h_img)
    if x2 <= x1 or y2 <= y1:
        return image_bytes  # degenerate; fallback to original
    cropped = img[y1:y2, x1:x2].copy()
    return encode_fn(cropped)


# ---------------------------------------------------------------------------
# Main compare entry
# ---------------------------------------------------------------------------

def compare_faces(
    image_a_bytes: bytes,
    image_b_bytes: bytes,
    infer_fn: Callable[[str, bytes, dict], dict],
    *,
    feature_capability: str = "agface_face_feature_glint512",
    detector_capability: str | None = DEFAULT_DETECTOR_CAPABILITY,
    decode_fn: Callable[[bytes], Any] | None = None,
    encode_fn: Callable[[Any], bytes] | None = None,
    margin_ratio: float = 0.15,
) -> dict:
    """Run the end-to-end face-compare pipeline and return a result dict.

    Args:
        image_a_bytes / image_b_bytes: uploaded file bytes.
        infer_fn: callable (capability, image_bytes, options) → result_dict,
            typically `_infer_for_pipeline` from main.py.
        feature_capability: one of ALLOWED_FEATURE_CAPABILITIES.
        detector_capability: set to None to skip detection/crop and pass the
            full image directly to the feature extractor.
        decode_fn / encode_fn: image codec functions (only required when a
            detector is used). In prod these are OpenCV-based helpers.
        margin_ratio: padding ratio around detected bbox for the face crop.

    Returns:
        {
            "feature_capability": str,
            "detector_capability": str | None,
            "faces": {"image_a": int, "image_b": int},
            "cosine": float,
            "score": float,                 # 0..100
            "dim": int,
            "feature_a_sample": [float,...],  # first 8 dims for debug
            "feature_b_sample": [float,...],
        }

    Raises:
        ValueError for invalid feature_capability or failed sub-inference.
    """
    if feature_capability not in ALLOWED_FEATURE_CAPABILITIES:
        raise ValueError(
            f"invalid feature_capability '{feature_capability}'; "
            f"allowed: {ALLOWED_FEATURE_CAPABILITIES}"
        )

    face_counts = {"image_a": 0, "image_b": 0}
    crops = {"image_a": image_a_bytes, "image_b": image_b_bytes}

    if detector_capability:
        if decode_fn is None or encode_fn is None:
            raise ValueError("decode_fn/encode_fn required when detector_capability is set")
        for tag, data in (("image_a", image_a_bytes), ("image_b", image_b_bytes)):
            det = infer_fn(detector_capability, data, {})
            faces = (det or {}).get("faces", [])
            face_counts[tag] = len(faces)
            bbox = pick_largest_face_bbox(det)
            if bbox is not None:
                try:
                    crops[tag] = crop_image_to_bbox(
                        data, decode_fn, encode_fn, bbox, margin_ratio=margin_ratio)
                except Exception as exc:
                    logger.warning("[agface_compare] crop failed for %s: %s; using full image",
                                   tag, exc)
                    crops[tag] = data
            else:
                logger.info("[agface_compare] no face detected in %s; feeding full image", tag)

    feat_a = infer_fn(feature_capability, crops["image_a"], {})
    feat_b = infer_fn(feature_capability, crops["image_b"], {})

    vec_a = (feat_a or {}).get("feature")
    vec_b = (feat_b or {}).get("feature")
    if not isinstance(vec_a, list) or not isinstance(vec_b, list):
        raise ValueError("feature plugin did not return a 'feature' array")

    cos = cosine_similarity(vec_a, vec_b)
    score = calibrate_score(cos)

    return {
        "feature_capability": feature_capability,
        "detector_capability": detector_capability,
        "faces": face_counts,
        "cosine": round(cos, 6),
        "score": round(score, 2),
        "dim": len(vec_a),
        "feature_a_sample": [round(v, 6) for v in vec_a[:8]],
        "feature_b_sample": [round(v, 6) for v in vec_b[:8]],
    }
