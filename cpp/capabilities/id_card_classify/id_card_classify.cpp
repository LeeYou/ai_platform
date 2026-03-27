/**
 * id_card_classify.cpp
 * id_card_classify 能力插件 — ABI 接口实现
 *
 * Phase 3 / Phase 6 实现。此文件为骨架占位，保证 CMake 目标可编译。
 */

#include "id_card_classify.h"

// AiGetAbiVersion: 返回本插件的 ABI 版本号
AI_EXPORT int32_t AiGetAbiVersion(void) { return AI_ABI_VERSION; }

// 以下接口在 Phase 3 / Phase 6 中实现
AI_EXPORT AiHandle AiCreate(const char* /*model_dir*/, const char* /*config_json*/) { return nullptr; }
AI_EXPORT int32_t  AiInit(AiHandle /*handle*/) { return AI_ERR_INTERNAL; }
AI_EXPORT int32_t  AiInfer(AiHandle /*handle*/, const AiImage* /*input*/, AiResult* /*output*/) { return AI_ERR_INTERNAL; }
AI_EXPORT int32_t  AiReload(AiHandle /*handle*/, const char* /*new_model_dir*/) { return AI_ERR_INTERNAL; }
AI_EXPORT int32_t  AiGetInfo(AiHandle /*handle*/, char* /*buf*/, int32_t /*buf_len*/) { return -AI_ERR_INTERNAL; }
AI_EXPORT void     AiDestroy(AiHandle /*handle*/) {}
AI_EXPORT void     AiFreeResult(AiResult* result) {
    if (!result) return;
    // Phase 3 实现时在此释放 json_result 和 error_msg
    result->json_result = nullptr;
    result->error_msg   = nullptr;
}
