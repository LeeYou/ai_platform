/**
 * capability_loader.cpp
 * 动态加载能力 SO（dlopen/dlsym），ABI 版本检查
 *
 * Phase 3 实现。此文件为骨架占位，保证 CMake 目标可编译。
 */

#include "ai_runtime_impl.h"

// Phase 3 实现内容：
//   - 扫描 so_dir 下所有 lib*.so 文件
//   - dlopen 每个 SO
//   - 调用 AiGetAbiVersion() 检查与 AI_ABI_VERSION 的兼容性
//   - 对每个合法 SO 注册到能力注册表（CapabilityRegistry）
