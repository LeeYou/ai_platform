#include "agface/face_align.h"

#include <algorithm>
#include <cmath>

namespace agface {

const float kRefLandmarks112[10] = {
    // x: left_eye, right_eye, nose, left_mouth, right_mouth
    38.2946f, 73.5318f, 56.0252f, 41.5493f, 70.7299f,
    // y
    51.6963f, 51.5014f, 71.7366f, 92.3655f, 92.2041f,
};

cv::Mat alignFaceTo112(const cv::Mat& image, const float* landmarks) {
    if (image.empty() || image.channels() != 3) return cv::Mat();

    const int w = image.cols;
    const int h = image.rows;

    // 源 5 点（像素坐标）
    float pts[10];
    if (landmarks) {
        for (int k = 0; k < 5; ++k) {
            pts[k * 2]     = landmarks[k];
            pts[k * 2 + 1] = landmarks[k + 5];
        }
    } else {
        // 合成地标：以图像中心为基准的正脸比例（与旧 face_feature_base.h 一致）
        const float fw = static_cast<float>(w);
        const float fh = static_cast<float>(h);
        pts[0] = fw * 0.35f; pts[1] = fh * 0.35f;  // left eye
        pts[2] = fw * 0.65f; pts[3] = fh * 0.35f;  // right eye
        pts[4] = fw * 0.50f; pts[5] = fh * 0.55f;  // nose
        pts[6] = fw * 0.38f; pts[7] = fh * 0.72f;  // left mouth
        pts[8] = fw * 0.62f; pts[9] = fh * 0.72f;  // right mouth
    }

    // 相似变换闭合解（与旧 alignFace 算法逐行等价）
    double sum_x = 0, sum_y = 0, sum_u = 0, sum_v = 0;
    double sum_xx_yy = 0, sum_ux_vy = 0, sum_vx_uy = 0;

    for (int c = 0; c < 5; ++c) {
        double sx = kRefLandmarks112[c];
        double sy = kRefLandmarks112[c + 5];
        double ux = pts[c * 2];
        double uy = pts[c * 2 + 1];

        sum_x += sx;
        sum_y += sy;
        sum_u += ux;
        sum_v += uy;
        sum_xx_yy += sx * sx + sy * sy;
        sum_ux_vy += sx * ux + sy * uy;
        sum_vx_uy += uy * sx - ux * sy;
    }

    if (sum_xx_yy < 1e-12) return cv::Mat();

    double q  = sum_u - sum_x * sum_ux_vy / sum_xx_yy
                + sum_y * sum_vx_uy / sum_xx_yy;
    double p  = sum_v - sum_y * sum_ux_vy / sum_xx_yy
                - sum_x * sum_vx_uy / sum_xx_yy;
    double r  = 5.0 - (sum_x * sum_x + sum_y * sum_y) / sum_xx_yy;
    if (std::fabs(r) < 1e-12) return cv::Mat();

    double a  = (sum_ux_vy - sum_x * q / r - sum_y * p / r) / sum_xx_yy;
    double b  = (sum_vx_uy + sum_y * q / r - sum_x * p / r) / sum_xx_yy;
    double cc = q / r;
    double d  = p / r;

    // 双线性重采样（与旧 alignFace 的像素遍历顺序一致：外层 x 遍历行、内层 y 遍历列）
    cv::Mat aligned(kAlignedHeight, kAlignedWidth, CV_8UC3);

    for (int x = 0; x < kAlignedHeight; ++x) {
        for (int y = 0; y < kAlignedWidth; ++y) {
            const float src_y_f = static_cast<float>(a * y - b * x + cc);
            const float src_x_f = static_cast<float>(b * y + a * x + d);

            const int   sx = static_cast<int>(src_x_f);
            const int   sy = static_cast<int>(src_y_f);
            const float fx = src_x_f - sx;
            const float fy = src_y_f - sy;

            for (int ch = 0; ch < 3; ++ch) {
                float v00 = 0, v01 = 0, v10 = 0, v11 = 0;
                if (sx >= 0 && sx < h && sy >= 0 && sy < w)
                    v00 = image.at<cv::Vec3b>(sx, sy)[ch];
                if (sx >= 0 && sx < h && sy + 1 >= 0 && sy + 1 < w)
                    v01 = image.at<cv::Vec3b>(sx, sy + 1)[ch];
                if (sx + 1 >= 0 && sx + 1 < h && sy >= 0 && sy < w)
                    v10 = image.at<cv::Vec3b>(sx + 1, sy)[ch];
                if (sx + 1 >= 0 && sx + 1 < h && sy + 1 >= 0 && sy + 1 < w)
                    v11 = image.at<cv::Vec3b>(sx + 1, sy + 1)[ch];

                const float val = v00 * (1 - fx) * (1 - fy) + v01 * (1 - fx) * fy
                                + v10 * fx * (1 - fy) + v11 * fx * fy;
                aligned.at<cv::Vec3b>(x, y)[ch] =
                    static_cast<uchar>(std::max(0.0f, std::min(255.0f, val)));
            }
        }
    }

    return aligned;
}

}  // namespace agface
