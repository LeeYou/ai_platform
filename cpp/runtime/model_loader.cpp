/**
 * model_loader.cpp
 * 模型包加载：读取 manifest.json、校验 checksum
 *
 * Phase 3 实现。此文件为骨架占位，保证 CMake 目标可编译。
 */

#include "ai_runtime_impl.h"

// Phase 3 实现内容：
//   - 读取 <model_dir>/manifest.json，解析元数据
//   - 用 SHA256 校验 model.onnx 与 manifest 中记录的 checksum 是否一致
//   - 验证 capability 名称与 ABI 版本约束
//   - 验证失败时返回 AI_ERR_MODEL_CORRUPT，记录详细错误日志
