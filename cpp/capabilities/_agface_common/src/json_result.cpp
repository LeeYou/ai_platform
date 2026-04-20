#include "agface/json_result.h"

#include <cstdlib>
#include <cstring>
#include <string>

namespace agface {

static char* dupToMalloc(const char* s, size_t len) {
    char* buf = static_cast<char*>(std::malloc(len + 1));
    if (!buf) return nullptr;
    if (len > 0 && s) std::memcpy(buf, s, len);
    buf[len] = '\0';
    return buf;
}

void fillResult(AiResult*             result,
                int32_t               error_code,
                const nlohmann::json& payload,
                const char*           error_msg) {
    if (!result) return;
    // 默认先清零（调用方若复用 AiResult 需手动先 freeResult）
    result->json_result = nullptr;
    result->result_len  = 0;
    result->error_msg   = nullptr;
    result->error_code  = error_code;

    const std::string serialized = payload.dump();
    result->json_result = dupToMalloc(serialized.c_str(), serialized.size());
    result->result_len  = result->json_result
                              ? static_cast<int32_t>(serialized.size())
                              : 0;

    if (error_msg) {
        const size_t n  = std::strlen(error_msg);
        result->error_msg = dupToMalloc(error_msg, n);
    }
}

void fillError(AiResult* result, int32_t error_code, const char* error_msg) {
    if (!result) return;
    result->json_result = nullptr;
    result->result_len  = 0;
    result->error_code  = error_code;
    result->error_msg   = nullptr;
    if (error_msg) {
        const size_t n    = std::strlen(error_msg);
        result->error_msg = dupToMalloc(error_msg, n);
    }
}

void freeResult(AiResult* result) {
    if (!result) return;
    if (result->json_result) {
        std::free(result->json_result);
        result->json_result = nullptr;
    }
    if (result->error_msg) {
        std::free(result->error_msg);
        result->error_msg = nullptr;
    }
    result->result_len = 0;
}

}  // namespace agface
