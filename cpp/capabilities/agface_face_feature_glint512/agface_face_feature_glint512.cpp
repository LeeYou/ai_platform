/**
 * @file agface_face_feature_glint512.cpp
 * @brief agface 人脸特征（Glint360K-R34, 512 维）能力插件。
 *
 * 与 agface_face_feature_residual256 共用 feature_plugin_impl.h 中的全部
 * Ai* ABI 实现，差异仅在于模型目录 / 输出维度（512）与 manifest.json。
 *
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#define AGFACE_FEATURE_PLUGIN_NAME    "agface_face_feature_glint512"
#define AGFACE_FEATURE_PLUGIN_VERSION "1.0.0"

#include "agface/feature_plugin_impl.h"
