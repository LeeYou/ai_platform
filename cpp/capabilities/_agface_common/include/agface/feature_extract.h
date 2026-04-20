#ifndef AGILESTAR_AGFACE_FEATURE_EXTRACT_H
#define AGILESTAR_AGFACE_FEATURE_EXTRACT_H

/**
 * @file feature_extract.h
 * @brief 共用的 NCNN 人脸特征提取流水：对齐 → 归一化 → forward → L2 归一化。
 *
 * 被 agface_face_feature_residual256 / agface_face_feature_glint512 等复用。
 * 预处理参数（mean / norm / input color）由 manifest 驱动，所以不同模型通过
 * 各自 manifest.json 描述即可，代码无需分叉。
 */

#include <string>
#include <vector>

#include <ncnn/net.h>
#include <opencv2/core.hpp>

#include "agface/manifest.h"
#include "agface/ncnn_session.h"

namespace agface {

/**
 * 对传入的 BGR 人脸图做 112×112 对齐（landmarks=nullptr 时使用合成地标），
 * 按 manifest 规定的 input.color / mean / norm 预处理，送入 ncnn 前向，
 * 取 manifest.output_blob，做 L2 归一化后写入 out。
 *
 * @return true 成功，out 为长度 == feature_dim（若 manifest 声明）或网络实际
 *         输出长度的一维向量。
 */
bool extractFaceFeature(NcnnSession*        session,
                        const NcnnManifest& manifest,
                        const cv::Mat&      bgr_face,
                        const float*        landmarks_opt,
                        std::vector<float>* out,
                        std::string*        error_out);

}  // namespace agface

#endif  // AGILESTAR_AGFACE_FEATURE_EXTRACT_H
