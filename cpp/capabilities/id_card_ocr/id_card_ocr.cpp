/**
 * id_card_ocr.cpp
 * 身份证全字段OCR — ABI 接口实现骨架
 *
 * TODO: 实现各接口。
 *
 * Copyright © 2026 北京爱知之星科技股份有限公司 (Agile Star). agilestar.cn
 */

#include "id_card_ocr.h"

AI_EXPORT int32_t AiGetAbiVersion(void) { return AI_ABI_VERSION; }

AI_EXPORT AiHandle AiCreate(const char* /*model_dir*/, const char* /*config_json*/) { return nullptr; }
AI_EXPORT int32_t  AiInit(AiHandle /*handle*/) { return AI_ERR_INTERNAL; }
AI_EXPORT int32_t  AiInfer(AiHandle /*handle*/, const AiImage* /*input*/, AiResult* /*output*/) { return AI_ERR_INTERNAL; }
AI_EXPORT int32_t  AiReload(AiHandle /*handle*/, const char* /*new_model_dir*/) { return AI_ERR_INTERNAL; }
AI_EXPORT int32_t  AiGetInfo(AiHandle /*handle*/, char* /*buf*/, int32_t /*buf_len*/) { return -AI_ERR_INTERNAL; }
AI_EXPORT void     AiDestroy(AiHandle /*handle*/) {}
AI_EXPORT void     AiFreeResult(AiResult* result) {
    if (!result) return;
    result->json_result = nullptr;
    result->error_msg   = nullptr;
}
