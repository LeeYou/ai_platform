/**
 * license_checker.cpp
 * License 校验（调用授权库），结果缓存 60 秒
 *
 * Phase 3 实现。此文件为骨架占位，保证 CMake 目标可编译。
 */

#include "ai_runtime_impl.h"

// Phase 3 实现内容：
//   - 调用 Phase 1 实现的 license_core 库进行签名验证
//   - 缓存校验结果（valid / expired / invalid），60 秒内不重复 IO
//   - 提供 CheckLicense(capability_name) 接口供 HTTP 层调用
//   - 后台线程每 60 秒轮询刷新缓存
