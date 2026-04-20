#ifndef AGILESTAR_AGFACE_LEGACY_VISION_CONTEXT_H
#define AGILESTAR_AGFACE_LEGACY_VISION_CONTEXT_H

#include <memory>
#include <string>
#include <vector>

#include <ncnn/net.h>
#include <opencv2/core.hpp>

#include "agface/face_detector.h"

namespace agface {

struct LegacyLiveModelConfig {
    float scale = 1.0f;
    float shift_x = 0.0f;
    float shift_y = 0.0f;
    int height = 80;
    int width = 80;
    std::string name;
};

struct LegacyAttrObject {
    cv::Rect_<float> rect;
    int label = -1;
    float prob = 0.0f;
};

struct LegacyMeshPose {
    bool valid = false;
    float pitch = 0.0f;
    float yaw = 0.0f;
    float roll = 0.0f;
    float eye_closed = 0.0f;
};

class LegacyVisionContext {
public:
    bool initFakePhotoModels(const std::string& model_dir, int num_threads);
    bool initBareheadModels(const std::string& model_dir, int num_threads);
    bool initFacePropertyModels(const std::string& model_dir, int num_threads);

    const FaceDetector& detector() const { return m_detector; }
    FaceDetector& detector() { return m_detector; }

    float detectLegacyLiveConfidence(const cv::Mat& image, const cv::Rect& face_rect) const;
    cv::Rect calculateLegacyLiveBox(const cv::Rect& face_rect,
                                    int image_w,
                                    int image_h,
                                    const LegacyLiveModelConfig& config) const;
    std::vector<LegacyAttrObject> detectLegacyFaceAttributes(const cv::Mat& image) const;
    LegacyMeshPose detectLegacyMeshPose(const cv::Mat& image, const cv::Rect& face_rect) const;
    float detectBareheadConfidence(const cv::Mat& image, const cv::Rect& face_rect) const;

private:
    bool fileExists(const std::string& path) const;
    bool loadNet(const std::string& param_path,
                 const std::string& bin_path,
                 int num_threads,
                 std::shared_ptr<ncnn::Net>* net_out) const;

    FaceDetector m_detector;
    std::string m_model_dir;
    std::vector<LegacyLiveModelConfig> m_live_configs;
    std::vector<std::shared_ptr<ncnn::Net>> m_live_nets;
    std::shared_ptr<ncnn::Net> m_attr_net;
    std::shared_ptr<ncnn::Net> m_mesh_net;
    std::shared_ptr<ncnn::Net> m_hat_net;
};

}  // namespace agface

#endif  // AGILESTAR_AGFACE_LEGACY_VISION_CONTEXT_H
