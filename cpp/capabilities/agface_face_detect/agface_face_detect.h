#ifndef AGILESTAR_AGFACE_FACE_DETECT_H
#define AGILESTAR_AGFACE_FACE_DETECT_H

/**
 * @file agface_face_detect.h
 * @brief agface_face_detect 能力插件内部上下文。
 *
 * 后端：NCNN（SSD 头，对齐旧 ai_agface detection.param/bin）
 * 推理流程（迁移自旧 FaceDetectRetina::detect）：
 *   1. AiImage → cv::Mat BGR
 *   2. 限高缩放（长边 ≤ max_image_dim）
 *   3. ncnn::Mat::from_pixels_resize(BGR, w, h, in_w, in_h)
 *      其中 in_w × in_h ≈ base_size²，保持输入宽高比
 *   4. substract_mean_normalize(mean, nullptr)
 *   5. create_extractor → input("data", ...) → extract("detection_out", ...)
 *   6. 遍历 [N, 6] 输出：每行 [label, conf, x1, y1, x2, y2]（归一化坐标）
 *   7. 阈值筛选 + 最小人脸过滤 + 映射回原图坐标
 * 输出 JSON：
 *   {
 *     "faces": [
 *       {"bbox":[x,y,w,h], "confidence":0.9x, "class_id":int}
 *     ],
 *     "image_size": [W, H]
 *   }
 */

#include <memory>
#include <mutex>
#include <string>

#include <ncnn/net.h>

#include "agface/instance_pool.h"
#include "agface/manifest.h"
#include "agface/ncnn_session.h"

struct AgfaceFaceDetectContext {
    std::string          model_dir;
    agface::NcnnManifest manifest;

    // 所有池内会话共享一份权重
    std::shared_ptr<ncnn::Net>                                       shared_net;
    std::unique_ptr<agface::InstancePool<agface::NcnnSession>>       pool;

    // reload 原子替换期间的互斥
    std::mutex reload_mu;

    bool initialized = false;
};

#endif  // AGILESTAR_AGFACE_FACE_DETECT_H
