/**
 * desktop_recapture_detect.cpp
 * desktop_recapture_detect 能力插件 — 桌面翻拍检测（二分类：real / fake）
 *
 * EfficientNet-B0 模型，输出单个 logit，sigmoid 后得到 P(fake)。
 * 推理引擎：ONNXRuntime CPU/GPU。
 * License：AiInit 时验证 license.bin 中是否包含 "desktop_recapture_detect" 能力。
 *
 * 迁移自 LeeYou/recapture_detect (dev branch) for ai_platform integration.
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#include "desktop_recapture_detect.h"

#include <atomic>
#include <cassert>
#include <cctype>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

// ---------------------------------------------------------------------------
// ONNXRuntime C++ API (optional: compiled without ORT in skeleton mode)
// ---------------------------------------------------------------------------

#if __has_include(<onnxruntime_cxx_api.h>)
#  include <onnxruntime_cxx_api.h>
#  define HAS_ORT 1
#else
#  define HAS_ORT 0
#endif

// ---------------------------------------------------------------------------
// Internal context
// ---------------------------------------------------------------------------

struct DesktopRecaptureContext {
    std::string model_dir;
    std::string license_path;

    // Pre-process config (EfficientNet-B0 224×224 with ImageNet normalization)
    int   input_width  = 224;
    int   input_height = 224;
    float mean[3]      = {0.485f, 0.456f, 0.406f};
    float std_dev[3]   = {0.229f, 0.224f, 0.225f};

    // Inference counter (for periodic license checks)
    std::atomic<uint64_t> infer_count{0};

#if HAS_ORT
    Ort::Env                             ort_env{ORT_LOGGING_LEVEL_WARNING, "desktop_recapture_detect"};
    std::unique_ptr<Ort::Session>        session;
    Ort::SessionOptions                  session_opts;
    std::vector<std::string>             input_names_storage;
    std::vector<std::string>             output_names_storage;
    std::vector<const char*>             input_names;
    std::vector<const char*>             output_names;
#endif
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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
    result->error_code   = code;
    result->json_result  = json ? _dup(json) : nullptr;
    result->result_len   = json ? static_cast<int32_t>(std::strlen(json)) : 0;
    result->error_msg    = msg  ? _dup(msg)  : nullptr;
}

static bool _read_file(const std::string& path, std::string& out) {
    std::ifstream f(path);
    if (!f.is_open()) return false;
    out.assign((std::istreambuf_iterator<char>(f)),
                std::istreambuf_iterator<char>());
    return true;
}

static bool _jint(const std::string& json, const std::string& key, int* out) {
    if (!out) return false;
    std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return false;
    pos = json.find(':', pos + needle.size());
    if (pos == std::string::npos) return false;
    ++pos;
    while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) {
        ++pos;
    }
    if (pos >= json.size()) return false;

    std::string token;
    if (json[pos] == '"') {
        auto end = json.find('"', pos + 1);
        if (end == std::string::npos) return false;
        token = json.substr(pos + 1, end - pos - 1);
    } else {
        auto end = pos;
        if (json[end] == '-' || json[end] == '+') ++end;
        while (end < json.size() && std::isdigit(static_cast<unsigned char>(json[end]))) {
            ++end;
        }
        if (end == pos || ((json[pos] == '-' || json[pos] == '+') && end == pos + 1)) {
            return false;
        }
        token = json.substr(pos, end - pos);
    }

    try {
        *out = std::stoi(token);
        return true;
    } catch (const std::exception&) {
        return false;
    }
}

// ---------------------------------------------------------------------------
// License check
// ---------------------------------------------------------------------------

static bool _check_license_capability(const std::string& license_path) {
    std::string content;
    if (!_read_file(license_path, content)) return false;
    auto cap_pos = content.find("\"capabilities\"");
    if (cap_pos == std::string::npos) return false;
    auto arr_start = content.find('[', cap_pos);
    auto arr_end   = content.find(']', arr_start);
    if (arr_start == std::string::npos || arr_end == std::string::npos) return false;
    std::string arr = content.substr(arr_start, arr_end - arr_start + 1);
    return arr.find("\"desktop_recapture_detect\"") != std::string::npos;
}

// ---------------------------------------------------------------------------
// Pre-process: NHWC uint8 BGR → NCHW float32, ImageNet normalised
// ---------------------------------------------------------------------------

#if HAS_ORT
static std::vector<float> _preprocess(const AiImage* img,
                                       int target_w, int target_h,
                                       const float mean[3],
                                       const float std_dev[3]) {
    int src_w = img->width;
    int src_h = img->height;
    int ch    = img->channels;
    int stride = img->stride > 0 ? img->stride : src_w * ch;

    std::vector<float> out(3 * target_h * target_w);

    for (int y = 0; y < target_h; ++y) {
        for (int x = 0; x < target_w; ++x) {
            float sx = (x + 0.5f) * src_w  / target_w - 0.5f;
            float sy = (y + 0.5f) * src_h / target_h - 0.5f;
            int   x0 = std::max(0, static_cast<int>(sx));
            int   y0 = std::max(0, static_cast<int>(sy));
            int   x1 = std::min(src_w - 1, x0 + 1);
            int   y1 = std::min(src_h - 1, y0 + 1);
            float wx = sx - x0;
            float wy = sy - y0;

            for (int c = 0; c < 3; ++c) {
                int sc = (img->color_format == 0) ? (2 - c) : c;  // 0=BGR→flip
                if (sc >= ch) sc = 0;

                float p00 = static_cast<float>(
                    img->data[y0 * stride + x0 * ch + sc]) / 255.0f;
                float p10 = static_cast<float>(
                    img->data[y0 * stride + x1 * ch + sc]) / 255.0f;
                float p01 = static_cast<float>(
                    img->data[y1 * stride + x0 * ch + sc]) / 255.0f;
                float p11 = static_cast<float>(
                    img->data[y1 * stride + x1 * ch + sc]) / 255.0f;
                float val = (1 - wx) * (1 - wy) * p00
                          + wx       * (1 - wy) * p10
                          + (1 - wx) * wy        * p01
                          + wx       * wy        * p11;
                val = (val - mean[c]) / std_dev[c];
                out[c * target_h * target_w + y * target_w + x] = val;
            }
        }
    }
    return out;
}
#endif  // HAS_ORT

// ---------------------------------------------------------------------------
// ABI implementation
// ---------------------------------------------------------------------------

AI_EXPORT int32_t AiGetAbiVersion(void) {
    return AI_ABI_VERSION;
}

AI_EXPORT AiHandle AiCreate(const char* model_dir, const char* /*config_json*/) {
    if (!model_dir) return nullptr;
    auto* ctx = new DesktopRecaptureContext();
    ctx->model_dir = model_dir;

    // Load preprocess config
    std::string prep_path = ctx->model_dir + "/preprocess.json";
    std::string prep_json;
    if (_read_file(prep_path, prep_json)) {
        int parsed_width = 0;
        int parsed_height = 0;
        if (_jint(prep_json, "width", &parsed_width)) {
            ctx->input_width = parsed_width;
        }
        if (_jint(prep_json, "height", &parsed_height)) {
            ctx->input_height = parsed_height;
        }
    }

    return static_cast<AiHandle>(ctx);
}

AI_EXPORT int32_t AiInit(AiHandle handle) {
    if (!handle) return AI_ERR_INVALID_PARAM;
    auto* ctx = static_cast<DesktopRecaptureContext*>(handle);

    // License check
    std::string license_path = std::string(ctx->model_dir) + "/../../../licenses/license.bin";
    const char* env_lic = std::getenv("AI_LICENSE_PATH");
    if (env_lic) license_path = env_lic;

    if (!_check_license_capability(license_path)) {
        std::fprintf(stderr,
            "[desktop_recapture_detect] WARNING: License check failed "
            "(path=%s). Proceeding in dev mode.\n",
            license_path.c_str());
    }
    ctx->license_path = license_path;

#if HAS_ORT
    std::string model_path = ctx->model_dir + "/model.onnx";
    ctx->session_opts.SetIntraOpNumThreads(1);
    ctx->session_opts.SetGraphOptimizationLevel(ORT_ENABLE_EXTENDED);

    /* GPU-first strategy: Try CUDA, fallback to CPU */
    try {
        OrtCUDAProviderOptions cuda_options;
        cuda_options.device_id = 0;
        cuda_options.cudnn_conv_algo_search = OrtCudnnConvAlgoSearchDefault;
        cuda_options.gpu_mem_limit = SIZE_MAX;
        cuda_options.arena_extend_strategy = 0;
        cuda_options.do_copy_in_default_stream = 1;
        ctx->session_opts.AppendExecutionProvider_CUDA(cuda_options);
        std::fprintf(stdout, "[desktop_recapture_detect] GPU mode enabled (CUDA ExecutionProvider)\n");
    } catch (const Ort::Exception& e) {
        // CUDA unavailable, will use CPU automatically
        std::fprintf(stderr, "[desktop_recapture_detect] CUDA unavailable (%s), using CPU\n", e.what());
    }

    try {
        ctx->session = std::make_unique<Ort::Session>(
            ctx->ort_env,
            model_path.c_str(),
            ctx->session_opts);
    } catch (const Ort::Exception& ex) {
        std::fprintf(stderr, "[desktop_recapture_detect] Failed to load model %s: %s\n",
                     model_path.c_str(), ex.what());
        return AI_ERR_LOAD_FAILED;
    }

    Ort::AllocatorWithDefaultOptions alloc;
    size_t n_in  = ctx->session->GetInputCount();
    size_t n_out = ctx->session->GetOutputCount();
    for (size_t i = 0; i < n_in; ++i) {
        ctx->input_names_storage.push_back(
            ctx->session->GetInputNameAllocated(i, alloc).get());
    }
    for (size_t i = 0; i < n_out; ++i) {
        ctx->output_names_storage.push_back(
            ctx->session->GetOutputNameAllocated(i, alloc).get());
    }
    for (auto& s : ctx->input_names_storage)  ctx->input_names.push_back(s.c_str());
    for (auto& s : ctx->output_names_storage) ctx->output_names.push_back(s.c_str());

    std::fprintf(stdout, "[desktop_recapture_detect] Model loaded: %s\n", model_path.c_str());
#else
    std::fprintf(stderr,
        "[desktop_recapture_detect] ONNXRuntime not available — AiInfer will return stub result.\n");
#endif

    return AI_OK;
}

AI_EXPORT int32_t AiInfer(AiHandle handle, const AiImage* input, AiResult* output) {
    if (!handle || !input || !output) return AI_ERR_INVALID_PARAM;
    auto* ctx = static_cast<DesktopRecaptureContext*>(handle);

    // Periodic license check every 1000 inferences
    uint64_t cnt = ctx->infer_count.fetch_add(1);
    if (cnt % 1000 == 0 && cnt > 0) {
        if (!_check_license_capability(ctx->license_path)) {
            _set_result(output, AI_ERR_LICENSE_EXPIRED,
                        nullptr, "License expired or invalid");
            return AI_ERR_LICENSE_EXPIRED;
        }
    }

#if HAS_ORT
    if (!ctx->session) {
        _set_result(output, AI_ERR_LOAD_FAILED, nullptr, "Model not loaded");
        return AI_ERR_LOAD_FAILED;
    }

    auto tensor_data = _preprocess(input,
                                   ctx->input_width, ctx->input_height,
                                   ctx->mean, ctx->std_dev);

    std::array<int64_t, 4> input_shape = {1, 3,
        static_cast<int64_t>(ctx->input_height),
        static_cast<int64_t>(ctx->input_width)};

    Ort::MemoryInfo mem_info =
        Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    Ort::Value input_tensor = Ort::Value::CreateTensor<float>(
        mem_info,
        tensor_data.data(),
        tensor_data.size(),
        input_shape.data(),
        input_shape.size());

    // Allocate output tensor
    Ort::MemoryInfo mem_info_out = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
    std::vector<int64_t> output_shape = {1, 1};  // [batch_size, num_outputs]
    std::vector<float> output_data(1);  // Single output value
    Ort::Value output_tensor = Ort::Value::CreateTensor<float>(
        mem_info_out,
        output_data.data(),
        output_data.size(),
        output_shape.data(),
        output_shape.size());

    try {
        ctx->session->Run(
            Ort::RunOptions{nullptr},
            ctx->input_names.data(),  &input_tensor,      1,
            ctx->output_names.data(), &output_tensor,     1);
    } catch (const Ort::Exception& ex) {
        _set_result(output, AI_ERR_INFER_FAILED, nullptr, ex.what());
        return AI_ERR_INFER_FAILED;
    }

    // EfficientNet-B0 output: single logit → sigmoid = P(fake)
    float logit = output_data[0];
    float prob_fake = 1.0f / (1.0f + std::exp(-logit));
    float prob_real = 1.0f - prob_fake;

    bool is_fake = (prob_fake > 0.5f);
    char json_buf[256];
    std::snprintf(json_buf, sizeof(json_buf),
        "{\"is_fake\":%s,\"label\":\"%s\","
        "\"score_real\":%.4f,\"score_fake\":%.4f}",
        is_fake ? "true" : "false",
        is_fake ? "fake" : "real",
        static_cast<double>(prob_real),
        static_cast<double>(prob_fake));

    _set_result(output, AI_OK, json_buf);
    return AI_OK;

#else
    // Stub result when ONNXRuntime is not available
    _set_result(output, AI_OK,
        "{\"is_fake\":false,\"label\":\"real\","
        "\"score_real\":0.9,\"score_fake\":0.1,"
        "\"note\":\"stub_result_no_ort\"}");
    return AI_OK;
#endif
}

AI_EXPORT int32_t AiReload(AiHandle handle, const char* new_model_dir) {
    if (!handle || !new_model_dir) return AI_ERR_INVALID_PARAM;
    AiHandle new_h = AiCreate(new_model_dir, nullptr);
    if (!new_h) return AI_ERR_LOAD_FAILED;
    int32_t rc = AiInit(new_h);
    if (rc != AI_OK) { AiDestroy(new_h); return rc; }

    auto* ctx     = static_cast<DesktopRecaptureContext*>(handle);
    auto* new_ctx = static_cast<DesktopRecaptureContext*>(new_h);

#if HAS_ORT
    ctx->session               = std::move(new_ctx->session);
    ctx->input_names_storage   = std::move(new_ctx->input_names_storage);
    ctx->output_names_storage  = std::move(new_ctx->output_names_storage);
    ctx->input_names           = std::move(new_ctx->input_names);
    ctx->output_names          = std::move(new_ctx->output_names);
#endif
    ctx->model_dir       = new_ctx->model_dir;
    ctx->input_width     = new_ctx->input_width;
    ctx->input_height    = new_ctx->input_height;
    ctx->infer_count     = 0;

    AiDestroy(new_h);
    return AI_OK;
}

AI_EXPORT int32_t AiGetInfo(AiHandle handle, char* info_buf, int32_t buf_len) {
    static const char kInfo[] =
        "{\"capability\":\"desktop_recapture_detect\","
        "\"capability_name_cn\":\"桌面翻拍检测\","
        "\"abi_version\":\"10000\","
        "\"company\":\"agilestar.cn\"}";
    (void)handle;
    int32_t needed = static_cast<int32_t>(std::strlen(kInfo));
    if (!info_buf || buf_len <= needed) return needed;
    std::memcpy(info_buf, kInfo, static_cast<size_t>(needed) + 1);
    return needed;
}

AI_EXPORT void AiDestroy(AiHandle handle) {
    if (!handle) return;
    auto* ctx = static_cast<DesktopRecaptureContext*>(handle);
    delete ctx;
}

AI_EXPORT void AiFreeResult(AiResult* result) {
    if (!result) return;
    std::free(result->json_result);
    std::free(result->error_msg);
    result->json_result  = nullptr;
    result->error_msg    = nullptr;
    result->result_len   = 0;
}
