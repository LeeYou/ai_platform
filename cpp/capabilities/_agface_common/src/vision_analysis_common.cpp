#include "agface/vision_analysis_common.h"

#include <algorithm>
#include <cmath>
#include <cstdio>

#include <opencv2/imgproc.hpp>

namespace agface {
namespace {

#if defined(CV_VERSION_EPOCH) && (CV_VERSION_EPOCH == 2)
static constexpr int kColorBgr2Hsv = CV_BGR2HSV;
static constexpr int kColorBgr2Gray = CV_BGR2GRAY;
#else
static constexpr int kColorBgr2Hsv = cv::COLOR_BGR2HSV;
static constexpr int kColorBgr2Gray = cv::COLOR_BGR2GRAY;
#endif

float rectStdDevGray(const cv::Mat& gray, const cv::Rect& roi) {
    cv::Rect safe = roi & cv::Rect(0, 0, gray.cols, gray.rows);
    if (safe.width <= 1 || safe.height <= 1) return 0.0f;
    cv::Scalar mean;
    cv::Scalar stddev;
    cv::meanStdDev(gray(safe), mean, stddev);
    return static_cast<float>(stddev[0]);
}

float laplacianVariance(const cv::Mat& gray, const cv::Rect& roi) {
    cv::Rect safe = roi & cv::Rect(0, 0, gray.cols, gray.rows);
    if (safe.width <= 2 || safe.height <= 2) return 0.0f;
    cv::Mat lap;
    cv::Laplacian(gray(safe), lap, CV_32F);
    cv::Scalar mean;
    cv::Scalar stddev;
    cv::meanStdDev(lap, mean, stddev);
    return static_cast<float>(stddev[0] * stddev[0]);
}

float edgeDensity(const cv::Mat& gray, const cv::Rect& roi) {
    cv::Rect safe = roi & cv::Rect(0, 0, gray.cols, gray.rows);
    if (safe.width <= 2 || safe.height <= 2) return 0.0f;
    cv::Mat edges;
    cv::Canny(gray(safe), edges, 60, 120);
    return static_cast<float>(cv::countNonZero(edges)) /
           static_cast<float>(std::max(1, safe.area()));
}

float meanSaturation(const cv::Mat& bgr, const cv::Rect& roi) {
    cv::Rect safe = roi & cv::Rect(0, 0, bgr.cols, bgr.rows);
    if (safe.width <= 1 || safe.height <= 1) return 0.0f;
    cv::Mat hsv;
    cv::cvtColor(bgr(safe), hsv, kColorBgr2Hsv);
    cv::Scalar mean = cv::mean(hsv);
    return static_cast<float>(mean[1]) / 255.0f;
}

float meanValue(const cv::Mat& bgr, const cv::Rect& roi) {
    cv::Rect safe = roi & cv::Rect(0, 0, bgr.cols, bgr.rows);
    if (safe.width <= 1 || safe.height <= 1) return 0.0f;
    cv::Mat hsv;
    cv::cvtColor(bgr(safe), hsv, kColorBgr2Hsv);
    cv::Scalar mean = cv::mean(hsv);
    return static_cast<float>(mean[2]) / 255.0f;
}

cv::Rect safeRect(const cv::Rect& roi, const cv::Mat& image) {
    return roi & cv::Rect(0, 0, image.cols, image.rows);
}

cv::Rect buildLegacyHeadRect(const cv::Rect& face_rect, const cv::Mat& image) {
    cv::Rect roi = face_rect;
    roi.x -= static_cast<int>(face_rect.width * 0.3f);
    roi.width = static_cast<int>(face_rect.width * 1.6f);
    roi.y -= static_cast<int>(face_rect.height * 0.6f);
    roi.height = static_cast<int>(face_rect.height * 1.85f);
    return safeRect(roi, image);
}

cv::Rect buildLegacyEyeBand(const cv::Rect& face_rect, const cv::Mat& image) {
    cv::Rect roi(face_rect.x + face_rect.width / 8,
                 face_rect.y + face_rect.height / 8,
                 face_rect.width * 3 / 4,
                 std::max(1, face_rect.height / 4));
    return safeRect(roi, image);
}

cv::Rect buildLegacyLowerFace(const cv::Rect& face_rect, const cv::Mat& image) {
    cv::Rect roi(face_rect.x + face_rect.width / 8,
                 face_rect.y + face_rect.height / 2,
                 face_rect.width * 3 / 4,
                 std::max(1, face_rect.height / 3));
    return safeRect(roi, image);
}

}  // namespace

float clamp01(float v) {
    if (v < 0.0f) return 0.0f;
    if (v > 1.0f) return 1.0f;
    return v;
}

cv::Mat preprocessLegacyVisionImage(const cv::Mat& image) {
    if (image.empty()) return image;
    if (image.cols <= 1280) return image.clone();
    cv::Mat resized;
    const int new_h = std::max(1, image.rows * 1280 / image.cols);
    cv::resize(image, resized, cv::Size(1280, new_h));
    return resized;
}

float estimateFakeConfidenceLegacy(const cv::Mat& image, const cv::Rect& face_rect) {
    return clamp01(1.0f - estimateRealConfidenceLegacy(image, face_rect));
}

float estimateRealConfidenceLegacy(const cv::Mat& image, const cv::Rect& face_rect) {
    cv::Mat gray;
    cv::cvtColor(image, gray, kColorBgr2Gray);
    const cv::Rect face = safeRect(face_rect, image);
    const float blur = laplacianVariance(gray, face);
    const float sat = meanSaturation(image, face);
    const float edge = edgeDensity(gray, face);
    const float brightness = meanValue(image, face);

    const float blur_good = clamp01(std::min(120.0f, blur) / 120.0f);
    const float sat_good = clamp01(std::min(0.35f, sat) / 0.35f);
    const float edge_good = clamp01(std::min(0.18f, edge) / 0.18f);
    const float brightness_good = 1.0f - clamp01(std::max(0.0f, brightness - 0.78f) / 0.22f);
    return clamp01(blur_good * 0.35f + sat_good * 0.15f + edge_good * 0.20f + brightness_good * 0.30f);
}

std::string buildAngleStringLegacy(const FaceDetectResult& det, const cv::Mat& image) {
    const float lx = det.landmarks[0] * image.cols;
    const float rx = det.landmarks[1] * image.cols;
    const float nx = det.landmarks[2] * image.cols;
    const float ly = det.landmarks[5] * image.rows;
    const float ry = det.landmarks[6] * image.rows;
    const float ny = det.landmarks[7] * image.rows;
    const float lmy = det.landmarks[8] * image.rows;
    const float rmy = det.landmarks[9] * image.rows;

    const float eye_mid_x = (lx + rx) * 0.5f;
    const float eye_mid_y = (ly + ry) * 0.5f;
    const float mouth_mid_y = (lmy + rmy) * 0.5f;
    const float mouth_mid_x = (det.landmarks[3] * image.cols + det.landmarks[4] * image.cols) * 0.5f;
    const float face_w = static_cast<float>(std::max(1, det.face_rect.width));
    const float face_h = static_cast<float>(std::max(1, det.face_rect.height));

    const float out_rx = std::max(-0.9f, std::min(0.9f,
        (((mouth_mid_y - eye_mid_y) / face_h) - 0.42f) * 1.45f + (((ny - eye_mid_y) / face_h) - 0.18f) * 0.95f));
    const float out_ry = std::max(-0.9f, std::min(0.9f,
        (((nx - eye_mid_x) / std::max(1.0f, face_w * 0.5f)) * 1.35f) + (((mouth_mid_x - eye_mid_x) / std::max(1.0f, face_w * 0.5f)) * 0.35f)));
    const float out_rz = std::max(-0.9f, std::min(0.9f,
        std::atan2(ry - ly, rx - lx) / 0.78f));

    const float pitch = out_rx * 50.0f;
    const float yaw = out_ry * 50.0f;
    const float roll = out_rz * 50.0f;

    char buf[96];
    std::snprintf(buf, sizeof(buf), "[%.2f,%.2f,%.2f]", pitch, yaw, roll);
    return std::string(buf);
}

float estimateGlassesLegacy(const cv::Mat& image, const cv::Rect& face_rect) {
    cv::Mat gray;
    cv::cvtColor(image, gray, kColorBgr2Gray);
    const cv::Rect eye_band = buildLegacyEyeBand(face_rect, image);
    const float overlap_edges = edgeDensity(gray, eye_band);
    const float texture = rectStdDevGray(gray, eye_band);
    const float confidence = overlap_edges * 1.8f + std::max(0.0f, texture - 20.0f) / 40.0f;
    return clamp01(confidence);
}

float estimateMaskLegacy(const cv::Mat& image, const cv::Rect& face_rect) {
    cv::Mat gray;
    cv::cvtColor(image, gray, kColorBgr2Gray);
    const cv::Rect lower = buildLegacyLowerFace(face_rect, image);
    const float texture = rectStdDevGray(gray, lower);
    const float sat = meanSaturation(image, lower);
    const float flat_region = clamp01((28.0f - std::min(28.0f, texture)) / 28.0f);
    const float low_sat = clamp01((0.22f - std::min(0.22f, sat)) / 0.22f);
    return clamp01(flat_region * 0.60f + low_sat * 0.40f);
}

float estimateEyeClosedLegacy(const cv::Mat& image, const cv::Rect& face_rect) {
    cv::Mat gray;
    cv::cvtColor(image, gray, kColorBgr2Gray);
    const cv::Rect eye_band = buildLegacyEyeBand(face_rect, image);
    const float edge = edgeDensity(gray, eye_band);
    const float blur = laplacianVariance(gray, eye_band);
    return clamp01(std::max(0.0f, (0.11f - edge) / 0.11f) * 0.50f + std::max(0.0f, (20.0f - blur) / 20.0f) * 0.50f);
}

float estimateHatLegacy(const cv::Mat& image, const cv::Rect& face_rect) {
    const cv::Rect head = buildLegacyHeadRect(face_rect, image);
    if (head.width <= 1 || head.height <= 1) return 0.0f;
    const cv::Rect top_half(head.x, head.y, head.width,
                            std::max(1, static_cast<int>(head.height * 0.45f)));
    const float darkness = 1.0f - meanValue(image, top_half);
    const float sat = meanSaturation(image, top_half);
    const float confidence = darkness * 0.55f + std::max(0.0f, sat - 0.18f) * 0.45f;
    return clamp01(confidence);
}

}  // namespace agface
