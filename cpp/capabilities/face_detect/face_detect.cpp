/**
 * face_detect.cpp
 * face_detect 能力插件 — 多人脸 YOLOv8 检测
 *
 * 实现 ai_capability.h 定义的完整 C ABI 接口。
 * 推理引擎：ONNXRuntime C API (CPU/GPU)。
 * 模型输出：YOLOv8 [1, num_classes+4, 8400]
 *
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#include "face_detect.h"

#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

/* Stringify helper for compile-time macro expansion */
#define STRINGIFY2(x) #x
#define STRINGIFY(x)  STRINGIFY2(x)

// ===========================================================================
// String / memory helpers
// ===========================================================================

static char* _dup(const char* s) {
    if (!s) return nullptr;
    size_t len = std::strlen(s);
    char*  buf = static_cast<char*>(std::malloc(len + 1));
    if (buf) std::memcpy(buf, s, len + 1);
    return buf;
}

static void _set_result(AiResult* result, int32_t code, const char* json,
                         const char* msg = nullptr) {
    if (!result) return;
    result->error_code  = code;
    result->json_result = json ? _dup(json) : nullptr;
    result->result_len  = json ? static_cast<int32_t>(std::strlen(json)) : 0;
    result->error_msg   = msg  ? _dup(msg)  : nullptr;
}

// ===========================================================================
// Minimal JSON helpers (no external dependency)
// ===========================================================================

static bool _read_file(const std::string& path, std::string& out) {
    std::ifstream f(path);
    if (!f.is_open()) return false;
    out.assign((std::istreambuf_iterator<char>(f)),
                std::istreambuf_iterator<char>());
    return true;
}

/** Extract a JSON string value for a given key (flat objects only). */
static std::string _jstr(const std::string& json, const std::string& key) {
    std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return "";
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) return "";
    pos = json.find('"', pos + 1);
    if (pos == std::string::npos) return "";
    auto end = json.find('"', pos + 1);
    if (end == std::string::npos) return "";
    return json.substr(pos + 1, end - pos - 1);
}

/** Extract a JSON numeric value for a given key. */
static double _jnum(const std::string& json, const std::string& key,
                    double default_val = 0.0) {
    std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return default_val;
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) return default_val;
    ++pos;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t')) ++pos;
    if (pos >= json.size()) return default_val;
    try { return std::stod(json.substr(pos)); }
    catch (...) { return default_val; }
}

static int _jint(const std::string& json, const std::string& key,
                 int default_val = 0) {
    return static_cast<int>(_jnum(json, key, default_val));
}

/** Extract a JSON array of strings for a given key. */
static std::vector<std::string> _jstr_array(const std::string& json,
                                             const std::string& key) {
    std::vector<std::string> result;
    std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return result;
    auto arr_start = json.find('[', pos);
    auto arr_end   = json.find(']', arr_start);
    if (arr_start == std::string::npos || arr_end == std::string::npos)
        return result;
    std::string arr = json.substr(arr_start + 1, arr_end - arr_start - 1);
    size_t p = 0;
    while (p < arr.size()) {
        auto q1 = arr.find('"', p);
        if (q1 == std::string::npos) break;
        auto q2 = arr.find('"', q1 + 1);
        if (q2 == std::string::npos) break;
        result.push_back(arr.substr(q1 + 1, q2 - q1 - 1));
        p = q2 + 1;
    }
    return result;
}

// ===========================================================================
// License check (runtime soft check)
// ===========================================================================

static bool _check_license_capability(const std::string& license_path) {
    std::string content;
    if (!_read_file(license_path, content)) return false;
    auto cap_pos = content.find("\"capabilities\"");
    if (cap_pos == std::string::npos) return false;
    auto arr_start = content.find('[', cap_pos);
    auto arr_end   = content.find(']', arr_start);
    if (arr_start == std::string::npos || arr_end == std::string::npos)
        return false;
    std::string arr = content.substr(arr_start, arr_end - arr_start + 1);
    return arr.find("\"face_detect\"") != std::string::npos;
}

// ===========================================================================
// ORT C-API status helper
// ===========================================================================

#if HAS_ORT
static bool _ort_ok(const OrtApi* api, OrtStatus* status, const char* context) {
    if (!status) return true;
    const char* msg = api->GetErrorMessage(status);
    std::fprintf(stderr, "[face_detect] ORT error in %s: %s\n", context, msg);
    api->ReleaseStatus(status);
    return false;
}
#endif

// ===========================================================================
// Letterbox preprocessing: NHWC uint8 → NCHW float32 RGB [0,1]
//
// Maintains aspect ratio, pads remaining area with 114/255.
// ===========================================================================

std::vector<float> fd_preprocess_letterbox(const AiImage* img,
                                           int target_w, int target_h,
                                           float& scale,
                                           float& pad_x, float& pad_y) {
    const int src_w  = img->width;
    const int src_h  = img->height;
    const int ch     = img->channels;
    const int stride = (img->stride > 0) ? img->stride : src_w * ch;

    /* Scale to fit the longer side into the target */
    const float scale_w = static_cast<float>(target_w) / src_w;
    const float scale_h = static_cast<float>(target_h) / src_h;
    scale = std::min(scale_w, scale_h);

    const int new_w = static_cast<int>(std::round(src_w * scale));
    const int new_h = static_cast<int>(std::round(src_h * scale));

    /* Centre padding */
    pad_x = (target_w - new_w) / 2.0f;
    pad_y = (target_h - new_h) / 2.0f;
    const int pad_left = static_cast<int>(pad_x);
    const int pad_top  = static_cast<int>(pad_y);

    /* Fill entire NCHW buffer with pad colour 114/255 */
    const float pad_val = 114.0f / 255.0f;
    std::vector<float> out(static_cast<size_t>(3) * target_h * target_w,
                           pad_val);

    /* Bilinear-resize source into the centred region */
    for (int y = 0; y < new_h; ++y) {
        for (int x = 0; x < new_w; ++x) {
            /* Map destination pixel back to source coordinates */
            float sx = (x + 0.5f) / scale - 0.5f;
            float sy = (y + 0.5f) / scale - 0.5f;

            int x0 = std::max(0, static_cast<int>(std::floor(sx)));
            int y0 = std::max(0, static_cast<int>(std::floor(sy)));
            int x1 = std::min(src_w - 1, x0 + 1);
            int y1 = std::min(src_h - 1, y0 + 1);

            float wx = sx - x0;  if (wx < 0.0f) wx = 0.0f;
            float wy = sy - y0;  if (wy < 0.0f) wy = 0.0f;

            const int dst_x = pad_left + x;
            const int dst_y = pad_top  + y;
            if (dst_x < 0 || dst_x >= target_w ||
                dst_y < 0 || dst_y >= target_h)
                continue;

            for (int c = 0; c < 3; ++c) {
                /* BGR → RGB: flip channels 0↔2 when input is BGR (format 0) */
                int sc = (img->color_format == 0) ? (2 - c) : c;
                if (sc >= ch) sc = 0;   /* graceful fallback for grayscale */

                float p00 = img->data[y0 * stride + x0 * ch + sc];
                float p10 = img->data[y0 * stride + x1 * ch + sc];
                float p01 = img->data[y1 * stride + x0 * ch + sc];
                float p11 = img->data[y1 * stride + x1 * ch + sc];

                float val = (1 - wx) * (1 - wy) * p00
                          + wx       * (1 - wy) * p10
                          + (1 - wx) * wy       * p01
                          + wx       * wy       * p11;

                /* Normalise to [0, 1] and write in NCHW order */
                val /= 255.0f;
                out[c * target_h * target_w + dst_y * target_w + dst_x] = val;
            }
        }
    }
    return out;
}

// ===========================================================================
// IoU (Intersection over Union)
// ===========================================================================

static float _iou(const Detection& a, const Detection& b) {
    float ix1 = std::max(a.x1, b.x1);
    float iy1 = std::max(a.y1, b.y1);
    float ix2 = std::min(a.x2, b.x2);
    float iy2 = std::min(a.y2, b.y2);

    float inter = std::max(0.0f, ix2 - ix1) * std::max(0.0f, iy2 - iy1);
    float area_a = (a.x2 - a.x1) * (a.y2 - a.y1);
    float area_b = (b.x2 - b.x1) * (b.y2 - b.y1);
    float uni = area_a + area_b - inter;

    return (uni > 0.0f) ? (inter / uni) : 0.0f;
}

// ===========================================================================
// Non-Maximum Suppression (per class)
// ===========================================================================

std::vector<Detection> fd_nms(std::vector<Detection>& detections,
                              float iou_threshold) {
    std::vector<Detection> result;
    if (detections.empty()) return result;

    /* Sort by confidence (descending) */
    std::sort(detections.begin(), detections.end(),
              [](const Detection& a, const Detection& b) {
                  return a.confidence > b.confidence;
              });

    /* Collect unique class IDs */
    std::vector<int> class_ids;
    for (const auto& d : detections) {
        if (std::find(class_ids.begin(), class_ids.end(), d.class_id)
            == class_ids.end()) {
            class_ids.push_back(d.class_id);
        }
    }

    /* Greedy NMS per class */
    for (int cls : class_ids) {
        std::vector<size_t> indices;
        for (size_t i = 0; i < detections.size(); ++i)
            if (detections[i].class_id == cls) indices.push_back(i);

        std::vector<bool> suppressed(indices.size(), false);
        for (size_t i = 0; i < indices.size(); ++i) {
            if (suppressed[i]) continue;
            result.push_back(detections[indices[i]]);
            for (size_t j = i + 1; j < indices.size(); ++j) {
                if (suppressed[j]) continue;
                if (_iou(detections[indices[i]], detections[indices[j]])
                    > iou_threshold) {
                    suppressed[j] = true;
                }
            }
        }
    }
    return result;
}

// ===========================================================================
// YOLOv8 postprocessing
//
// Raw output tensor shape: [1, (num_classes + 4), 8400]
// After transpose:         [8400, (num_classes + 4)]
//   columns 0-3  → cx, cy, w, h   (pixel coordinates in letterbox space)
//   columns 4..  → per-class confidence scores
// ===========================================================================

std::vector<Detection> fd_postprocess_yolov8(const float* output_data,
                                              const int64_t* output_shape,
                                              int    num_dims,
                                              int    num_classes,
                                              float  conf_threshold,
                                              float  scale,
                                              float  pad_x, float  pad_y,
                                              int    orig_w, int    orig_h) {
    std::vector<Detection> detections;
    if (num_dims < 2 || !output_data) return detections;

    /*
     * Determine layout.  YOLOv8 standard: [1, C+4, N]  (C+4 < N)
     * Some exports may already be [1, N, C+4].
     */
    int64_t dim_a = output_shape[num_dims - 2];   /* C+4 or N */
    int64_t dim_b = output_shape[num_dims - 1];   /* N   or C+4 */

    bool transposed;        /* true → data is [C+4, N], need col-major access */
    int  num_dets;
    int  feat_dim;

    if (dim_a == num_classes + 4 && dim_b > dim_a) {
        /* Standard [1, C+4, N] */
        transposed = true;
        feat_dim   = static_cast<int>(dim_a);
        num_dets   = static_cast<int>(dim_b);
    } else if (dim_b == num_classes + 4 && dim_a > dim_b) {
        /* Already [1, N, C+4] */
        transposed = false;
        feat_dim   = static_cast<int>(dim_b);
        num_dets   = static_cast<int>(dim_a);
    } else {
        /* Ambiguous — fall back to treating second-to-last as feature dim */
        transposed = (dim_a < dim_b);
        feat_dim   = static_cast<int>(transposed ? dim_a : dim_b);
        num_dets   = static_cast<int>(transposed ? dim_b : dim_a);
    }

    if (feat_dim < 4 + num_classes) return detections;

    for (int i = 0; i < num_dets; ++i) {
        /* Read cx, cy, w, h */
        float cx, cy, bw, bh;
        if (transposed) {
            cx = output_data[0 * num_dets + i];
            cy = output_data[1 * num_dets + i];
            bw = output_data[2 * num_dets + i];
            bh = output_data[3 * num_dets + i];
        } else {
            cx = output_data[i * feat_dim + 0];
            cy = output_data[i * feat_dim + 1];
            bw = output_data[i * feat_dim + 2];
            bh = output_data[i * feat_dim + 3];
        }

        /* Find the class with the highest score */
        float best_score = 0.0f;
        int   best_class = 0;
        for (int c = 0; c < num_classes; ++c) {
            float s = transposed
                ? output_data[(4 + c) * num_dets + i]
                : output_data[i * feat_dim + 4 + c];
            if (s > best_score) { best_score = s; best_class = c; }
        }
        if (best_score < conf_threshold) continue;

        /* cx,cy,w,h → x1,y1,x2,y2  (letterbox space) */
        float x1 = cx - bw * 0.5f;
        float y1 = cy - bh * 0.5f;
        float x2 = cx + bw * 0.5f;
        float y2 = cy + bh * 0.5f;

        /* Map back to original image coordinates */
        x1 = (x1 - pad_x) / scale;
        y1 = (y1 - pad_y) / scale;
        x2 = (x2 - pad_x) / scale;
        y2 = (y2 - pad_y) / scale;

        /* Clamp */
        x1 = std::max(0.0f, std::min(x1, static_cast<float>(orig_w)));
        y1 = std::max(0.0f, std::min(y1, static_cast<float>(orig_h)));
        x2 = std::max(0.0f, std::min(x2, static_cast<float>(orig_w)));
        y2 = std::max(0.0f, std::min(y2, static_cast<float>(orig_h)));

        /* Discard degenerate boxes */
        if (x2 - x1 < 1.0f || y2 - y1 < 1.0f) continue;

        detections.push_back({x1, y1, x2, y2, best_score, best_class});
    }
    return detections;
}

// ===========================================================================
// Build the JSON result string
// ===========================================================================

static std::string _build_json_result(
        const std::vector<Detection>& dets,
        const std::vector<std::string>& labels) {
    std::string json;
    json.reserve(128 + dets.size() * 128);
    json += "{\"detections\":[";

    for (size_t i = 0; i < dets.size(); ++i) {
        const auto& d = dets[i];
        const std::string& label =
            (d.class_id >= 0 &&
             d.class_id < static_cast<int>(labels.size()))
            ? labels[d.class_id] : "unknown";

        char buf[256];
        std::snprintf(buf, sizeof(buf),
            "{\"bbox\":[%.2f,%.2f,%.2f,%.2f],"
            "\"confidence\":%.4f,"
            "\"label\":\"%s\","
            "\"class_id\":%d}",
            static_cast<double>(d.x1), static_cast<double>(d.y1),
            static_cast<double>(d.x2), static_cast<double>(d.y2),
            static_cast<double>(d.confidence),
            label.c_str(), d.class_id);

        if (i > 0) json += ',';
        json += buf;
    }

    char tail[64];
    std::snprintf(tail, sizeof(tail),
        "],\"count\":%d,\"face_detected\":%s}",
        static_cast<int>(dets.size()),
        dets.empty() ? "false" : "true");
    json += tail;
    return json;
}

// ===========================================================================
// ABI implementation — AiGetAbiVersion
// ===========================================================================

AI_EXPORT int32_t AiGetAbiVersion(void) {
    return AI_ABI_VERSION;
}

// ===========================================================================
// AiCreate — allocate context, load manifest + preprocess config
// ===========================================================================

AI_EXPORT AiHandle AiCreate(const char* model_dir, const char* config_json) {
    if (!model_dir) return nullptr;

    auto* ctx = new (std::nothrow) FaceDetectContext();
    if (!ctx) return nullptr;
    ctx->model_dir = model_dir;

    /* --- manifest.json --- */
    std::string manifest_path = ctx->model_dir + "/manifest.json";
    std::string manifest;
    if (_read_file(manifest_path, manifest)) {
        int nc = _jint(manifest, "num_classes", 2);
        if (nc > 0) ctx->num_classes = nc;

        double ct = _jnum(manifest, "conf_threshold", 0.25);
        if (ct > 0.0) ctx->conf_threshold = static_cast<float>(ct);

        double nt = _jnum(manifest, "nms_threshold", 0.45);
        if (nt > 0.0) ctx->nms_threshold = static_cast<float>(nt);

        auto labels = _jstr_array(manifest, "class_labels");
        if (!labels.empty()) ctx->class_labels = std::move(labels);
    }

    /* Provide default labels if none were loaded */
    if (ctx->class_labels.empty()) {
        ctx->class_labels = {"face", "occluded_face"};
        while (static_cast<int>(ctx->class_labels.size()) < ctx->num_classes) {
            ctx->class_labels.push_back(
                "class_" + std::to_string(ctx->class_labels.size()));
        }
    }

    /* --- preprocess.json --- */
    std::string prep_path = ctx->model_dir + "/preprocess.json";
    std::string prep_json;
    if (_read_file(prep_path, prep_json)) {
        int rw = _jint(prep_json, "width",  640);
        int rh = _jint(prep_json, "height", 640);
        if (rw > 0) ctx->input_width  = rw;
        if (rh > 0) ctx->input_height = rh;
    }

    /* --- optional runtime overrides from config_json --- */
    if (config_json) {
        std::string cfg(config_json);
        double ct = _jnum(cfg, "conf_threshold", -1.0);
        if (ct > 0.0) ctx->conf_threshold = static_cast<float>(ct);
        double nt = _jnum(cfg, "nms_threshold", -1.0);
        if (nt > 0.0) ctx->nms_threshold = static_cast<float>(nt);
    }

    return static_cast<AiHandle>(ctx);
}

// ===========================================================================
// AiInit — load ORT model, query input/output metadata
// ===========================================================================

AI_EXPORT int32_t AiInit(AiHandle handle) {
    if (!handle) return AI_ERR_INVALID_PARAM;
    auto* ctx = static_cast<FaceDetectContext*>(handle);

    /* --- License (soft check — warn in dev mode) --- */
    std::string license_path =
        ctx->model_dir + "/../../../licenses/license.bin";
    const char* env_lic = std::getenv("AI_LICENSE_PATH");
    if (env_lic) license_path = env_lic;

    if (!_check_license_capability(license_path)) {
        std::fprintf(stderr,
            "[face_detect] WARNING: License check failed (path=%s). "
            "Proceeding in dev mode.\n", license_path.c_str());
    }
    ctx->license_path = license_path;

#if HAS_ORT
    /* Obtain the C API function table */
    const OrtApiBase* api_base = OrtGetApiBase();
    ctx->ort_api = api_base->GetApi(ORT_API_VERSION);
    const OrtApi* api = ctx->ort_api;

    /* Environment */
    if (!_ort_ok(api,
            api->CreateEnv(ORT_LOGGING_LEVEL_WARNING, "face_detect",
                           &ctx->ort_env),
            "CreateEnv")) {
        return AI_ERR_LOAD_FAILED;
    }

    /* Session options */
    if (!_ort_ok(api,
            api->CreateSessionOptions(&ctx->ort_session_opts),
            "CreateSessionOptions")) {
        return AI_ERR_LOAD_FAILED;
    }
    api->SetIntraOpNumThreads(ctx->ort_session_opts, 1);
    api->SetSessionGraphOptimizationLevel(ctx->ort_session_opts,
                                          ORT_ENABLE_EXTENDED);

    /* GPU-first strategy: Try CUDA, fallback to CPU */
    OrtCUDAProviderOptions cuda_options;
    std::memset(&cuda_options, 0, sizeof(cuda_options));
    cuda_options.device_id = 0;
    cuda_options.cudnn_conv_algo_search = OrtCudnnConvAlgoSearchDefault;
    cuda_options.gpu_mem_limit = SIZE_MAX;
    cuda_options.arena_extend_strategy = 0;
    cuda_options.do_copy_in_default_stream = 1;

    OrtStatus* cuda_status = api->SessionOptionsAppendExecutionProvider_CUDA(
        ctx->ort_session_opts, &cuda_options);

    if (cuda_status == nullptr) {
        std::fprintf(stdout, "[face_detect] GPU mode enabled (CUDA ExecutionProvider)\n");
    } else {
        // CUDA unavailable, will use CPU automatically
        const char* err_msg = api->GetErrorMessage(cuda_status);
        std::fprintf(stderr, "[face_detect] CUDA unavailable (%s), using CPU\n", err_msg);
        api->ReleaseStatus(cuda_status);
    }

    /* Load model.onnx */
    std::string model_path = ctx->model_dir + "/model.onnx";
    if (!_ort_ok(api,
            api->CreateSession(ctx->ort_env, model_path.c_str(),
                               ctx->ort_session_opts, &ctx->ort_session),
            "CreateSession")) {
        std::fprintf(stderr, "[face_detect] Failed to load model: %s\n",
                     model_path.c_str());
        return AI_ERR_LOAD_FAILED;
    }

    /* Default allocator (used for name queries) */
    if (!_ort_ok(api,
            api->GetAllocatorWithDefaultOptions(&ctx->ort_allocator),
            "GetAllocatorWithDefaultOptions")) {
        return AI_ERR_LOAD_FAILED;
    }

    /* Query input names */
    size_t num_inputs = 0;
    if (!_ort_ok(api,
            api->SessionGetInputCount(ctx->ort_session, &num_inputs),
            "SessionGetInputCount")) {
        return AI_ERR_LOAD_FAILED;
    }
    for (size_t i = 0; i < num_inputs; ++i) {
        char* name = nullptr;
        if (!_ort_ok(api,
                api->SessionGetInputName(ctx->ort_session, i,
                                         ctx->ort_allocator, &name),
                "SessionGetInputName")) {
            return AI_ERR_LOAD_FAILED;
        }
        ctx->input_names.push_back(name);
    }

    /* Query output names */
    size_t num_outputs = 0;
    if (!_ort_ok(api,
            api->SessionGetOutputCount(ctx->ort_session, &num_outputs),
            "SessionGetOutputCount")) {
        return AI_ERR_LOAD_FAILED;
    }
    for (size_t i = 0; i < num_outputs; ++i) {
        char* name = nullptr;
        if (!_ort_ok(api,
                api->SessionGetOutputName(ctx->ort_session, i,
                                          ctx->ort_allocator, &name),
                "SessionGetOutputName")) {
            return AI_ERR_LOAD_FAILED;
        }
        ctx->output_names.push_back(name);
    }

    std::fprintf(stdout,
        "[face_detect] Model loaded: %s (inputs=%zu, outputs=%zu)\n",
        model_path.c_str(), num_inputs, num_outputs);
#else
    std::fprintf(stderr,
        "[face_detect] ONNXRuntime not available — "
        "AiInfer will return stub result.\n");
#endif  /* HAS_ORT */

    return AI_OK;
}

// ===========================================================================
// AiInfer — preprocess → run → postprocess → JSON
// ===========================================================================

AI_EXPORT int32_t AiInfer(AiHandle handle,
                           const AiImage* input,
                           AiResult* output) {
    if (!handle || !input || !output) return AI_ERR_INVALID_PARAM;
    if (!input->data || input->width <= 0 || input->height <= 0)
        return AI_ERR_INVALID_PARAM;

    auto* ctx = static_cast<FaceDetectContext*>(handle);

    /* Periodic license re-check every 1000 inferences */
    uint64_t cnt = ctx->infer_count.fetch_add(1);
    if (cnt > 0 && cnt % 1000 == 0) {
        if (!_check_license_capability(ctx->license_path)) {
            _set_result(output, AI_ERR_LICENSE_EXPIRED,
                        nullptr, "License expired or invalid");
            return AI_ERR_LICENSE_EXPIRED;
        }
    }

#if HAS_ORT
    if (!ctx->ort_session) {
        _set_result(output, AI_ERR_LOAD_FAILED, nullptr, "Model not loaded");
        return AI_ERR_LOAD_FAILED;
    }
    const OrtApi* api = ctx->ort_api;

    /* ---- 1. Pre-process (letterbox) ---- */
    float scale = 1.0f, pad_x = 0.0f, pad_y = 0.0f;
    std::vector<float> tensor_data = fd_preprocess_letterbox(
        input, ctx->input_width, ctx->input_height, scale, pad_x, pad_y);

    /* Create input tensor */
    int64_t input_shape[4] = {
        1, 3,
        static_cast<int64_t>(ctx->input_height),
        static_cast<int64_t>(ctx->input_width)
    };

    OrtMemoryInfo* mem_info = nullptr;
    if (!_ort_ok(api,
            api->CreateCpuMemoryInfo(OrtArenaAllocator, OrtMemTypeDefault,
                                     &mem_info),
            "CreateCpuMemoryInfo")) {
        _set_result(output, AI_ERR_INFER_FAILED, nullptr,
                    "Failed to create memory info");
        return AI_ERR_INFER_FAILED;
    }

    OrtValue* input_tensor = nullptr;
    OrtStatus* ts = api->CreateTensorWithDataAsOrtValue(
        mem_info,
        tensor_data.data(),
        tensor_data.size() * sizeof(float),
        input_shape, 4,
        ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT,
        &input_tensor);
    api->ReleaseMemoryInfo(mem_info);

    if (!_ort_ok(api, ts, "CreateTensorWithDataAsOrtValue")) {
        _set_result(output, AI_ERR_INFER_FAILED, nullptr,
                    "Failed to create input tensor");
        return AI_ERR_INFER_FAILED;
    }

    /* ---- 2. Run inference ---- */
    const size_t n_out = ctx->output_names.size();
    std::vector<OrtValue*> output_tensors(n_out, nullptr);

    const OrtValue* input_arr[] = {input_tensor};
    OrtStatus* run_status = api->Run(
        ctx->ort_session,
        nullptr,                                            /* run options  */
        (const char* const*)ctx->input_names.data(),
        input_arr,  ctx->input_names.size(),
        (const char* const*)ctx->output_names.data(),
        n_out,
        output_tensors.data());

    api->ReleaseValue(input_tensor);

    if (!_ort_ok(api, run_status, "Run")) {
        _set_result(output, AI_ERR_INFER_FAILED, nullptr,
                    "Inference execution failed");
        return AI_ERR_INFER_FAILED;
    }

    /* ---- 3. Read output tensor ---- */
    float* out_data = nullptr;
    if (!_ort_ok(api,
            api->GetTensorMutableData(output_tensors[0],
                                      reinterpret_cast<void**>(&out_data)),
            "GetTensorMutableData")) {
        for (auto* t : output_tensors) if (t) api->ReleaseValue(t);
        _set_result(output, AI_ERR_INFER_FAILED, nullptr,
                    "Failed to get output data");
        return AI_ERR_INFER_FAILED;
    }

    OrtTensorTypeAndShapeInfo* shape_info = nullptr;
    api->GetTensorTypeAndShape(output_tensors[0], &shape_info);
    size_t ndim = 0;
    api->GetDimensionsCount(shape_info, &ndim);
    std::vector<int64_t> out_shape(ndim);
    api->GetDimensions(shape_info, out_shape.data(), ndim);
    api->ReleaseTensorTypeAndShapeInfo(shape_info);

    /* ---- 4. Post-process (decode + NMS) ---- */
    auto raw_dets = fd_postprocess_yolov8(
        out_data, out_shape.data(), static_cast<int>(ndim),
        ctx->num_classes, ctx->conf_threshold,
        scale, pad_x, pad_y,
        input->width, input->height);

    for (auto* t : output_tensors) if (t) api->ReleaseValue(t);

    auto final_dets = fd_nms(raw_dets, ctx->nms_threshold);

    /* ---- 5. Build JSON ---- */
    std::string json = _build_json_result(final_dets, ctx->class_labels);
    _set_result(output, AI_OK, json.c_str());
    return AI_OK;

#else  /* no ORT */
    _set_result(output, AI_OK,
        "{\"detections\":[],\"count\":0,\"face_detected\":false,"
        "\"note\":\"stub_result_no_ort\"}");
    return AI_OK;
#endif
}

// ===========================================================================
// AiReload — hot-swap model without destroying the handle
// ===========================================================================

AI_EXPORT int32_t AiReload(AiHandle handle, const char* new_model_dir) {
    if (!handle || !new_model_dir) return AI_ERR_INVALID_PARAM;

    /* Build a fresh context with the new model */
    AiHandle new_h = AiCreate(new_model_dir, nullptr);
    if (!new_h) return AI_ERR_LOAD_FAILED;
    int32_t rc = AiInit(new_h);
    if (rc != AI_OK) { AiDestroy(new_h); return rc; }

    auto* ctx     = static_cast<FaceDetectContext*>(handle);
    auto* new_ctx = static_cast<FaceDetectContext*>(new_h);

#if HAS_ORT
    const OrtApi* api = ctx->ort_api ? ctx->ort_api : new_ctx->ort_api;

    /* Release old ORT resources */
    if (ctx->ort_allocator) {
        for (auto* name : ctx->input_names)
            ctx->ort_allocator->Free(ctx->ort_allocator, name);
        for (auto* name : ctx->output_names)
            ctx->ort_allocator->Free(ctx->ort_allocator, name);
    }
    ctx->input_names.clear();
    ctx->output_names.clear();
    if (ctx->ort_session)      api->ReleaseSession(ctx->ort_session);
    if (ctx->ort_session_opts) api->ReleaseSessionOptions(ctx->ort_session_opts);
    if (ctx->ort_env)          api->ReleaseEnv(ctx->ort_env);

    /* Move new resources into the existing context */
    ctx->ort_api          = new_ctx->ort_api;
    ctx->ort_env          = new_ctx->ort_env;
    ctx->ort_session      = new_ctx->ort_session;
    ctx->ort_session_opts = new_ctx->ort_session_opts;
    ctx->ort_allocator    = new_ctx->ort_allocator;
    ctx->input_names      = std::move(new_ctx->input_names);
    ctx->output_names     = std::move(new_ctx->output_names);

    /* Prevent AiDestroy(new_h) from double-freeing the moved resources */
    new_ctx->ort_env          = nullptr;
    new_ctx->ort_session      = nullptr;
    new_ctx->ort_session_opts = nullptr;
    new_ctx->input_names.clear();
    new_ctx->output_names.clear();
#endif

    ctx->model_dir      = new_ctx->model_dir;
    ctx->num_classes    = new_ctx->num_classes;
    ctx->conf_threshold = new_ctx->conf_threshold;
    ctx->nms_threshold  = new_ctx->nms_threshold;
    ctx->class_labels   = std::move(new_ctx->class_labels);
    ctx->input_width    = new_ctx->input_width;
    ctx->input_height   = new_ctx->input_height;
    ctx->infer_count    = 0;

    AiDestroy(new_h);
    return AI_OK;
}

// ===========================================================================
// AiGetInfo — return capability metadata as JSON
// ===========================================================================

AI_EXPORT int32_t AiGetInfo(AiHandle handle, char* info_buf, int32_t buf_len) {
    (void)handle;
    static const char kInfo[] =
        "{\"capability\":\"face_detect\","
        "\"capability_name_cn\":\"人脸检测\","
        "\"abi_version\":\"" STRINGIFY(AI_ABI_VERSION) "\","
        "\"company\":\"agilestar.cn\"}";

    int32_t needed = static_cast<int32_t>(std::strlen(kInfo));
    if (!info_buf || buf_len <= needed) return needed;
    std::memcpy(info_buf, kInfo, static_cast<size_t>(needed) + 1);
    return needed;
}

// ===========================================================================
// AiDestroy — release all resources
// ===========================================================================

AI_EXPORT void AiDestroy(AiHandle handle) {
    if (!handle) return;
    auto* ctx = static_cast<FaceDetectContext*>(handle);

#if HAS_ORT
    if (ctx->ort_api) {
        const OrtApi* api = ctx->ort_api;

        /* Free ORT-allocated input/output name strings */
        if (ctx->ort_allocator) {
            for (auto* name : ctx->input_names)
                ctx->ort_allocator->Free(ctx->ort_allocator, name);
            for (auto* name : ctx->output_names)
                ctx->ort_allocator->Free(ctx->ort_allocator, name);
        }

        if (ctx->ort_session)
            api->ReleaseSession(ctx->ort_session);
        if (ctx->ort_session_opts)
            api->ReleaseSessionOptions(ctx->ort_session_opts);
        if (ctx->ort_env)
            api->ReleaseEnv(ctx->ort_env);
    }
#endif

    delete ctx;
}

// ===========================================================================
// AiFreeResult — free plugin-allocated result strings
// ===========================================================================

AI_EXPORT void AiFreeResult(AiResult* result) {
    if (!result) return;
    std::free(result->json_result);
    std::free(result->error_msg);
    result->json_result = nullptr;
    result->error_msg   = nullptr;
    result->result_len  = 0;
}
