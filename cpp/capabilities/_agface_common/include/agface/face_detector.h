#ifndef AGILESTAR_AGFACE_FACE_DETECTOR_H
#define AGILESTAR_AGFACE_FACE_DETECTOR_H

/**
 * @file face_detector.h
 * @brief 内部 FaceDetector 助手 —— SSD 人脸检测 + MTCNN ONet 5 点地标 + 旋转兜底。
 *
 * 端到端兼容旧 ai_agface/src/face_detector.{h,cpp}。此类不作为独立 Ai* 能力
 * 导出；它只在 agface_barehead / agface_fake_photo / agface_face_property 等
 * 插件内部用来先取"最大人脸 bbox + 5 点"，再送到各自的判别网络。
 *
 * 为什么不直接复用 agface_face_detect 插件？
 *   - agface_face_detect 是跨进程能力单元，属"HTTP/runtime 层调度单位"。
 *   - 本 helper 是"同进程同 SO 内的函数调用"，省去进程/线程/实例池开销，
 *     同时提供旋转兜底 + ONet landmarks（MVP 的 agface_face_detect 不做）。
 */

#include <memory>
#include <mutex>
#include <string>

#include <ncnn/net.h>
#include <opencv2/core.hpp>

namespace agface {

struct FaceDetectResult {
    bool      found = false;
    cv::Rect  face_rect;            ///< bbox in (possibly resized/rotated) working image coords
    float     landmarks[10] = {};   ///< 5-point normalized to full-image coords [x0..x4,y0..y4]
};

class FaceDetector {
public:
    FaceDetector()  = default;
    ~FaceDetector() { m_det_net.clear(); m_onet.clear(); }

    FaceDetector(const FaceDetector&)            = delete;
    FaceDetector& operator=(const FaceDetector&) = delete;

    /**
     * 加载两个网络：
     *   <model_dir>/detection/detection.param + .bin   (SSD)
     *   <model_dir>/detection/det3.param + .bin        (MTCNN ONet landmarks)
     */
    bool init(const std::string& model_dir,
              int                num_threads    = 2,
              bool               rotation_fallback = true);

    /**
     * 在整张图上找最大人脸 + 5 点地标。
     * 若初次未找到，依 rotation_fallback 尝试 CCW90/CW90/180 三次。
     */
    FaceDetectResult detectLargestFace(const cv::Mat& bgr_image);

    bool isInitialized() const { return m_initialized; }

    // 可调参数（默认与旧 FaceDetector 一致）
    void setThreshold(float v)   { m_threshold    = v; }
    void setMinFaceSize(int v)   { m_min_face_size = v; }
    void setInputSize(int v)     { m_input_size    = v; }
    void setMaxImageDim(int v)   { m_max_image_dim = v; }

private:
    int  detectSSD(const cv::Mat& img, cv::Rect* out_rect);
    void extractLandmarks(const cv::Mat& img, const cv::Rect& face, float* marks);

    std::string m_model_dir;
    ncnn::Net   m_det_net;
    ncnn::Net   m_onet;

    float m_threshold      = 0.5f;
    int   m_min_face_size  = 40;
    int   m_input_size     = 192;
    int   m_max_image_dim  = 1200;
    bool  m_rotation_fallback = true;
    bool  m_initialized    = false;

    std::mutex m_mutex;
};

}  // namespace agface

#endif  // AGILESTAR_AGFACE_FACE_DETECTOR_H
