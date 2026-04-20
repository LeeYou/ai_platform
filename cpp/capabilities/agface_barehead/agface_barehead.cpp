#include <cstdio>
#include <cstring>
#include <exception>
#include <fstream>
#include <memory>
#include <mutex>
#include <string>

#include <nlohmann/json.hpp>
#include <opencv2/core.hpp>

#include "agface/image_utils.h"
#include "agface/json_result.h"
#include "agface/legacy_vision_context.h"
#include "agface/vision_analysis_common.h"
#include "ai_capability.h"
#include "ai_types.h"

namespace {

bool fileExists(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    return f.good();
}

bool validateModelDir(const std::string& model_dir) {
    return fileExists(model_dir + "/manifest.json") &&
           fileExists(model_dir + "/detection/detection.param") &&
           fileExists(model_dir + "/detection/detection.bin") &&
           fileExists(model_dir + "/detection/det3.param") &&
           fileExists(model_dir + "/detection/det3.bin") &&
           fileExists(model_dir + "/detection/modelht.param") &&
           fileExists(model_dir + "/detection/modelht.bin");
}

struct Context {
    std::string model_dir;
    std::unique_ptr<agface::LegacyVisionContext> vision;
    std::mutex reload_mu;
    bool initialized = false;
};

nlohmann::json inferInternal(Context* ctx, const cv::Mat& image, int32_t* error_out) {
    nlohmann::json result;
    cv::Mat work = agface::preprocessLegacyVisionImage(image);
    agface::FaceDetectResult det = ctx->vision->detector().detectLargestFace(work);
    if (!det.found) {
        if (error_out) *error_out = AI_ERR_INFER_FAILED;
        result["status"] = 0;
        result["message"] = "no face";
        return result;
    }

    const float confidence = agface::clamp01(ctx->vision->detectBareheadConfidence(work, det.face_rect));
    result["status"] = 1;
    result["result"] = confidence >= 0.70f ? 1 : 0;
    result["confidence"] = confidence;
    result["face_bbox"] = {det.face_rect.x, det.face_rect.y, det.face_rect.width, det.face_rect.height};
    if (error_out) *error_out = AI_OK;
    return result;
}

bool initInternal(Context* ctx, std::string* err) {
    ctx->vision = std::make_unique<agface::LegacyVisionContext>();
    if (ctx->vision->initBareheadModels(ctx->model_dir, 2)) {
        return true;
    }
    ctx->vision.reset();
    if (err) *err = "failed to init legacy barehead models";
    return false;
}

}  // namespace

extern "C" {

AI_EXPORT int32_t AiGetAbiVersion(void) { return AI_ABI_VERSION; }

AI_EXPORT AiHandle AiCreate(const char* model_dir, const char* /*config_json*/) {
    if (!model_dir || !*model_dir) return nullptr;
    if (!validateModelDir(model_dir)) return nullptr;
    auto ctx = std::make_unique<Context>();
    ctx->model_dir = model_dir;
    return ctx.release();
}

AI_EXPORT int32_t AiInit(AiHandle handle) {
    auto* ctx = static_cast<Context*>(handle);
    if (!ctx) return AI_ERR_INVALID_PARAM;
    if (ctx->initialized) return AI_OK;

    std::lock_guard<std::mutex> lk(ctx->reload_mu);
    std::string err;
    if (!initInternal(ctx, &err)) {
        std::fprintf(stderr, "[agface_barehead] init failed: %s\n", err.c_str());
        return AI_ERR_LOAD_FAILED;
    }
    ctx->initialized = true;
    return AI_OK;
}

AI_EXPORT int32_t AiInfer(AiHandle handle, const AiImage* input, AiResult* output) {
    if (!handle || !input || !output) return AI_ERR_INVALID_PARAM;
    auto* ctx = static_cast<Context*>(handle);
    if (!ctx->initialized) {
        agface::fillError(output, AI_ERR_INVALID_PARAM, "agface_barehead not initialized");
        return AI_ERR_INVALID_PARAM;
    }

    cv::Mat bgr;
    if (!agface::aiImageToBgrMat(input, &bgr) || bgr.empty()) {
        agface::fillError(output, AI_ERR_IMAGE_DECODE, "agface_barehead: invalid AiImage");
        return AI_ERR_IMAGE_DECODE;
    }

    int32_t err_code = AI_OK;
    try {
        nlohmann::json payload = inferInternal(ctx, bgr, &err_code);
        if (err_code != AI_OK) {
            agface::fillResult(output, err_code, payload, "agface_barehead: inference error");
            return err_code;
        }
        agface::fillResult(output, AI_OK, payload, nullptr);
        return AI_OK;
    } catch (const std::exception& e) {
        agface::fillError(output, AI_ERR_INTERNAL, e.what());
        return AI_ERR_INTERNAL;
    } catch (...) {
        agface::fillError(output, AI_ERR_INTERNAL, "agface_barehead: unknown exception");
        return AI_ERR_INTERNAL;
    }
}

AI_EXPORT int32_t AiReload(AiHandle handle, const char* new_model_dir) {
    if (!handle || !new_model_dir || !*new_model_dir) return AI_ERR_INVALID_PARAM;
    auto* ctx = static_cast<Context*>(handle);
    std::lock_guard<std::mutex> lk(ctx->reload_mu);

    Context staging;
    staging.model_dir = new_model_dir;
    std::string err;
    if (!initInternal(&staging, &err)) {
        std::fprintf(stderr, "[agface_barehead] reload failed: %s\n", err.c_str());
        return AI_ERR_LOAD_FAILED;
    }
    staging.initialized = true;
    ctx->model_dir = std::move(staging.model_dir);
    ctx->vision = std::move(staging.vision);
    ctx->initialized = true;
    return AI_OK;
}

AI_EXPORT int32_t AiGetInfo(AiHandle handle, char* info_buf, int32_t buf_len) {
    if (!handle) return -static_cast<int32_t>(AI_ERR_INVALID_PARAM);
    nlohmann::json j;
    j["name"] = "agface_barehead";
    j["version"] = "1.0.0";
    j["backend"] = "ncnn";
    j["legacy_family"] = "ai_agface";
    j["task"] = "barehead";
    const std::string s = j.dump();
    const int32_t len = static_cast<int32_t>(s.size());
    if (!info_buf || buf_len <= 0) return len;
    if (buf_len < len + 1) return len;
    std::memcpy(info_buf, s.c_str(), len);
    info_buf[len] = '\0';
    return len;
}

AI_EXPORT void AiDestroy(AiHandle handle) {
    delete static_cast<Context*>(handle);
}

AI_EXPORT void AiFreeResult(AiResult* result) {
    agface::freeResult(result);
}

}
