#include "agface/feature_extract.h"

#include <cmath>

#include <opencv2/imgproc.hpp>

#include "agface/face_align.h"

namespace agface {

static ncnn::Mat::PixelType pixelTypeFromManifestColor(const std::string& color,
                                                      bool               src_is_bgr) {
    // 对齐 后的 aligned 是 BGR；目标张量色彩顺序由 manifest 指定。
    if (color == "RGB") {
        return src_is_bgr ? ncnn::Mat::PIXEL_BGR2RGB : ncnn::Mat::PIXEL_RGB;
    }
    if (color == "GRAY") {
        return src_is_bgr ? ncnn::Mat::PIXEL_BGR2GRAY : ncnn::Mat::PIXEL_GRAY;
    }
    // 默认 BGR
    return src_is_bgr ? ncnn::Mat::PIXEL_BGR : ncnn::Mat::PIXEL_RGB2BGR;
}

bool extractFaceFeature(NcnnSession*        session,
                        const NcnnManifest& manifest,
                        const cv::Mat&      bgr_face,
                        const float*        landmarks_opt,
                        std::vector<float>* out,
                        std::string*        error_out) {
    auto fail = [&](const std::string& m) {
        if (error_out) *error_out = m;
        return false;
    };
    if (!session || !out) return fail("session or out is null");
    if (bgr_face.empty() || bgr_face.channels() != 3)
        return fail("bgr_face invalid (empty or not 3-channel)");

    // 1) 对齐到 112×112（BGR）
    const cv::Mat aligned = alignFaceTo112(bgr_face, landmarks_opt);
    if (aligned.empty()) return fail("face alignment failed");

    // 2) 送入 ncnn：按 manifest.input.color 决定像素顺序，base_size 沿用 112
    const ncnn::Mat::PixelType pix = pixelTypeFromManifestColor(
        manifest.input_color, /*src_is_bgr=*/true);
    const int target = manifest.input_base_size > 0 ? manifest.input_base_size : 112;

    ncnn::Mat in = ncnn::Mat::from_pixels_resize(
        aligned.data, pix, aligned.cols, aligned.rows, target, target);
    in.substract_mean_normalize(manifest.mean.data(), manifest.norm.data());

    ncnn::Extractor ex = session->createExtractor();
    if (ex.input(manifest.input_blob.c_str(), in) != 0)
        return fail("ncnn input set failed: " + manifest.input_blob);

    ncnn::Mat feat;
    if (ex.extract(manifest.output_blob.c_str(), feat) != 0)
        return fail("ncnn extract failed: " + manifest.output_blob);

    const int dim = feat.w > 0 ? feat.w
                               : static_cast<int>(feat.total());
    if (dim <= 0) return fail("feature output dim <= 0");
    if (manifest.feature_dim > 0 && dim != manifest.feature_dim) {
        return fail("feature_dim mismatch: manifest says "
                    + std::to_string(manifest.feature_dim)
                    + " but got " + std::to_string(dim));
    }

    out->resize(dim);
    const float* src = static_cast<const float*>(feat.data);
    for (int i = 0; i < dim; ++i) (*out)[i] = src[i];

    // 3) L2 归一化（便于下游直接做余弦相似度 = 点积）
    double sq = 0.0;
    for (float v : *out) sq += static_cast<double>(v) * v;
    if (sq > 1e-12) {
        const float inv = static_cast<float>(1.0 / std::sqrt(sq));
        for (float& v : *out) v *= inv;
    }
    return true;
}

}  // namespace agface
