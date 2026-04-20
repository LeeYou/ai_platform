#ifndef AGILESTAR_AGFACE_IMAGE_UTILS_H
#define AGILESTAR_AGFACE_IMAGE_UTILS_H

/**
 * @file image_utils.h
 * @brief AiImage ↔ cv::Mat（BGR）转换工具。
 *
 * 统一约定：agface 能力插件内部一律使用 BGR 3-channel uint8 cv::Mat。
 * 若 AiImage.color_format 为 RGB 或 GRAY，会做一次性转换到 BGR。
 */

#include <opencv2/core.hpp>

#include "ai_types.h"

namespace agface {

/**
 * 将 AiImage 无拷贝地包一层 cv::Mat（BGR 情况下）。
 *
 * 若输入为 RGB/GRAY 会拷贝转换，得到独立 BGR 图。
 * 若 stride ≠ width*channels，会尊重 stride 并做必要拷贝以交付紧密排列。
 *
 * @param img  不得为 null；要求 data_type=0 (uint8)，channels ∈ {1,3}
 * @param out  输出 BGR 图；函数返回 true 时保证 out 为空/满足约束的 CV_8UC3
 * @return true 成功；false 表示参数不合法
 */
bool aiImageToBgrMat(const AiImage* img, cv::Mat* out);

}  // namespace agface

#endif  // AGILESTAR_AGFACE_IMAGE_UTILS_H
