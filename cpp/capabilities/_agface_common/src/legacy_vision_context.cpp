#include "agface/legacy_vision_context.h"

#include <algorithm>
#include <cfloat>
#include <cmath>
#include <cstdio>
#include <cstring>

#include <opencv2/imgproc.hpp>

#include "agface/vision_analysis_common.h"

namespace agface {
namespace {

float intersectionArea(const cv::Rect_<float>& a, const cv::Rect_<float>& b) {
    const float x1 = std::max(a.x, b.x);
    const float y1 = std::max(a.y, b.y);
    const float x2 = std::min(a.x + a.width, b.x + b.width);
    const float y2 = std::min(a.y + a.height, b.y + b.height);
    const float w = x2 - x1;
    const float h = y2 - y1;
    return (w > 0.0f && h > 0.0f) ? (w * h) : 0.0f;
}

float iouRect(const cv::Rect_<float>& a, const cv::Rect_<float>& b) {
    const float inter = intersectionArea(a, b);
    const float uni = a.width * a.height + b.width * b.height - inter;
    return uni > 0.0f ? (inter / uni) : 0.0f;
}

struct YoloProposal {
    cv::Rect_<float> rect;
    int label = -1;
    float prob = 0.0f;
};

void generateLegacyYoloProposals(const ncnn::Mat& anchors,
                                 int stride,
                                 const ncnn::Mat& in_pad,
                                 const ncnn::Mat& feat_blob,
                                 float prob_threshold,
                                 std::vector<YoloProposal>& objects) {
    const int num_grid = feat_blob.h;
    int num_grid_x;
    int num_grid_y;
    if (in_pad.w > in_pad.h) {
        num_grid_x = in_pad.w / stride;
        num_grid_y = num_grid / num_grid_x;
    } else {
        num_grid_y = in_pad.h / stride;
        num_grid_x = num_grid / num_grid_y;
    }
    const int num_class = feat_blob.w - 5 - 3 * 4;
    const int num_anchors = anchors.w / 2;
    auto sigmoid = [](float x) -> float { return 1.0f / (1.0f + std::exp(-x)); };

    for (int q = 0; q < num_anchors; q++) {
        const float anchor_w = anchors[q * 2];
        const float anchor_h = anchors[q * 2 + 1];
        const ncnn::Mat feat = feat_blob.channel(q);
        for (int i = 0; i < num_grid_y; i++) {
            for (int j = 0; j < num_grid_x; j++) {
                const float* featptr = feat.row(i * num_grid_x + j);
                float box_confidence = sigmoid(featptr[4]);
                if (box_confidence < prob_threshold) continue;
                int class_index = 0;
                float class_score = -FLT_MAX;
                for (int k = 0; k < num_class; k++) {
                    float score = featptr[5 + k];
                    if (score > class_score) {
                        class_index = k;
                        class_score = score;
                    }
                }
                float confidence = box_confidence * sigmoid(class_score);
                if (confidence < prob_threshold) continue;

                float dx = sigmoid(featptr[0]);
                float dy = sigmoid(featptr[1]);
                float dw = sigmoid(featptr[2]);
                float dh = sigmoid(featptr[3]);
                float pb_cx = (dx * 2.f - 0.5f + j) * stride;
                float pb_cy = (dy * 2.f - 0.5f + i) * stride;
                float pb_w = static_cast<float>(std::pow(dw * 2.f, 2.0)) * anchor_w;
                float pb_h = static_cast<float>(std::pow(dh * 2.f, 2.0)) * anchor_h;
                YoloProposal obj;
                obj.rect.x = pb_cx - pb_w * 0.5f;
                obj.rect.y = pb_cy - pb_h * 0.5f;
                obj.rect.width = pb_w;
                obj.rect.height = pb_h;
                obj.label = class_index;
                obj.prob = confidence;
                objects.push_back(obj);
            }
        }
    }
}

struct Float3 {
    float x;
    float y;
    float z;
};

struct Rigid3D {
    float r[9];
};

cv::Vec3f rotationMatrixToEulerAnglesSimple(const float* r) {
    const float sy = std::sqrt(r[0] * r[0] + r[3] * r[3]);
    const bool singular = sy < 1e-6f;
    float x;
    float y;
    float z;
    if (!singular) {
        x = std::atan2(r[7], r[8]);
        y = std::atan2(-r[6], sy);
        z = std::atan2(r[3], r[0]);
    } else {
        x = std::atan2(-r[5], r[4]);
        y = std::atan2(-r[6], sy);
        z = 0.0f;
    }
    return cv::Vec3f(x, y, z);
}

bool computeRigidRotation5(const Float3 src[5], const Float3 dst[5], Rigid3D& rigid) {
    cv::Mat src_mat(3, 5, CV_32FC1);
    cv::Mat dst_mat(3, 5, CV_32FC1);
    Float3 src_center{0.0f, 0.0f, 0.0f};
    Float3 dst_center{0.0f, 0.0f, 0.0f};
    for (int i = 0; i < 5; ++i) {
        src_center.x += src[i].x;
        src_center.y += src[i].y;
        src_center.z += src[i].z;
        dst_center.x += dst[i].x;
        dst_center.y += dst[i].y;
        dst_center.z += dst[i].z;
    }
    src_center.x /= 5.0f;
    src_center.y /= 5.0f;
    src_center.z /= 5.0f;
    dst_center.x /= 5.0f;
    dst_center.y /= 5.0f;
    dst_center.z /= 5.0f;

    float* src_data = reinterpret_cast<float*>(src_mat.data);
    float* dst_data = reinterpret_cast<float*>(dst_mat.data);
    for (int i = 0; i < 5; ++i) {
        src_data[i] = src[i].x - src_center.x;
        src_data[5 + i] = src[i].y - src_center.y;
        src_data[10 + i] = src[i].z - src_center.z;
        dst_data[i] = dst[i].x - dst_center.x;
        dst_data[5 + i] = dst[i].y - dst_center.y;
        dst_data[10 + i] = dst[i].z - dst_center.z;
    }

    cv::Mat s = src_mat * dst_mat.t();
    cv::Mat u;
    cv::Mat w;
    cv::Mat vt;
    cv::SVD::compute(s, w, u, vt);
    cv::Mat temp = u * vt;
    float det = static_cast<float>(cv::determinant(temp));
    float dat_m[] = {1, 0, 0, 0, 1, 0, 0, 0, det};
    cv::Mat m(3, 3, CV_32FC1, dat_m);
    cv::Mat r = vt.t() * m * u.t();
    std::memcpy(rigid.r, r.data, sizeof(float) * 9);
    return true;
}

float computeHatConfidenceFromDetections(const cv::Rect& face_rect,
                                         const ncnn::Mat& out,
                                         int img_w,
                                         int img_h) {
    float best_prob = 0.0f;
    const int head_top = face_rect.y;
    const int head_bottom = face_rect.y + static_cast<int>(face_rect.height * 0.35f);
    const int head_left = face_rect.x;
    const int head_right = face_rect.x + face_rect.width;
    for (int i = 0; i < out.h; ++i) {
        const float* vals = out.row(i);
        const float prob = vals[1];
        const int x1 = static_cast<int>(vals[2] * img_w);
        const int y1 = static_cast<int>(vals[3] * img_h);
        const int x2 = static_cast<int>(vals[4] * img_w);
        const int y2 = static_cast<int>(vals[5] * img_h);
        const int cx = (x1 + x2) / 2;
        const int cy = (y1 + y2) / 2;
        if (cx >= head_left && cx <= head_right && cy >= head_top && cy <= head_bottom) {
            best_prob = std::max(best_prob, prob);
        }
    }
    return best_prob;
}

}  // namespace

bool LegacyVisionContext::fileExists(const std::string& path) const {
    FILE* fp = nullptr;
#ifdef _WIN32
    fopen_s(&fp, path.c_str(), "rb");
#else
    fp = std::fopen(path.c_str(), "rb");
#endif
    if (!fp) return false;
    std::fclose(fp);
    return true;
}

bool LegacyVisionContext::loadNet(const std::string& param_path,
                                  const std::string& bin_path,
                                  int num_threads,
                                  std::shared_ptr<ncnn::Net>* net_out) const {
    if (!net_out) return false;
    auto net = std::make_shared<ncnn::Net>();
    net->opt.lightmode = true;
    net->opt.num_threads = std::max(1, num_threads);
    net->opt.use_vulkan_compute = false;
    if (net->load_param(param_path.c_str()) != 0) return false;
    if (net->load_model(bin_path.c_str()) != 0) return false;
    *net_out = std::move(net);
    return true;
}

bool LegacyVisionContext::initFakePhotoModels(const std::string& model_dir, int num_threads) {
    m_model_dir = model_dir;
    const bool live_models_ready =
        fileExists(m_model_dir + "/detection/model_1.param") &&
        fileExists(m_model_dir + "/detection/model_1.bin") &&
        fileExists(m_model_dir + "/detection/model_2.param") &&
        fileExists(m_model_dir + "/detection/model_2.bin") &&
        fileExists(m_model_dir + "/detection/model_3.param") &&
        fileExists(m_model_dir + "/detection/model_3.bin");
    const bool attr_models_ready =
        fileExists(m_model_dir + "/detection/yolov7s320face.param") &&
        fileExists(m_model_dir + "/detection/yolov7s320face.bin");
    if (!live_models_ready || !attr_models_ready) {
        return false;
    }

    m_live_configs.clear();
    m_live_nets.clear();
    m_live_configs.push_back({2.7f, 0.0f, 0.0f, 80, 80, "model_1"});
    m_live_configs.push_back({4.0f, 0.0f, 0.0f, 80, 80, "model_2"});
    m_live_configs.push_back({2.0f, 0.0f, 0.0f, 80, 80, "model_3"});

    for (const auto& cfg : m_live_configs) {
        std::shared_ptr<ncnn::Net> net;
        if (!loadNet(m_model_dir + "/detection/" + cfg.name + ".param",
                     m_model_dir + "/detection/" + cfg.name + ".bin",
                     num_threads,
                     &net)) {
            return false;
        }
        m_live_nets.push_back(std::move(net));
    }

    if (!loadNet(m_model_dir + "/detection/yolov7s320face.param",
                 m_model_dir + "/detection/yolov7s320face.bin",
                 num_threads,
                 &m_attr_net)) {
        return false;
    }

    m_mesh_net.reset();
    m_hat_net.reset();
    return m_detector.init(m_model_dir, num_threads);
}

bool LegacyVisionContext::initBareheadModels(const std::string& model_dir, int num_threads) {
    m_model_dir = model_dir;
    if (!loadNet(m_model_dir + "/detection/modelht.param",
                 m_model_dir + "/detection/modelht.bin",
                 num_threads,
                 &m_hat_net)) {
        return false;
    }
    m_attr_net.reset();
    m_mesh_net.reset();
    m_live_configs.clear();
    m_live_nets.clear();
    return m_detector.init(m_model_dir, num_threads);
}

bool LegacyVisionContext::initFacePropertyModels(const std::string& model_dir, int num_threads) {
    if (!initFakePhotoModels(model_dir, num_threads)) {
        return false;
    }
    if (!loadNet(m_model_dir + "/detection/modelht.param",
                 m_model_dir + "/detection/modelht.bin",
                 num_threads,
                 &m_hat_net)) {
        return false;
    }
    if (!loadNet(m_model_dir + "/detection/face_landmark_with_attention.param",
                 m_model_dir + "/detection/face_landmark_with_attention.bin",
                 1,
                 &m_mesh_net)) {
        return false;
    }
    return true;
}

cv::Rect LegacyVisionContext::calculateLegacyLiveBox(const cv::Rect& face_rect,
                                                     int image_w,
                                                     int image_h,
                                                     const LegacyLiveModelConfig& config) const {
    int box_width = face_rect.width;
    int box_height = face_rect.height;
    int shift_x = static_cast<int>(box_width * config.shift_x);
    int shift_y = static_cast<int>(box_height * config.shift_y);
    float scale = std::min(config.scale,
                           std::min((image_w - 1) / static_cast<float>(std::max(1, box_width)),
                                    (image_h - 1) / static_cast<float>(std::max(1, box_height))));
    int box_center_x = box_width / 2 + face_rect.x;
    int box_center_y = box_height / 2 + face_rect.y;
    int new_width = static_cast<int>(box_width * scale);
    int new_height = static_cast<int>(box_height * scale);
    int left_top_x = box_center_x - new_width / 2 + shift_x;
    int left_top_y = box_center_y - new_height / 2 + shift_y;
    int right_bottom_x = box_center_x + new_width / 2 + shift_x;
    int right_bottom_y = box_center_y + new_height / 2 + shift_y;

    if (left_top_x < 0) {
        right_bottom_x -= left_top_x;
        left_top_x = 0;
    }
    if (left_top_y < 0) {
        right_bottom_y -= left_top_y;
        left_top_y = 0;
    }
    if (right_bottom_x >= image_w) {
        int s = right_bottom_x - image_w + 1;
        left_top_x -= s;
        right_bottom_x -= s;
    }
    if (right_bottom_y >= image_h) {
        int s = right_bottom_y - image_h + 1;
        left_top_y -= s;
        right_bottom_y -= s;
    }

    left_top_x = std::max(0, left_top_x);
    left_top_y = std::max(0, left_top_y);
    right_bottom_x = std::min(image_w - 1, right_bottom_x);
    right_bottom_y = std::min(image_h - 1, right_bottom_y);
    return cv::Rect(left_top_x,
                    left_top_y,
                    std::max(1, right_bottom_x - left_top_x),
                    std::max(1, right_bottom_y - left_top_y));
}

float LegacyVisionContext::detectLegacyLiveConfidence(const cv::Mat& image, const cv::Rect& face_rect) const {
    if (m_live_nets.size() != m_live_configs.size() || m_live_nets.empty()) {
        return estimateRealConfidenceLegacy(image, face_rect);
    }

    float confidence = 0.0f;
    static const float weights[3] = {0.25f, 0.25f, 0.50f};
    for (size_t i = 0; i < m_live_configs.size(); ++i) {
        const LegacyLiveModelConfig& cfg = m_live_configs[i];
        cv::Rect roi = calculateLegacyLiveBox(face_rect, image.cols, image.rows, cfg);
        if (roi.width <= 1 || roi.height <= 1) continue;

        cv::Mat crop;
        cv::resize(image(roi), crop, cv::Size(cfg.width, cfg.height));
        ncnn::Mat in = ncnn::Mat::from_pixels(crop.data, ncnn::Mat::PIXEL_BGR, crop.cols, crop.rows);
        ncnn::Extractor ex = m_live_nets[i]->create_extractor();
        ex.set_light_mode(true);
        ex.input("data", in);
        ncnn::Mat out;
        if (ex.extract("softmax", out) != 0 || out.w < 2) {
            return estimateRealConfidenceLegacy(image, face_rect);
        }
        confidence += out.row(0)[1] * weights[i];
    }

    const float area_ratio = (face_rect.width * face_rect.height) /
                             static_cast<float>(std::max(1, image.cols * image.rows));
    if (area_ratio < 0.0140f) {
        confidence *= 0.73f;
    }
    return clamp01(confidence);
}

std::vector<LegacyAttrObject> LegacyVisionContext::detectLegacyFaceAttributes(const cv::Mat& image) const {
    std::vector<LegacyAttrObject> result;
    if (!m_attr_net) return result;

    const int img_w = image.cols;
    const int img_h = image.rows;
    int w = img_w;
    int h = img_h;
    float scale = 1.0f;
    const int target_size = 320;
    if (w > h) {
        scale = static_cast<float>(target_size) / w;
        w = target_size;
        h = static_cast<int>(h * scale);
    } else {
        scale = static_cast<float>(target_size) / h;
        h = target_size;
        w = static_cast<int>(w * scale);
    }

    ncnn::Mat in = ncnn::Mat::from_pixels_resize(image.data, ncnn::Mat::PIXEL_BGR2RGB, img_w, img_h, w, h);
    int wpad = target_size - w;
    int hpad = target_size - h;
    ncnn::Mat in_pad;
    ncnn::copy_make_border(in, in_pad, hpad / 2, hpad - hpad / 2,
                           wpad / 2, wpad - wpad / 2,
                           ncnn::BORDER_CONSTANT, 255.f);
    static const float norm_vals[3] = {1.f / 255.f, 1.f / 255.f, 1.f / 255.f};
    in_pad.substract_mean_normalize(nullptr, norm_vals);

    ncnn::Extractor ex = m_attr_net->create_extractor();
    ex.set_light_mode(true);
    ex.input("data", in_pad);

    std::vector<YoloProposal> proposals;
    ncnn::Mat out8;
    ncnn::Mat out16;
    ncnn::Mat out32;
    ex.extract("stride_8", out8);
    ex.extract("stride_16", out16);
    ex.extract("stride_32", out32);

    ncnn::Mat anchors8(6);
    anchors8[0] = 4.f; anchors8[1] = 5.f; anchors8[2] = 6.f; anchors8[3] = 8.f; anchors8[4] = 10.f; anchors8[5] = 12.f;
    ncnn::Mat anchors16(6);
    anchors16[0] = 15.f; anchors16[1] = 19.f; anchors16[2] = 23.f; anchors16[3] = 30.f; anchors16[4] = 39.f; anchors16[5] = 52.f;
    ncnn::Mat anchors32(6);
    anchors32[0] = 72.f; anchors32[1] = 97.f; anchors32[2] = 123.f; anchors32[3] = 164.f; anchors32[4] = 209.f; anchors32[5] = 297.f;
    if (!out8.empty()) generateLegacyYoloProposals(anchors8, 8, in_pad, out8, 0.42f, proposals);
    if (!out16.empty()) generateLegacyYoloProposals(anchors16, 16, in_pad, out16, 0.42f, proposals);
    if (!out32.empty()) generateLegacyYoloProposals(anchors32, 32, in_pad, out32, 0.42f, proposals);

    std::sort(proposals.begin(), proposals.end(), [](const YoloProposal& a, const YoloProposal& b) {
        return a.prob > b.prob;
    });
    for (size_t i = 0; i < proposals.size(); ++i) {
        bool keep = true;
        for (size_t j = 0; j < result.size(); ++j) {
            if (iouRect(proposals[i].rect, result[j].rect) > 0.45f) {
                keep = false;
                break;
            }
        }
        if (!keep) continue;
        LegacyAttrObject obj;
        float x0 = (proposals[i].rect.x - (wpad / 2)) / scale;
        float y0 = (proposals[i].rect.y - (hpad / 2)) / scale;
        float x1 = (proposals[i].rect.x + proposals[i].rect.width - (wpad / 2)) / scale;
        float y1 = (proposals[i].rect.y + proposals[i].rect.height - (hpad / 2)) / scale;
        x0 = std::max(0.0f, std::min(x0, static_cast<float>(img_w - 1)));
        y0 = std::max(0.0f, std::min(y0, static_cast<float>(img_h - 1)));
        x1 = std::max(0.0f, std::min(x1, static_cast<float>(img_w - 1)));
        y1 = std::max(0.0f, std::min(y1, static_cast<float>(img_h - 1)));
        obj.rect = cv::Rect_<float>(x0, y0, std::max(1.0f, x1 - x0), std::max(1.0f, y1 - y0));
        obj.label = proposals[i].label;
        obj.prob = proposals[i].prob;
        result.push_back(obj);
    }
    return result;
}

LegacyMeshPose LegacyVisionContext::detectLegacyMeshPose(const cv::Mat& image, const cv::Rect& face_rect) const {
    LegacyMeshPose pose;
    if (!m_mesh_net) return pose;

    cv::Rect roi = face_rect;
    roi.x -= static_cast<int>(face_rect.width * 0.125f);
    roi.y -= static_cast<int>(face_rect.height * 0.125f);
    roi.width = static_cast<int>(face_rect.width * 1.25f);
    roi.height = static_cast<int>(face_rect.height * 1.25f);
    roi &= cv::Rect(0, 0, image.cols, image.rows);
    if (roi.width <= 1 || roi.height <= 1) return pose;

    cv::Mat out = image(roi).clone();
    if (out.cols != out.rows) {
        const int maxw = std::max(out.cols, out.rows);
        cv::Mat square = cv::Mat::zeros(maxw, maxw, out.type());
        out.copyTo(square(cv::Rect(0, 0, out.cols, out.rows)));
        out = square;
    }
    cv::resize(out, out, cv::Size(192, 192));
    ncnn::Mat in = ncnn::Mat::from_pixels(out.data, ncnn::Mat::PIXEL_BGR2RGB, out.cols, out.rows);
    static const float mean_vals[3] = {127.5f, 127.5f, 127.5f};
    static const float norm_vals[3] = {1 / 127.5f, 1 / 127.5f, 1 / 127.5f};
    in.substract_mean_normalize(mean_vals, norm_vals);

    ncnn::Extractor ex = m_mesh_net->create_extractor();
    ex.input("net/input", in);
    ncnn::Mat face_mesh;
    if (ex.extract("net/output", face_mesh) != 0 || face_mesh.empty()) {
        return pose;
    }

    ncnn::Mat data = face_mesh.channel(0);
    const float* points = reinterpret_cast<const float*>(data.data);
    if (!points) return pose;

    const int idxs[5] = {33, 263, 44, 43, 273};
    const Float3 ref[5] = {
        {104.f, 128.f, 12.f},
        {274.f, 127.f, 10.f},
        {178.f, 193.f, -30.f},
        {131.f, 256.f, -0.25f},
        {247.f, 256.f, -1.5f},
    };
    Float3 src[5];
    for (int i = 0; i < 5; ++i) {
        const int idx = idxs[i];
        src[i].x = points[idx * 3 + 0];
        src[i].y = points[idx * 3 + 1];
        src[i].z = points[idx * 3 + 2];
    }

    Rigid3D rigid;
    if (!computeRigidRotation5(src, ref, rigid)) {
        return pose;
    }
    cv::Vec3f euler = rotationMatrixToEulerAnglesSimple(rigid.r);
    pose.pitch = euler[0] * 50.0f;
    pose.yaw = euler[1] * 50.0f;
    pose.roll = euler[2] * 50.0f;

    const float f_l = (std::fabs(points[33 * 3 + 1] - points[145 * 3 + 1]) + std::fabs(points[33 * 3 + 1] - points[159 * 3 + 1])) * 0.5f;
    const float f_r = (std::fabs(points[263 * 3 + 1] - points[374 * 3 + 1]) + std::fabs(points[263 * 3 + 1] - points[386 * 3 + 1])) * 0.5f;
    const float eye_open = (f_l + f_r) * 0.5f;
    pose.eye_closed = clamp01((8.2f - std::min(8.2f, eye_open)) / 8.2f);
    pose.valid = true;
    return pose;
}

float LegacyVisionContext::detectBareheadConfidence(const cv::Mat& image, const cv::Rect& face_rect) const {
    if (!m_hat_net) return estimateHatLegacy(image, face_rect);

    ncnn::Mat in = ncnn::Mat::from_pixels_resize(image.data, ncnn::Mat::PIXEL_BGR,
                                                 image.cols, image.rows, 320, 320);
    static const float norm_vals[3] = {1.f / 255.f, 1.f / 255.f, 1.f / 255.f};
    in.substract_mean_normalize(nullptr, norm_vals);

    ncnn::Extractor ex = m_hat_net->create_extractor();
    ex.input("images", in);

    ncnn::Mat stride8;
    ncnn::Mat stride16;
    ncnn::Mat stride32;
    const int ret8 = ex.extract("stride_8", stride8);
    const int ret16 = ex.extract("stride_16", stride16);
    const int ret32 = ex.extract("stride_32", stride32);

    float confidence = 0.0f;
    bool has_valid_output = false;
    if (ret8 == 0 && !stride8.empty() && stride8.w >= 6) {
        confidence = std::max(confidence, computeHatConfidenceFromDetections(face_rect, stride8, image.cols, image.rows));
        has_valid_output = true;
    }
    if (ret16 == 0 && !stride16.empty() && stride16.w >= 6) {
        confidence = std::max(confidence, computeHatConfidenceFromDetections(face_rect, stride16, image.cols, image.rows));
        has_valid_output = true;
    }
    if (ret32 == 0 && !stride32.empty() && stride32.w >= 6) {
        confidence = std::max(confidence, computeHatConfidenceFromDetections(face_rect, stride32, image.cols, image.rows));
        has_valid_output = true;
    }

    return has_valid_output ? confidence : estimateHatLegacy(image, face_rect);
}

}  // namespace agface
