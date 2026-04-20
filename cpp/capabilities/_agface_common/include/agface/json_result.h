#ifndef AGILESTAR_AGFACE_JSON_RESULT_H
#define AGILESTAR_AGFACE_JSON_RESULT_H

/**
 * @file json_result.h
 * @brief AiResult 的 JSON 填充工具 —— 与 SDK 的 AiFreeResult 释放约定严格对齐。
 *
 * 约定（@/cpp/sdk/ai_types.h）：
 *   AiResult::json_result 和 AiResult::error_msg 必须由插件用 std::malloc 分配，
 *   由插件导出的 AiFreeResult 用 std::free 释放。不得跨模块调用 free()。
 */

#include <string>

#include <nlohmann/json.hpp>

#include "ai_types.h"

namespace agface {

/**
 * 用给定的 JSON 对象填充 AiResult。
 *
 * @param result      非空输出结构
 * @param error_code  AiErrorCode（AI_OK=0 成功）
 * @param payload     成功时的 JSON 结果；即使失败也可附带（例如 {"error":"..."}）
 * @param error_msg   可选错误描述；nullptr 表示不填 error_msg
 *
 * 函数内部用 std::malloc 分配内存并写入；配合本模块导出的 AiFreeResult 释放。
 */
void fillResult(AiResult*              result,
                int32_t                error_code,
                const nlohmann::json&  payload,
                const char*            error_msg = nullptr);

/**
 * 便捷版：仅填错误码 + 错误文本，json_result 置空。
 */
void fillError(AiResult* result, int32_t error_code, const char* error_msg);

/**
 * 标准 AiFreeResult 实现 —— 能力插件的 AiFreeResult 可直接转调此函数。
 * std::free 两个字段并置空长度。
 */
void freeResult(AiResult* result);

}  // namespace agface

#endif  // AGILESTAR_AGFACE_JSON_RESULT_H
