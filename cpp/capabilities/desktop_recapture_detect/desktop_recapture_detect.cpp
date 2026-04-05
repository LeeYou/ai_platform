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

#include <algorithm>
#include <array>
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
    std::string model_version = "unknown";

    // Pre-process config (EfficientNet-B0 224×224 with ImageNet normalization)
    int   input_width  = 224;
    int   input_height = 224;
    float scale        = 1.0f / 255.0f;
    bool  normalize    = true;
    float mean[3]      = {0.485f, 0.456f, 0.406f};
    float std_dev[3]   = {0.229f, 0.224f, 0.225f};
    int   target_color_format = 1;  // 0=BGR, 1=RGB

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

static bool _jvalue_pos(const std::string& json, const std::string& key, size_t* out_pos) {
    if (!out_pos) return false;
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
    *out_pos = pos;
    return true;
}

static bool _jstr(const std::string& json, const std::string& key, std::string* out) {
    if (!out) return false;
    size_t pos = 0;
    if (!_jvalue_pos(json, key, &pos) || json[pos] != '"') return false;
    auto end = json.find('"', pos + 1);
    if (end == std::string::npos) return false;
    *out = json.substr(pos + 1, end - pos - 1);
    return true;
}

static bool _jbool(const std::string& json, const std::string& key, bool* out) {
    if (!out) return false;
    size_t pos = 0;
    if (!_jvalue_pos(json, key, &pos)) return false;
    if (json.compare(pos, 4, "true") == 0) {
        *out = true;
        return true;
    }
    if (json.compare(pos, 5, "false") == 0) {
        *out = false;
        return true;
    }
    return false;
}

static bool _jfloat(const std::string& json, const std::string& key, float* out) {
    if (!out) return false;
    size_t pos = 0;
    if (!_jvalue_pos(json, key, &pos)) return false;
    const char* start = json.c_str() + pos;
    char* end = nullptr;
    float value = std::strtof(start, &end);
    if (end == start) return false;
    *out = value;
    return true;
}

static bool _jfloat_array3(const std::string& json, const std::string& key, float out[3]) {
    if (!out) return false;
    std::string needle = "\"" + key + "\"";
    auto pos = json.find(needle);
    if (pos == std::string::npos) return false;
    pos = json.find('[', pos + needle.size());
    if (pos == std::string::npos) return false;
    ++pos;
    for (int i = 0; i < 3; ++i) {
        while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) {
            ++pos;
        }
        if (pos >= json.size()) return false;
        const char* start = json.c_str() + pos;
        char* end = nullptr;
        float value = std::strtof(start, &end);
        if (end == start) return false;
        out[i] = value;
        pos = static_cast<size_t>(end - json.c_str());
        while (pos < json.size() && std::isspace(static_cast<unsigned char>(json[pos]))) {
            ++pos;
        }
        if (i < 2) {
            if (pos >= json.size() || json[pos] != ',') return false;
            ++pos;
        }
    }
    return true;
}

static void _load_manifest_config(DesktopRecaptureContext* ctx) {
    if (!ctx) return;
    std::string manifest_json;
    if (!_read_file(ctx->model_dir + "/manifest.json", manifest_json)) return;
    std::string parsed_version;
    if (_jstr(manifest_json, "model_version", &parsed_version) && !parsed_version.empty()) {
        ctx->model_version = parsed_version;
    }
}

static void _load_preprocess_config(DesktopRecaptureContext* ctx) {
    if (!ctx) return;
    std::string prep_json;
    if (!_read_file(ctx->model_dir + "/preprocess.json", prep_json)) return;

    int parsed_width = 0;
    int parsed_height = 0;
    float parsed_scale = 0.0f;
    float parsed_mean[3] = {};
    float parsed_std[3] = {};
    bool parsed_normalize = false;
    std::string parsed_color_convert;

    if (_jint(prep_json, "width", &parsed_width) && parsed_width > 0) {
        ctx->input_width = parsed_width;
    }
    if (_jint(prep_json, "height", &parsed_height) && parsed_height > 0) {
        ctx->input_height = parsed_height;
    }
    if (_jfloat(prep_json, "scale", &parsed_scale) && parsed_scale > 0.0f) {
        ctx->scale = parsed_scale;
    }
    if (_jbool(prep_json, "normalize", &parsed_normalize)) {
        ctx->normalize = parsed_normalize;
    }
    if (_jfloat_array3(prep_json, "mean", parsed_mean)) {
        std::copy(parsed_mean, parsed_mean + 3, ctx->mean);
    }
    if (_jfloat_array3(prep_json, "std", parsed_std)) {
        for (int i = 0; i < 3; ++i) {
            if (parsed_std[i] > 0.0f) {
                ctx->std_dev[i] = parsed_std[i];
            }
        }
    }
    if (_jstr(prep_json, "color_convert", &parsed_color_convert)) {
        if (parsed_color_convert == "BGR2RGB") {
            ctx->target_color_format = 1;
        } else if (parsed_color_convert == "RGB2BGR") {
            ctx->target_color_format = 0;
        }
    }
}

// ---------------------------------------------------------------------------
// Pre-process: NHWC uint8 BGR → NCHW float32, ImageNet normalised
// ---------------------------------------------------------------------------

#if HAS_ORT
static int _semantic_to_source_channel(int input_color_format, int semantic_channel) {
    if (input_color_format == 0) return 2 - semantic_channel;  // BGR input
    if (input_color_format == 1) return semantic_channel;      // RGB input
    return semantic_channel;
}

static int _output_channel_to_source_channel(const DesktopRecaptureContext* ctx,
                                             const AiImage* img,
                                             int output_channel) {
    if (!ctx || !img) return output_channel;
    if (ctx->target_color_format == 0) {
        int semantic_channel = 2 - output_channel;  // B,G,R output
        return _semantic_to_source_channel(img->color_format, semantic_channel);
    }
    if (ctx->target_color_format == 1) {
        return _semantic_to_source_channel(img->color_format, output_channel);  // R,G,B output
    }
    return output_channel;
}

static float _transform_pixel(float pixel_value,
                              const DesktopRecaptureContext* ctx,
                              int output_channel) {
    float value = pixel_value;
    if (ctx) {
        value *= ctx->scale;
        if (ctx->normalize) {
            float denom = ctx->std_dev[output_channel];
            if (std::fabs(denom) < 1e-12f) denom = 1.0f;
            value = (value - ctx->mean[output_channel]) / denom;
        }
    }
    return value;
}

static std::vector<float> _preprocess(const AiImage* img,
                                       const DesktopRecaptureContext* ctx) {
    int target_w = ctx->input_width;
    int target_h = ctx->input_height;
    int src_w = img->width;
    int src_h = img->height;
    int ch    = img->channels;
    int stride = img->stride > 0 ? img->stride : src_w * ch;

    std::vector<float> out(3 * target_h * target_w);

    // Fast path: when the caller has already resized the image to the target
    // dimensions (e.g. via cv2.resize in Python), skip bilinear interpolation
    // and only perform the normalization.  This is ~10–100× faster than the
    // general bilinear path for large source images.
    if (src_w == target_w && src_h == target_h) {
        for (int y = 0; y < target_h; ++y) {
            for (int x = 0; x < target_w; ++x) {
                for (int c = 0; c < 3; ++c) {
                    int sc = _output_channel_to_source_channel(ctx, img, c);
                    if (sc >= ch) sc = 0;
                    float val = static_cast<float>(
                        img->data[y * stride + x * ch + sc]);
                    val = _transform_pixel(val, ctx, c);
                    out[c * target_h * target_w + y * target_w + x] = val;
                }
            }
        }
        return out;
    }

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
                int sc = _output_channel_to_source_channel(ctx, img, c);
                if (sc >= ch) sc = 0;

                float p00 = static_cast<float>(
                    img->data[y0 * stride + x0 * ch + sc]);
                float p10 = static_cast<float>(
                    img->data[y0 * stride + x1 * ch + sc]);
                float p01 = static_cast<float>(
                    img->data[y1 * stride + x0 * ch + sc]);
                float p11 = static_cast<float>(
                    img->data[y1 * stride + x1 * ch + sc]);
                float val = (1 - wx) * (1 - wy) * p00
                          + wx       * (1 - wy) * p10
                          + (1 - wx) * wy        * p01
                          + wx       * wy        * p11;
                val = _transform_pixel(val, ctx, c);
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
    _load_manifest_config(ctx);
    _load_preprocess_config(ctx);

    return static_cast<AiHandle>(ctx);
}

AI_EXPORT int32_t AiInit(AiHandle handle) {
    if (!handle) return AI_ERR_INVALID_PARAM;
    auto* ctx = static_cast<DesktopRecaptureContext*>(handle);

#if HAS_ORT
    std::string model_path = ctx->model_dir + "/model.onnx";
    ctx->session_opts.SetIntraOpNumThreads(1);
    ctx->session_opts.SetGraphOptimizationLevel(ORT_ENABLE_EXTENDED);

    /* GPU-first strategy: Try CUDA, fallback to CPU */
    try {
        OrtCUDAProviderOptions cuda_options;
        cuda_options.device_id = 0;
        cuda_options.cudnn_conv_algo_search = OrtCudnnConvAlgoSearchDefault;
        // Use 0 (unlimited) instead of SIZE_MAX.  Passing SIZE_MAX causes ORT's
        // CUDA-provider arena code to overflow when computing buffer sizes, which
        // eventually throws std::length_error inside an ORT worker thread and calls
        // std::terminate before our try/catch can intercept it.
        cuda_options.gpu_mem_limit = 0;
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
    } catch (const std::exception& ex) {
        // Catch non-ORT C++ exceptions (e.g. std::length_error from CUDA arena init)
        std::fprintf(stderr, "[desktop_recapture_detect] Unexpected error loading model %s: %s\n",
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

    // Warm-up: run multiple dummy inferences so that CUDA JIT kernel compilation,
    // cuDNN algorithm selection, and GPU memory arena allocation all happen at
    // init time rather than on the first real request.  A single pass primes the
    // kernels; additional passes cause the CUDA memory arena to reach its steady-
    // state size so that it does not need to grow (and re-allocate) on the first
    // real call after a period of GPU idle.
    {
        size_t n = static_cast<size_t>(ctx->input_width) *
                   static_cast<size_t>(ctx->input_height) * 3;
        std::vector<float> dummy(n, 0.0f);
        std::array<int64_t, 4> sh = {1, 3,
            static_cast<int64_t>(ctx->input_height),
            static_cast<int64_t>(ctx->input_width)};
        Ort::MemoryInfo mi = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);

        bool warmup_ok = true;
        for (int wi = 0; wi < 3; ++wi) {
            Ort::Value wt = Ort::Value::CreateTensor<float>(
                mi, dummy.data(), n, sh.data(), sh.size());
            try {
                ctx->session->Run(Ort::RunOptions{nullptr},
                                  ctx->input_names.data(), &wt, 1,
                                  ctx->output_names.data(), ctx->output_names.size());
            } catch (const std::exception& ex) {
                std::fprintf(stderr,
                    "[desktop_recapture_detect] GPU warm-up pass %d failed (non-fatal): %s\n",
                    wi + 1, ex.what());
                warmup_ok = false;
                break;
            } catch (...) {
                std::fprintf(stderr,
                    "[desktop_recapture_detect] GPU warm-up pass %d failed (non-fatal, unknown error)\n",
                    wi + 1);
                warmup_ok = false;
                break;
            }
        }
        if (warmup_ok) {
            std::fprintf(stdout,
                "[desktop_recapture_detect] GPU warm-up completed (3 passes).\n");
        }
    }
#else
    std::fprintf(stderr,
        "[desktop_recapture_detect] ONNXRuntime not available — AiInfer will return stub result.\n");
#endif

    return AI_OK;
}

AI_EXPORT int32_t AiInfer(AiHandle handle, const AiImage* input, AiResult* output) {
    if (!handle || !input || !output) return AI_ERR_INVALID_PARAM;
    auto* ctx = static_cast<DesktopRecaptureContext*>(handle);

#if HAS_ORT
    if (!ctx->session) {
        _set_result(output, AI_ERR_LOAD_FAILED, nullptr, "Model not loaded");
        return AI_ERR_LOAD_FAILED;
    }

    std::vector<float> tensor_data;
    try {
        tensor_data = _preprocess(input, ctx);
    } catch (const std::exception& ex) {
        _set_result(output, AI_ERR_INFER_FAILED, nullptr, ex.what());
        return AI_ERR_INFER_FAILED;
    }

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

    // Let ORT allocate the output tensor — pre-allocating a CPU buffer and passing
    // it to Run() causes ORT's CUDA provider to allocate internal staging buffers
    // whose size computation can overflow, throwing std::length_error inside ORT.
    std::vector<Ort::Value> outputs;
    try {
        outputs = ctx->session->Run(
            Ort::RunOptions{nullptr},
            ctx->input_names.data(), &input_tensor,           1,
            ctx->output_names.data(), ctx->output_names.size());
    } catch (const std::exception& ex) {
        _set_result(output, AI_ERR_INFER_FAILED, nullptr, ex.what());
        return AI_ERR_INFER_FAILED;
    } catch (...) {
        _set_result(output, AI_ERR_INFER_FAILED, nullptr, "Unknown inference error");
        return AI_ERR_INFER_FAILED;
    }

    if (outputs.empty() || !outputs[0].IsTensor()) {
        _set_result(output, AI_ERR_INFER_FAILED, nullptr, "No output tensor returned");
        return AI_ERR_INFER_FAILED;
    }

    // EfficientNet-B0 output: single logit → sigmoid = P(fake)
    float logit = outputs[0].GetTensorData<float>()[0];
    float prob_fake = 1.0f / (1.0f + std::exp(-logit));
    float prob_real = 1.0f - prob_fake;

    bool is_fake = (prob_fake > 0.5f);

    // Diagnostic log: helps operators verify model output and detect bias issues
    // (e.g. model always outputting positive logits regardless of input).
    std::fprintf(stdout,
        "[desktop_recapture_detect] logit=%.4f prob_fake=%.4f is_fake=%s\n",
        static_cast<double>(logit),
        static_cast<double>(prob_fake),
        is_fake ? "true" : "false");
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
    ctx->model_version   = new_ctx->model_version;
    ctx->input_width     = new_ctx->input_width;
    ctx->input_height    = new_ctx->input_height;
    ctx->scale           = new_ctx->scale;
    ctx->normalize       = new_ctx->normalize;
    ctx->target_color_format = new_ctx->target_color_format;
    std::copy(new_ctx->mean, new_ctx->mean + 3, ctx->mean);
    std::copy(new_ctx->std_dev, new_ctx->std_dev + 3, ctx->std_dev);
    ctx->infer_count     = 0;

    AiDestroy(new_h);
    return AI_OK;
}

AI_EXPORT int32_t AiGetInfo(AiHandle handle, char* info_buf, int32_t buf_len) {
    auto* ctx = static_cast<DesktopRecaptureContext*>(handle);
    std::string model_version = (ctx && !ctx->model_version.empty()) ? ctx->model_version : "unknown";
    char info[256];
    std::snprintf(info, sizeof(info),
        "{\"capability\":\"desktop_recapture_detect\","
        "\"capability_name_cn\":\"桌面翻拍检测\","
        "\"abi_version\":\"10000\","
        "\"model_version\":\"%s\","
        "\"company\":\"agilestar.cn\"}",
        model_version.c_str());
    int32_t needed = static_cast<int32_t>(std::strlen(info));
    if (!info_buf || buf_len <= needed) return needed;
    std::memcpy(info_buf, info, static_cast<size_t>(needed) + 1);
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
