#include <algorithm>
#include <cstdio>
#include <cstring>
#include <exception>
#include <fstream>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

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
           fileExists(model_dir + "/detection/model_1.param") &&
           fileExists(model_dir + "/detection/model_1.bin") &&
           fileExists(model_dir + "/detection/model_2.param") &&
           fileExists(model_dir + "/detection/model_2.bin") &&
           fileExists(model_dir + "/detection/model_3.param") &&
           fileExists(model_dir + "/detection/model_3.bin") &&
           fileExists(model_dir + "/detection/modelht.param") &&
           fileExists(model_dir + "/detection/modelht.bin") &&
           fileExists(model_dir + "/detection/yolov7s320face.param") &&
           fileExists(model_dir + "/detection/yolov7s320face.bin") &&
           fileExists(model_dir + "/detection/face_landmark_with_attention.param") &&
           fileExists(model_dir + "/detection/face_landmark_with_attention.bin");
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

    agface::LegacyMeshPose mesh_pose = ctx->vision->detectLegacyMeshPose(work, det.face_rect);
    std::string angle = agface::buildAngleStringLegacy(det, work);
    if (mesh_pose.valid) {
        char angle_buf[96];
        std::snprintf(angle_buf, sizeof(angle_buf), "[%.2f,%.2f,%.2f]", mesh_pose.pitch, mesh_pose.yaw, mesh_pose.roll);
        angle = angle_buf;
    }

    float glasses = agface::estimateGlassesLegacy(work, det.face_rect);
    float mask = agface::estimateMaskLegacy(work, det.face_rect);
    float hat = agface::estimateHatLegacy(work, det.face_rect);
    float fake = agface::clamp01(1.0f - ctx->vision->detectLegacyLiveConfidence(work, det.face_rect));
    float eye_closed = mesh_pose.valid ? mesh_pose.eye_closed : agface::estimateEyeClosedLegacy(work, det.face_rect);

    cv::Rect face = det.face_rect;
    cv::Rect roi = face;
    roi.x -= static_cast<int>(face.width * 0.3f);
    roi.width = static_cast<int>(face.width * 1.6f);
    roi.y -= static_cast<int>(face.height * 0.6f);
    roi.height = static_cast<int>(face.height * 1.85f);
    roi &= cv::Rect(0, 0, work.cols, work.rows);
    if (roi.width > 1 && roi.height > 1) {
        std::vector<agface::LegacyAttrObject> objs = ctx->vision->detectLegacyFaceAttributes(work(roi).clone());
        const cv::Rect_<float> face_rect_global(static_cast<float>(face.x), static_cast<float>(face.y),
                                                static_cast<float>(face.width), static_cast<float>(face.height));
        const float center_x = face.x + face.width * 0.5f;
        const float center_y = face.y + face.height * 0.5f;
        auto intersectionArea = [](const cv::Rect_<float>& a, const cv::Rect_<float>& b) -> float {
            const float x1 = std::max(a.x, b.x);
            const float y1 = std::max(a.y, b.y);
            const float x2 = std::min(a.x + a.width, b.x + b.width);
            const float y2 = std::min(a.y + a.height, b.y + b.height);
            const float w = x2 - x1;
            const float h = y2 - y1;
            return (w > 0.0f && h > 0.0f) ? (w * h) : 0.0f;
        };
        for (const auto& obj : objs) {
            cv::Rect_<float> obj_rect = obj.rect;
            obj_rect.x += roi.x;
            obj_rect.y += roi.y;
            const float obj_area = obj_rect.width * obj_rect.height;
            const float overlap = intersectionArea(obj_rect, face_rect_global) /
                                  (obj_area > 1.0f ? obj_area : 1.0f);
            if ((obj.label == 1 || obj.label == 7) && overlap > 0.25f && obj.prob >= 0.45f) {
                glasses = std::max(glasses, obj.prob);
            }
            if (obj.label == 2 && overlap > 0.02f && obj.prob >= 0.55f) {
                mask = std::max(mask, obj.prob);
            }
            if (obj.label == 3 && obj_rect.y < face.y + face.height * 0.45f && obj.prob >= 0.70f) {
                hat = std::max(hat, obj.prob);
            }
            if (obj.label == 6 && center_x > obj_rect.x && center_x < obj_rect.x + obj_rect.width &&
                center_y > obj_rect.y && center_y < obj_rect.y + obj_rect.height) {
                fake = 1.0f;
            }
        }
    }

    result["status"] = 1;
    result["angle"] = angle;
    result["glasses"] = glasses;
    result["mask"] = mask;
    result["facew"] = static_cast<float>(det.face_rect.width) / static_cast<float>(std::max(1, work.cols));
    result["eyeclosed"] = eye_closed;
    result["hat"] = hat;
    result["fake"] = fake;
    result["face_bbox"] = {det.face_rect.x, det.face_rect.y, det.face_rect.width, det.face_rect.height};
    if (error_out) *error_out = AI_OK;
    return result;
}

bool initInternal(Context* ctx, std::string* err) {
    ctx->vision = std::make_unique<agface::LegacyVisionContext>();
    if (ctx->vision->initFacePropertyModels(ctx->model_dir, 2)) {
        return true;
    }
    ctx->vision.reset();
    if (err) *err = "failed to init legacy face_property models";
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
        std::fprintf(stderr, "[agface_face_property] init failed: %s\n", err.c_str());
        return AI_ERR_LOAD_FAILED;
    }
    ctx->initialized = true;
    return AI_OK;
}

AI_EXPORT int32_t AiInfer(AiHandle handle, const AiImage* input, AiResult* output) {
    if (!handle || !input || !output) return AI_ERR_INVALID_PARAM;
    auto* ctx = static_cast<Context*>(handle);
    if (!ctx->initialized) {
        agface::fillError(output, AI_ERR_INVALID_PARAM, "agface_face_property not initialized");
        return AI_ERR_INVALID_PARAM;
    }

    cv::Mat bgr;
    if (!agface::aiImageToBgrMat(input, &bgr) || bgr.empty()) {
        agface::fillError(output, AI_ERR_IMAGE_DECODE, "agface_face_property: invalid AiImage");
        return AI_ERR_IMAGE_DECODE;
    }

    int32_t err_code = AI_OK;
    try {
        nlohmann::json payload = inferInternal(ctx, bgr, &err_code);
        if (err_code != AI_OK) {
            agface::fillResult(output, err_code, payload, "agface_face_property: inference error");
            return err_code;
        }
        agface::fillResult(output, AI_OK, payload, nullptr);
        return AI_OK;
    } catch (const std::exception& e) {
        agface::fillError(output, AI_ERR_INTERNAL, e.what());
        return AI_ERR_INTERNAL;
    } catch (...) {
        agface::fillError(output, AI_ERR_INTERNAL, "agface_face_property: unknown exception");
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
        std::fprintf(stderr, "[agface_face_property] reload failed: %s\n", err.c_str());
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
    j["name"] = "agface_face_property";
    j["version"] = "1.0.0";
    j["backend"] = "ncnn";
    j["legacy_family"] = "ai_agface";
    j["task"] = "face_property";
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
