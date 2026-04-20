#ifndef AGILESTAR_AGFACE_FACE_ALIGN_H
#define AGILESTAR_AGFACE_FACE_ALIGN_H

/**
 * @file face_align.h
 * @brief 5 点相似变换对齐到 112×112（BGR 3 通道 uint8）。
 *
 * 移植自旧 ai_agface/src/ai_modules/face_feature/face_feature_base.h 的
 * `alignFace` 闭合解 + 双线性重采样逻辑（与原 Align::AlignmentCen 算法等价）。
 *
 * 用途：
 *   - agface_face_feature_* 插件在特征提取前统一做 112×112 对齐。
 *   - landmarks 可以为 nullptr，此时使用以图像中心为基准的合成地标
 *     （便于客户端只传一张已粗裁剪的人脸图，无需自己提供五点）。
 */

#include <opencv2/core.hpp>

namespace agface {

/// 标准 112×112 参考 5 点（左眼/右眼/鼻/左嘴/右嘴），[x0..x4, y0..y4]
extern const float kRefLandmarks112[10];

constexpr int kAlignedWidth  = 112;
constexpr int kAlignedHeight = 112;

/**
 * 把 BGR 人脸图对齐到 112×112。
 *
 * @param image     非空 BGR CV_8UC3
 * @param landmarks 10 floats [x0..x4, y0..y4]，像素坐标；可为 nullptr
 * @return 112×112 BGR 图；失败返回 empty Mat
 */
cv::Mat alignFaceTo112(const cv::Mat& image, const float* landmarks);

}  // namespace agface

#endif  // AGILESTAR_AGFACE_FACE_ALIGN_H
