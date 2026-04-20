#include "agface/face_detector.h"

#include <algorithm>
#include <cmath>
#include <cstdio>

#include <opencv2/imgproc.hpp>

namespace agface {

static const float kSsdMeanVals[3]     = {104.f, 117.f, 123.f};
static const float kOnetMeanVals[3]    = {127.5f, 127.5f, 127.5f};
static const float kOnetNormVals[3]    = {0.0078125f, 0.0078125f, 0.0078125f};  // 1/128

static cv::Mat resizeIfNeeded(const cv::Mat& image, int max_dim) {
    const int longest = std::max(image.cols, image.rows);
    if (longest <= max_dim) return image;
    const float scale = static_cast<float>(max_dim) / longest;
    cv::Mat out;
    cv::resize(image, out,
               cv::Size(static_cast<int>(image.cols * scale),
                        static_cast<int>(image.rows * scale)));
    return out;
}

// type=-1 → CCW 90, type=1 → CW 90, type=0 → 180
static void rotateImage(const cv::Mat& src, cv::Mat& dst, int type) {
    if (type == -1) {
        cv::transpose(src, dst);
        cv::flip(dst, dst, 0);
    } else if (type == 1) {
        cv::transpose(src, dst);
        cv::flip(dst, dst, 1);
    } else {
        cv::flip(src, dst, -1);
    }
}

bool FaceDetector::init(const std::string& model_dir, int num_threads, bool rotation_fallback) {
    m_model_dir         = model_dir;
    m_rotation_fallback = rotation_fallback;

    const std::string det_param  = model_dir + "/detection/detection.param";
    const std::string det_bin    = model_dir + "/detection/detection.bin";
    const std::string onet_param = model_dir + "/detection/det3.param";
    const std::string onet_bin   = model_dir + "/detection/det3.bin";

    m_det_net.opt.lightmode          = true;
    m_det_net.opt.num_threads        = std::max(1, num_threads);
    m_det_net.opt.use_vulkan_compute = false;

    if (m_det_net.load_param(det_param.c_str()) != 0) {
        std::fprintf(stderr, "[agface::FaceDetector] load_param failed: %s\n", det_param.c_str());
        return false;
    }
    if (m_det_net.load_model(det_bin.c_str()) != 0) {
        std::fprintf(stderr, "[agface::FaceDetector] load_model failed: %s\n", det_bin.c_str());
        return false;
    }

    m_onet.opt.lightmode   = true;
    m_onet.opt.num_threads = 1;

    if (m_onet.load_param(onet_param.c_str()) != 0) {
        std::fprintf(stderr, "[agface::FaceDetector] ONet load_param failed: %s\n", onet_param.c_str());
        return false;
    }
    if (m_onet.load_model(onet_bin.c_str()) != 0) {
        std::fprintf(stderr, "[agface::FaceDetector] ONet load_model failed: %s\n", onet_bin.c_str());
        return false;
    }

    m_initialized = true;
    return true;
}

int FaceDetector::detectSSD(const cv::Mat& img, cv::Rect* out_rect) {
    const int   w       = img.cols;
    const int   h       = img.rows;
    const float aspect  = static_cast<float>(w) / static_cast<float>(h);
    const int   input_w = static_cast<int>(m_input_size * std::sqrt(aspect));
    const int   input_h = static_cast<int>(m_input_size / std::sqrt(aspect));

    ncnn::Mat in = ncnn::Mat::from_pixels_resize(
        img.data, ncnn::Mat::PIXEL_BGR, w, h, input_w, input_h);
    in.substract_mean_normalize(kSsdMeanVals, nullptr);

    ncnn::Extractor ex = m_det_net.create_extractor();
    ex.input("data", in);

    ncnn::Mat out;
    if (ex.extract("detection_out", out) != 0) return 0;

    int   count    = 0;
    int   maxArea  = 0;
    for (int i = 0; i < out.h; ++i) {
        const float* v = out.row(i);
        const float conf = v[1];
        if (conf < m_threshold) continue;

        float x1 = v[2] * w;
        float y1 = v[3] * h;
        const float x2 = v[4] * w;
        const float y2 = v[5] * h;
        const float box_w = x2 - x1 + 1.0f;
        const float box_h = y2 - y1 + 1.0f;
        const float size  = (box_w + box_h) * 0.5f;
        if (size < static_cast<float>(m_min_face_size)) continue;

        const float cx = x1 + box_w * 0.5f;
        const float cy = y1 + box_h * 0.5f;
        x1 = cx - size * 0.5f;
        y1 = cy - size * 0.5f;

        const int span = static_cast<int>(y2 - y1);
        int posx = static_cast<int>(x1);
        int posy = static_cast<int>(y1 + span * 0.10f);
        int fw   = static_cast<int>(x2 - x1);
        int fh   = fw;

        if (posx < 0) posx = 0;
        if (posy < 0) posy = 0;
        if (posx + fw > w) fw = w - posx;
        if (posy + fh > h) fh = h - posy;

        const int area = fw * fh;
        if (area > maxArea) {
            maxArea = area;
            if (out_rect) *out_rect = cv::Rect(posx, posy, fw, fh);
        }
        ++count;
    }
    return count;
}

void FaceDetector::extractLandmarks(const cv::Mat& img, const cv::Rect& face, float* marks) {
    const cv::Rect safe = face & cv::Rect(0, 0, img.cols, img.rows);
    if (safe.width <= 0 || safe.height <= 0) return;

    const cv::Mat face_crop = img(safe).clone();
    ncnn::Mat tempIm = ncnn::Mat::from_pixels(
        face_crop.data, ncnn::Mat::PIXEL_BGR, face_crop.cols, face_crop.rows);

    ncnn::Mat in;
    ncnn::resize_bilinear(tempIm, in, 48, 48);
    in.substract_mean_normalize(kOnetMeanVals, kOnetNormVals);

    ncnn::Extractor ex = m_onet.create_extractor();
    ex.input("data", in);

    ncnn::Mat keypoint;
    if (ex.extract("conv6-3", keypoint) != 0) return;

    for (int k = 0; k < 5; ++k) {
        marks[k]     = (safe.x + safe.width  * keypoint[k])     / static_cast<float>(img.cols);
        marks[k + 5] = (safe.y + safe.height * keypoint[k + 5]) / static_cast<float>(img.rows);
    }
}

FaceDetectResult FaceDetector::detectLargestFace(const cv::Mat& image) {
    FaceDetectResult result;
    if (!m_initialized || image.empty()) return result;

    std::lock_guard<std::mutex> lk(m_mutex);

    cv::Mat processed = resizeIfNeeded(image, m_max_image_dim);
    cv::Rect face;
    int count = detectSSD(processed, &face);

    if (count <= 0 && m_rotation_fallback) {
        cv::Mat rot;
        // CCW 90
        rotateImage(processed, rot, -1);
        count = detectSSD(rot, &face);
        if (count > 0) {
            processed = rot;
        } else {
            // CW 90
            rotateImage(processed, rot, 1);
            count = detectSSD(rot, &face);
            if (count > 0) {
                processed = rot;
            } else {
                // 180
                rotateImage(processed, rot, 0);
                count = detectSSD(rot, &face);
                if (count > 0) processed = rot;
            }
        }
    }

    if (count <= 0) return result;

    extractLandmarks(processed, face, result.landmarks);
    result.found     = true;
    result.face_rect = face;
    return result;
}

}  // namespace agface
