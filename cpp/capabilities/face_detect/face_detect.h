#ifndef AGILESTAR_FACE_DETECT_H
#define AGILESTAR_FACE_DETECT_H

/**
 * face_detect.h
 * face_detect 能力插件内部头文件
 *
 * 声明 FaceDetectContext 上下文结构和内部辅助函数。
 * 推理引擎：ONNXRuntime C API (onnxruntime_c_api.h)。
 * 模型格式：YOLOv8 多人脸检测，输出 [1, num_classes+4, 8400]。
 */

#include "ai_capability.h"

#include <atomic>
#include <string>
#include <vector>

#if __has_include(<onnxruntime_c_api.h>)
#  include <onnxruntime_c_api.h>
#  define HAS_ORT 1
#else
#  define HAS_ORT 0
#endif

/* --------------------------------------------------------------------------
 * Detection — single bounding-box result in original image coordinates
 * -------------------------------------------------------------------------- */
struct Detection {
    float x1, y1, x2, y2;
    float confidence;
    int   class_id;
};

/* --------------------------------------------------------------------------
 * FaceDetectContext — per-instance state for the face_detect plugin
 * -------------------------------------------------------------------------- */
struct FaceDetectContext {
    std::string model_dir;
    std::string license_path;

    /* Model / inference configuration (from manifest.json / preprocess.json) */
    int   input_width      = 640;
    int   input_height     = 640;
    int   num_classes      = 2;
    float conf_threshold   = 0.25f;
    float nms_threshold    = 0.45f;

    /* Class labels (e.g. "face", "occluded_face") */
    std::vector<std::string> class_labels;

    /* Inference counter for periodic license re-check */
    std::atomic<uint64_t> infer_count{0};

#if HAS_ORT
    const OrtApi*      ort_api          = nullptr;
    OrtEnv*            ort_env          = nullptr;
    OrtSession*        ort_session      = nullptr;
    OrtSessionOptions* ort_session_opts = nullptr;
    OrtAllocator*      ort_allocator    = nullptr;

    /* Input / output names — allocated by the ORT allocator, freed on destroy */
    std::vector<char*> input_names;
    std::vector<char*> output_names;
#endif
};

/* --------------------------------------------------------------------------
 * Internal helper function declarations
 * -------------------------------------------------------------------------- */

/**
 * Letterbox-resize an input image to (target_w × target_h), returning an
 * NCHW float32 tensor normalised to [0, 1].  Grey padding (114/255) fills
 * the border.  The scale factor and padding offsets are written back so the
 * caller can map detections to the original coordinate space.
 */
std::vector<float> fd_preprocess_letterbox(const AiImage* img,
                                           int target_w, int target_h,
                                           float& scale,
                                           float& pad_x, float& pad_y);

/**
 * Decode the raw YOLOv8 output tensor into a vector of detections.
 * Applies a confidence threshold but does NOT apply NMS.
 *
 * @param output_data  Pointer to the raw float buffer
 * @param output_shape Dimension array (e.g. {1, C+4, 8400})
 * @param num_dims     Number of dimensions
 */
std::vector<Detection> fd_postprocess_yolov8(const float* output_data,
                                              const int64_t* output_shape,
                                              int    num_dims,
                                              int    num_classes,
                                              float  conf_threshold,
                                              float  scale,
                                              float  pad_x, float  pad_y,
                                              int    orig_w, int    orig_h);

/**
 * Per-class Non-Maximum Suppression.
 */
std::vector<Detection> fd_nms(std::vector<Detection>& detections,
                              float iou_threshold);

#endif /* AGILESTAR_FACE_DETECT_H */
