#ifndef AGILESTAR_AGFACE_FEATURE_PLUGIN_IMPL_H
#define AGILESTAR_AGFACE_FEATURE_PLUGIN_IMPL_H

/**
 * @file feature_plugin_impl.h
 * @brief 供 agface_face_feature_* 能力插件复用的模板实现。
 *
 * 每个 feature 插件只需提供一个 default_plugin_name/version 字符串并包含本头
 * 文件即可完成 `Ai*` C ABI 全套导出。不同模型的差异（输入大小、mean/norm、
 * 输出 blob 名、特征维度）全部通过 manifest.json 驱动，无需改代码。
 *
 * 使用方式（在 plugin 的单一 .cpp 中）：
 *
 *   #define AGFACE_FEATURE_PLUGIN_NAME    "agface_face_feature_residual256"
 *   #define AGFACE_FEATURE_PLUGIN_VERSION "1.0.0"
 *   #include "agface/feature_plugin_impl.h"
 *
 * 之后本头文件会定义完整的 extern "C" Ai* 符号导出。整个 plugin.cpp 不超过
 * 10 行，模型差异交给 manifest。
 */

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <ncnn/net.h>
#include <opencv2/core.hpp>

#include "agface/feature_extract.h"
#include "agface/image_utils.h"
#include "agface/instance_pool.h"
#include "agface/json_result.h"
#include "agface/manifest.h"
#include "agface/ncnn_session.h"
#include "ai_capability.h"
#include "ai_types.h"

#ifndef AGFACE_FEATURE_PLUGIN_NAME
#  error "AGFACE_FEATURE_PLUGIN_NAME must be defined before including feature_plugin_impl.h"
#endif
#ifndef AGFACE_FEATURE_PLUGIN_VERSION
#  define AGFACE_FEATURE_PLUGIN_VERSION "1.0.0"
#endif

namespace agface_feature_plugin {

struct Context {
    std::string          model_dir;
    agface::NcnnManifest manifest;

    std::shared_ptr<ncnn::Net>                                       shared_net;
    std::unique_ptr<agface::InstancePool<agface::NcnnSession>>       pool;

    std::mutex reload_mu;
    bool       initialized = false;
};

inline bool buildNetAndPool(Context* ctx, std::string* err) {
    auto fail = [&](const std::string& m) {
        if (err) *err = m;
        return false;
    };

    auto net = std::make_shared<ncnn::Net>();
    net->opt.lightmode          = true;
    net->opt.num_threads        = 1;
    net->opt.use_vulkan_compute = false;

    if (net->load_param(ctx->manifest.param_path.c_str()) != 0)
        return fail("ncnn load_param failed: " + ctx->manifest.param_path);
    if (net->load_model(ctx->manifest.bin_path.c_str()) != 0)
        return fail("ncnn load_model failed: " + ctx->manifest.bin_path);

    int pool_size = static_cast<int>(std::thread::hardware_concurrency());
    if (pool_size < 2) pool_size = 2;
    pool_size = pool_size / 2;
    if (pool_size < 1) pool_size = 1;

    auto factory = [net]() -> std::unique_ptr<agface::NcnnSession> {
        return std::make_unique<agface::NcnnSession>(net);
    };
    ctx->shared_net = std::move(net);
    ctx->pool = std::make_unique<agface::InstancePool<agface::NcnnSession>>(
        pool_size, factory);
    return true;
}

}  // namespace agface_feature_plugin

extern "C" {

AI_EXPORT int32_t AiGetAbiVersion(void) { return AI_ABI_VERSION; }

AI_EXPORT AiHandle AiCreate(const char* model_dir, const char* /*config_json*/) {
    if (!model_dir || !*model_dir) return nullptr;
    auto ctx = std::make_unique<agface_feature_plugin::Context>();
    ctx->model_dir = model_dir;

    std::string err;
    if (!agface::loadManifestFromDir(ctx->model_dir, &ctx->manifest, &err)) {
        std::fprintf(stderr, "[%s] load manifest failed: %s\n",
                     AGFACE_FEATURE_PLUGIN_NAME, err.c_str());
        return nullptr;
    }
    return ctx.release();
}

AI_EXPORT int32_t AiInit(AiHandle handle) {
    auto* ctx = static_cast<agface_feature_plugin::Context*>(handle);
    if (!ctx) return AI_ERR_INVALID_PARAM;
    if (ctx->initialized) return AI_OK;

    std::lock_guard<std::mutex> lk(ctx->reload_mu);
    std::string                 err;
    if (!agface_feature_plugin::buildNetAndPool(ctx, &err)) {
        std::fprintf(stderr, "[%s] init failed: %s\n",
                     AGFACE_FEATURE_PLUGIN_NAME, err.c_str());
        return AI_ERR_LOAD_FAILED;
    }
    ctx->initialized = true;
    return AI_OK;
}

AI_EXPORT int32_t AiInfer(AiHandle handle, const AiImage* input, AiResult* output) {
    if (!handle || !input || !output) return AI_ERR_INVALID_PARAM;
    auto* ctx = static_cast<agface_feature_plugin::Context*>(handle);
    if (!ctx->initialized) {
        agface::fillError(output, AI_ERR_INVALID_PARAM,
                          AGFACE_FEATURE_PLUGIN_NAME " not initialized");
        return AI_ERR_INVALID_PARAM;
    }

    cv::Mat bgr;
    if (!agface::aiImageToBgrMat(input, &bgr) || bgr.empty()) {
        agface::fillError(output, AI_ERR_IMAGE_DECODE,
                          AGFACE_FEATURE_PLUGIN_NAME ": invalid AiImage");
        return AI_ERR_IMAGE_DECODE;
    }

    auto session = ctx->pool->acquire(5000);
    if (!session) {
        agface::fillError(output, AI_ERR_INTERNAL,
                          AGFACE_FEATURE_PLUGIN_NAME ": session acquire timeout");
        return AI_ERR_INTERNAL;
    }

    std::vector<float> feat;
    std::string        err;
    try {
        if (!agface::extractFaceFeature(session.get(), ctx->manifest, bgr,
                                        /*landmarks=*/nullptr, &feat, &err)) {
            agface::fillError(output, AI_ERR_INFER_FAILED, err.c_str());
            return AI_ERR_INFER_FAILED;
        }
    } catch (const std::exception& e) {
        agface::fillError(output, AI_ERR_INTERNAL, e.what());
        return AI_ERR_INTERNAL;
    } catch (...) {
        agface::fillError(output, AI_ERR_INTERNAL,
                          AGFACE_FEATURE_PLUGIN_NAME ": unknown exception");
        return AI_ERR_INTERNAL;
    }

    nlohmann::json payload;
    payload["feature"] = feat;
    payload["dim"]     = static_cast<int>(feat.size());
    payload["l2_normalized"] = true;
    agface::fillResult(output, AI_OK, payload, nullptr);
    return AI_OK;
}

AI_EXPORT int32_t AiReload(AiHandle handle, const char* new_model_dir) {
    if (!handle || !new_model_dir || !*new_model_dir) return AI_ERR_INVALID_PARAM;
    auto* ctx = static_cast<agface_feature_plugin::Context*>(handle);
    std::lock_guard<std::mutex> lk(ctx->reload_mu);

    agface_feature_plugin::Context staging;
    staging.model_dir = new_model_dir;
    std::string err;
    if (!agface::loadManifestFromDir(staging.model_dir, &staging.manifest, &err)) {
        std::fprintf(stderr, "[%s] reload manifest failed: %s\n",
                     AGFACE_FEATURE_PLUGIN_NAME, err.c_str());
        return AI_ERR_MODEL_CORRUPT;
    }
    if (!agface_feature_plugin::buildNetAndPool(&staging, &err)) {
        std::fprintf(stderr, "[%s] reload build failed: %s\n",
                     AGFACE_FEATURE_PLUGIN_NAME, err.c_str());
        return AI_ERR_LOAD_FAILED;
    }
    ctx->manifest   = std::move(staging.manifest);
    ctx->shared_net = std::move(staging.shared_net);
    ctx->pool       = std::move(staging.pool);
    ctx->model_dir  = std::move(staging.model_dir);
    return AI_OK;
}

AI_EXPORT int32_t AiGetInfo(AiHandle handle, char* info_buf, int32_t buf_len) {
    if (!handle) return -static_cast<int32_t>(AI_ERR_INVALID_PARAM);
    auto* ctx = static_cast<agface_feature_plugin::Context*>(handle);

    nlohmann::json j;
    j["name"]        = ctx->manifest.name.empty() ? AGFACE_FEATURE_PLUGIN_NAME
                                                  : ctx->manifest.name;
    j["version"]     = ctx->manifest.version.empty() ? AGFACE_FEATURE_PLUGIN_VERSION
                                                     : ctx->manifest.version;
    j["backend"]     = "ncnn";
    j["feature_dim"] = ctx->manifest.feature_dim;
    j["input"]       = {
        {"blob", ctx->manifest.input_blob},
        {"base_size", ctx->manifest.input_base_size},
        {"color", ctx->manifest.input_color},
    };
    j["output"] = {
        {"blob", ctx->manifest.output_blob},
        {"l2_normalized", true},
    };
    const std::string s   = j.dump();
    const int32_t     len = static_cast<int32_t>(s.size());
    if (!info_buf || buf_len <= 0) return len;
    if (buf_len < len + 1) return len;
    std::memcpy(info_buf, s.c_str(), len);
    info_buf[len] = '\0';
    return len;
}

AI_EXPORT void AiDestroy(AiHandle handle) {
    if (!handle) return;
    delete static_cast<agface_feature_plugin::Context*>(handle);
}

AI_EXPORT void AiFreeResult(AiResult* result) { agface::freeResult(result); }

}  // extern "C"

#endif  // AGILESTAR_AGFACE_FEATURE_PLUGIN_IMPL_H
