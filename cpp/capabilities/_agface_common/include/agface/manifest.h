#ifndef AGILESTAR_AGFACE_MANIFEST_H
#define AGILESTAR_AGFACE_MANIFEST_H

/**
 * @file manifest.h
 * @brief 解析 agface 能力的模型包 manifest.json。
 *
 * 约定的 manifest.json 字段（示例）：
 * {
 *   "name":    "agface_face_detect",
 *   "version": "1.0.0",
 *   "backend": "ncnn",
 *   "param_file": "detection.param",
 *   "bin_file":   "detection.bin",
 *   "input": {
 *     "blob": "data",
 *     "base_size": 192,                 // 与旧 ai_agface/kInputSize 对齐
 *     "color": "BGR",
 *     "mean":  [104.0, 117.0, 123.0],
 *     "norm":  [1.0, 1.0, 1.0]
 *   },
 *   "output": {
 *     "blob": "detection_out",
 *     "format": "ssd"                   // 或 "yolov5" / "retinaface_anchor" 等
 *   },
 *   "thresholds": {
 *     "score":    0.5,
 *     "min_face": 40,
 *     "max_image_dim": 1200
 *   }
 * }
 */

#include <array>
#include <string>

namespace agface {

struct NcnnManifest {
    std::string name;
    std::string version;
    std::string backend;  // "ncnn"

    std::string param_file;
    std::string bin_file;

    // Input
    std::string        input_blob     = "data";
    int                input_base_size = 192;
    std::string        input_color    = "BGR";
    std::array<float, 3> mean         = {104.f, 117.f, 123.f};
    std::array<float, 3> norm         = {1.f, 1.f, 1.f};

    // Output
    std::string output_blob   = "detection_out";
    std::string output_format = "ssd";

    // Thresholds
    float score_threshold = 0.5f;
    int   min_face        = 40;
    int   max_image_dim   = 1200;

    // 特征提取专用（feature 插件读取）
    int   feature_dim     = 0;  // 0 表示未声明；>0 时启用维度自检

    // 解析后的绝对路径（由 loadFromDir 填充）
    std::string param_path;
    std::string bin_path;
};

/**
 * 从模型目录加载并解析 manifest.json。
 *
 * @param model_dir 绝对路径，目录内必须包含 manifest.json
 * @param out       成功时填充
 * @param error_out 失败时填充可读错误描述
 * @return true 成功；false 失败（error_out 含原因）
 */
bool loadManifestFromDir(const std::string& model_dir,
                         NcnnManifest*      out,
                         std::string*       error_out);

}  // namespace agface

#endif  // AGILESTAR_AGFACE_MANIFEST_H
