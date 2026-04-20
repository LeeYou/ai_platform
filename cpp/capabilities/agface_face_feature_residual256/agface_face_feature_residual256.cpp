/**
 * @file agface_face_feature_residual256.cpp
 * @brief agface 人脸特征（ResNet Residual, 256 维）能力插件。
 *
 * 整套 Ai* ABI 由 @/cpp/capabilities/_agface_common/include/agface/feature_plugin_impl.h
 * 提供；本插件只需声明标识与版本，即可复用全部实现。模型差异（input/output
 * blob、feature_dim、mean/norm）由 manifest.json 驱动。
 *
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#define AGFACE_FEATURE_PLUGIN_NAME    "agface_face_feature_residual256"
#define AGFACE_FEATURE_PLUGIN_VERSION "1.0.0"

#include "agface/feature_plugin_impl.h"
