#ifndef AGILESTAR_AGFACE_VISION_ANALYSIS_COMMON_H
#define AGILESTAR_AGFACE_VISION_ANALYSIS_COMMON_H

#include <string>

#include <opencv2/core.hpp>

#include "agface/face_detector.h"

namespace agface {

cv::Mat preprocessLegacyVisionImage(const cv::Mat& image);

float estimateFakeConfidenceLegacy(const cv::Mat& image, const cv::Rect& face_rect);
float estimateRealConfidenceLegacy(const cv::Mat& image, const cv::Rect& face_rect);
std::string buildAngleStringLegacy(const FaceDetectResult& det, const cv::Mat& image);
float estimateGlassesLegacy(const cv::Mat& image, const cv::Rect& face_rect);
float estimateMaskLegacy(const cv::Mat& image, const cv::Rect& face_rect);
float estimateEyeClosedLegacy(const cv::Mat& image, const cv::Rect& face_rect);
float estimateHatLegacy(const cv::Mat& image, const cv::Rect& face_rect);

float clamp01(float v);

}  // namespace agface

#endif  // AGILESTAR_AGFACE_VISION_ANALYSIS_COMMON_H
