/**
 * @file agface_face_feature_mobilenet256.cpp
 * @brief agface 人脸特征（MobileFaceNet, 256 维）能力插件。
 *
 * 与 residual256 / glint512 共用 feature_plugin_impl.h，差异仅在
 * manifest.json 的 output.blob (= "fc1") 与模型目录。
 *
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#define AGFACE_FEATURE_PLUGIN_NAME    "agface_face_feature_mobilenet256"
#define AGFACE_FEATURE_PLUGIN_VERSION "1.0.0"

#include "agface/feature_plugin_impl.h"
