#include "agface/image_utils.h"

#include <opencv2/imgproc.hpp>

namespace agface {

// color_format 约定（与 ai_types.h 一致）：0=BGR，1=RGB，2=GRAY
static constexpr int kColorBGR  = 0;
static constexpr int kColorRGB  = 1;
static constexpr int kColorGRAY = 2;

bool aiImageToBgrMat(const AiImage* img, cv::Mat* out) {
    if (!img || !img->data || !out) return false;
    if (img->width <= 0 || img->height <= 0) return false;
    if (img->data_type != 0) return false;  // 只支持 uint8
    if (img->channels != 1 && img->channels != 3) return false;

    const int rowBytes =
        (img->stride > 0) ? img->stride : img->width * img->channels;
    const int expectedTight = img->width * img->channels;

    // Step 1: 包一层 cv::Mat（可能共享 AiImage 内存）
    const int cvType = (img->channels == 1) ? CV_8UC1 : CV_8UC3;
    cv::Mat   wrapped(img->height, img->width, cvType,
                      const_cast<uint8_t*>(img->data),
                      static_cast<size_t>(rowBytes));

    // Step 2: 若 stride 不紧密，必须 clone 到紧密排列
    cv::Mat tight = (rowBytes == expectedTight) ? wrapped : wrapped.clone();

    // Step 3: 颜色转换到 BGR 3 通道
    switch (img->color_format) {
        case kColorBGR:
            if (img->channels == 3) {
                // 若 tight 就是 wrapped 的视图，后续我们希望 out 拥有独立缓冲区
                // （避免调用方释放 AiImage.data 后 out 悬空）
                *out = tight.clone();
            } else {  // 单通道当作灰度
                cv::cvtColor(tight, *out, cv::COLOR_GRAY2BGR);
            }
            break;
        case kColorRGB:
            if (img->channels == 3) {
                cv::cvtColor(tight, *out, cv::COLOR_RGB2BGR);
            } else {
                cv::cvtColor(tight, *out, cv::COLOR_GRAY2BGR);
            }
            break;
        case kColorGRAY:
            if (img->channels == 1) {
                cv::cvtColor(tight, *out, cv::COLOR_GRAY2BGR);
            } else {
                // 3 通道但声明为 GRAY —— 先转灰度再转 BGR
                cv::Mat gray;
                cv::cvtColor(tight, gray, cv::COLOR_BGR2GRAY);
                cv::cvtColor(gray, *out, cv::COLOR_GRAY2BGR);
            }
            break;
        default:
            // 未知 color_format：按 BGR 处理
            if (img->channels == 3) {
                *out = tight.clone();
            } else {
                cv::cvtColor(tight, *out, cv::COLOR_GRAY2BGR);
            }
            break;
    }

    return !out->empty();
}

}  // namespace agface
