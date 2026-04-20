/**
 * @file agface_face_detect.cpp
 * @brief agface_face_detect 能力插件 —— 完整 Ai* C ABI 实现。
 *
 * 迁移自 ai_agface/src/ai_modules/face_detect/face_detect_retina.cpp。
 * License 校验由 libai_runtime.so 在 Runtime 层统一处理，此处不再内置。
 *
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#include "agface_face_detect.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>
#include <thread>

#include <ncnn/net.h>
#include <opencv2/core.hpp>
#include <opencv2/imgproc.hpp>

#include "agface/image_utils.h"
#include "agface/json_result.h"
#include "ai_capability.h"
#include "ai_types.h"

#ifndef AI_CAPABILITY_NAME
#  define AI_CAPABILITY_NAME "agface_face_detect"
#endif
#ifndef AI_CAPABILITY_VERSION
#  define AI_CAPABILITY_VERSION "1.0.0"
#endif

namespace {

// ─── 构造共享 ncnn::Net + 实例池 ────────────────────────────────────────────
bool buildSharedNetAndPool(AgfaceFaceDetectContext* ctx, std::string* err) {
    auto fail = [&](const std::string& m) {
        if (err) *err = m;
        return false;
    };

    auto net = std::make_shared<ncnn::Net>();
    net->opt.lightmode          = true;
    net->opt.num_threads        = 1;
    net->opt.use_vulkan_compute = false;

    if (net->load_param(ctx->manifest.param_path.c_str()) != 0) {
        return fail("ncnn load_param failed: " + ctx->manifest.param_path);
    }
    if (net->load_model(ctx->manifest.bin_path.c_str()) != 0) {
        return fail("ncnn load_model failed: " + ctx->manifest.bin_path);
    }

    int pool_size = static_cast<int>(std::thread::hardware_concurrency());
    if (pool_size < 2) pool_size = 2;
    pool_size = pool_size / 2;
    if (pool_size < 1) pool_size = 1;

    auto factory = [net]() -> std::unique_ptr<agface::NcnnSession> {
        return std::make_unique<agface::NcnnSession>(net);
    };
    auto pool = std::make_unique<agface::InstancePool<agface::NcnnSession>>(
        pool_size, factory);

    ctx->shared_net = std::move(net);
    ctx->pool       = std::move(pool);
    return true;
}

// ─── 核心推理：与旧 FaceDetectRetina::detect 等价 ────────────────────────────
nlohmann::json detectInternal(AgfaceFaceDetectContext* ctx,
                              const cv::Mat&           image,
                              int32_t*                 error_out) {
    nlohmann::json result;
    result["faces"]      = nlohmann::json::array();
    result["image_size"] = {image.cols, image.rows};

    if (!ctx->pool) {
        if (error_out) *error_out = AI_ERR_INTERNAL;
        return result;
    }

    auto session = ctx->pool->acquire(5000);
    if (!session) {
        if (error_out) *error_out = AI_ERR_INTERNAL;
        return result;
    }

    const int max_dim = ctx->manifest.max_image_dim;
    cv::Mat   processed = image;
    float     scale     = 1.0f;
    int       src_long  = std::max(image.cols, image.rows);
    if (src_long > max_dim) {
        scale = static_cast<float>(max_dim) / src_long;
        cv::resize(image, processed,
                   cv::Size(static_cast<int>(image.cols * scale),
                            static_cast<int>(image.rows * scale)));
    }
    const int w = processed.cols;
    const int h = processed.rows;

    // 输入尺寸：in_w × in_h ≈ base_size²，保持宽高比
    const float base   = static_cast<float>(ctx->manifest.input_base_size);
    const float aspect = static_cast<float>(w) / static_cast<float>(h);
    const int   in_w   = static_cast<int>(base * std::sqrt(aspect));
    const int   in_h   = static_cast<int>(base / std::sqrt(aspect));

    ncnn::Mat in = ncnn::Mat::from_pixels_resize(
        processed.data, ncnn::Mat::PIXEL_BGR, w, h, in_w, in_h);
    in.substract_mean_normalize(ctx->manifest.mean.data(), nullptr);

    ncnn::Extractor ex = session->createExtractor();
    ex.input(ctx->manifest.input_blob.c_str(), in);

    ncnn::Mat out;
    if (ex.extract(ctx->manifest.output_blob.c_str(), out) != 0) {
        if (error_out) *error_out = AI_ERR_INFER_FAILED;
        return result;
    }

    const float inv_scale = 1.0f / scale;
    const float threshold = ctx->manifest.score_threshold;
    const int   min_face  = ctx->manifest.min_face;

    for (int i = 0; i < out.h; ++i) {
        const float* vals = out.row(i);
        // SSD 输出格式：[class_id, confidence, x1, y1, x2, y2]（归一化到 0..1）
        const float conf = vals[1];
        if (conf < threshold) continue;

        const float x1 = vals[2] * w;
        const float y1 = vals[3] * h;
        const float x2 = vals[4] * w;
        const float y2 = vals[5] * h;
        const float bw = x2 - x1 + 1.0f;
        const float bh = y2 - y1 + 1.0f;
        const float sz = (bw + bh) * 0.5f;
        if (sz < static_cast<float>(min_face)) continue;

        nlohmann::json face;
        face["bbox"] = {x1 * inv_scale, y1 * inv_scale, bw * inv_scale, bh * inv_scale};
        face["confidence"] = conf;
        face["class_id"]   = static_cast<int>(vals[0]);
        result["faces"].push_back(std::move(face));
    }

    if (error_out) *error_out = AI_OK;
    return result;
}

}  // namespace

// ═══════════════════════════════════════════════════════════════════════════
// C ABI export — @/cpp/sdk/ai_capability.h
// ═══════════════════════════════════════════════════════════════════════════

extern "C" {

AI_EXPORT int32_t AiGetAbiVersion(void) { return AI_ABI_VERSION; }

AI_EXPORT AiHandle AiCreate(const char* model_dir, const char* /*config_json*/) {
    if (!model_dir || !*model_dir) return nullptr;

    auto ctx       = std::make_unique<AgfaceFaceDetectContext>();
    ctx->model_dir = model_dir;

    std::string err;
    if (!agface::loadManifestFromDir(ctx->model_dir, &ctx->manifest, &err)) {
        std::fprintf(stderr, "[agface_face_detect] load manifest failed: %s\n",
                     err.c_str());
        return nullptr;
    }

    return ctx.release();  // 所有权转给调用方，AiDestroy 时收回
}

AI_EXPORT int32_t AiInit(AiHandle handle) {
    auto* ctx = static_cast<AgfaceFaceDetectContext*>(handle);
    if (!ctx) return AI_ERR_INVALID_PARAM;
    if (ctx->initialized) return AI_OK;

    std::lock_guard<std::mutex> lk(ctx->reload_mu);
    std::string                 err;
    if (!buildSharedNetAndPool(ctx, &err)) {
        std::fprintf(stderr, "[agface_face_detect] init failed: %s\n", err.c_str());
        return AI_ERR_LOAD_FAILED;
    }
    ctx->initialized = true;
    return AI_OK;
}

AI_EXPORT int32_t AiInfer(AiHandle handle, const AiImage* input, AiResult* output) {
    if (!handle || !input || !output) return AI_ERR_INVALID_PARAM;

    auto* ctx = static_cast<AgfaceFaceDetectContext*>(handle);
    if (!ctx->initialized) {
        agface::fillError(output, AI_ERR_INVALID_PARAM,
                          "agface_face_detect not initialized");
        return AI_ERR_INVALID_PARAM;
    }

    cv::Mat bgr;
    if (!agface::aiImageToBgrMat(input, &bgr) || bgr.empty()) {
        agface::fillError(output, AI_ERR_IMAGE_DECODE,
                          "agface_face_detect: invalid AiImage");
        return AI_ERR_IMAGE_DECODE;
    }

    int32_t err_code = AI_OK;
    try {
        const nlohmann::json payload = detectInternal(ctx, bgr, &err_code);
        if (err_code != AI_OK) {
            agface::fillResult(output, err_code, payload,
                               "agface_face_detect: inference error");
            return err_code;
        }
        agface::fillResult(output, AI_OK, payload, nullptr);
        return AI_OK;
    } catch (const std::exception& e) {
        agface::fillError(output, AI_ERR_INTERNAL, e.what());
        return AI_ERR_INTERNAL;
    } catch (...) {
        agface::fillError(output, AI_ERR_INTERNAL,
                          "agface_face_detect: unknown exception");
        return AI_ERR_INTERNAL;
    }
}

AI_EXPORT int32_t AiReload(AiHandle handle, const char* new_model_dir) {
    if (!handle || !new_model_dir || !*new_model_dir) return AI_ERR_INVALID_PARAM;

    auto* ctx = static_cast<AgfaceFaceDetectContext*>(handle);
    std::lock_guard<std::mutex> lk(ctx->reload_mu);

    AgfaceFaceDetectContext staging;
    staging.model_dir = new_model_dir;

    std::string err;
    if (!agface::loadManifestFromDir(staging.model_dir, &staging.manifest, &err)) {
        std::fprintf(stderr, "[agface_face_detect] reload manifest failed: %s\n",
                     err.c_str());
        return AI_ERR_MODEL_CORRUPT;
    }
    if (!buildSharedNetAndPool(&staging, &err)) {
        std::fprintf(stderr, "[agface_face_detect] reload build failed: %s\n",
                     err.c_str());
        return AI_ERR_LOAD_FAILED;
    }

    // 原子替换（旧 pool 在析构时等待所有 ScopedInstance 归还）
    ctx->manifest   = std::move(staging.manifest);
    ctx->shared_net = std::move(staging.shared_net);
    ctx->pool       = std::move(staging.pool);
    ctx->model_dir  = std::move(staging.model_dir);
    return AI_OK;
}

AI_EXPORT int32_t AiGetInfo(AiHandle handle, char* info_buf, int32_t buf_len) {
    if (!handle) return -static_cast<int32_t>(AI_ERR_INVALID_PARAM);
    auto* ctx = static_cast<AgfaceFaceDetectContext*>(handle);

    nlohmann::json j;
    j["name"]    = ctx->manifest.name.empty() ? AI_CAPABILITY_NAME : ctx->manifest.name;
    j["version"] = ctx->manifest.version.empty() ? AI_CAPABILITY_VERSION
                                                 : ctx->manifest.version;
    j["backend"] = "ncnn";
    j["input"]   = {
        {"blob", ctx->manifest.input_blob},
        {"base_size", ctx->manifest.input_base_size},
        {"color", ctx->manifest.input_color},
    };
    j["output"] = {
        {"blob", ctx->manifest.output_blob},
        {"format", ctx->manifest.output_format},
    };
    j["thresholds"] = {
        {"score", ctx->manifest.score_threshold},
        {"min_face", ctx->manifest.min_face},
        {"max_image_dim", ctx->manifest.max_image_dim},
    };

    const std::string s   = j.dump();
    const int32_t     len = static_cast<int32_t>(s.size());
    if (!info_buf || buf_len <= 0) return len;
    if (buf_len < len + 1) return len;  // 告知所需大小
    std::memcpy(info_buf, s.c_str(), len);
    info_buf[len] = '\0';
    return len;
}

AI_EXPORT void AiDestroy(AiHandle handle) {
    if (!handle) return;
    auto* ctx = static_cast<AgfaceFaceDetectContext*>(handle);
    delete ctx;
}

AI_EXPORT void AiFreeResult(AiResult* result) {
    agface::freeResult(result);
}

}  // extern "C"
