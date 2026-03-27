/**
 * ai_jni_bridge.cpp
 * JNI 接口层 — 封装 C ABI 供 Java 调用（cn.agilestar.ai 包）
 *
 * Phase 6 实现。此文件为骨架占位，保证 CMake 目标可编译。
 */

#include "cn_agilestar_ai_AiCapability.h"
#include "ai_capability.h"

// Phase 6 实现内容：
//   - nativeCreate：调用 AiCreate，将 AiHandle 转为 jlong 返回 Java
//   - nativeInit：调用 AiInit
//   - nativeInfer：调用 AiInfer，将 AiResult.json_result 转为 jstring 返回 Java
//   - nativeDestroy：调用 AiDestroy
