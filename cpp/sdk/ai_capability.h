#ifndef AGILESTAR_AI_CAPABILITY_H
#define AGILESTAR_AI_CAPABILITY_H

#include "ai_types.h"

/* --------------------------------------------------------------------------
 * 跨平台符号导出宏
 * -------------------------------------------------------------------------- */
#ifdef _WIN32
#  define AI_EXPORT __declspec(dllexport)
#else
#  define AI_EXPORT __attribute__((visibility("default")))
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* --------------------------------------------------------------------------
 * ABI 版本号
 *
 * 编码规则：major * 10000 + minor * 100 + patch
 * 当前版本：v1.0.0 → 10000
 *
 * 兼容性规则：
 *   新增接口（不破坏现有接口）  → minor +1（向后兼容）
 *   修改现有接口签名            → major +1（不兼容，Runtime 拒绝加载）
 *   修改数据结构内存布局        → major +1（不兼容）
 *   新增 AiErrorCode 枚举值    → minor +1（调用方需处理未知值）
 * -------------------------------------------------------------------------- */
#define AI_ABI_VERSION 10000  /* v1.0.0 */

/**
 * 返回本插件实现的 ABI 版本号。
 * Runtime 在 dlopen 后第一个调用此接口，版本不兼容则拒绝加载。
 */
AI_EXPORT int32_t AiGetAbiVersion(void);

/* --------------------------------------------------------------------------
 * 实例生命周期接口
 * -------------------------------------------------------------------------- */

/**
 * 创建能力实例（分配内部数据结构，不加载模型）。
 *
 * @param model_dir   模型包目录的绝对路径，目录内须含 manifest.json 和 model.onnx
 * @param config_json 可选的 JSON 字符串，用于覆盖 manifest 中的推理参数；传 NULL 使用默认值
 * @return 实例 Handle；失败返回 NULL
 */
AI_EXPORT AiHandle AiCreate(const char* model_dir, const char* config_json);

/**
 * 初始化实例（加载模型文件、校验 License、预热推理引擎）。
 * 必须在 AiCreate 成功后、首次 AiInfer 调用前执行，且只调用一次。
 *
 * @param handle 由 AiCreate 返回的实例 Handle
 * @return AI_OK 表示成功；其他值见 AiErrorCode
 */
AI_EXPORT int32_t AiInit(AiHandle handle);

/**
 * 执行单次推理。
 *
 * 线程安全约束：
 *   - 同一 handle 不得被多个线程并发调用（调用方负责互斥）
 *   - 不同 handle 之间相互线程安全
 *
 * @param handle  由 AiCreate 返回的实例 Handle
 * @param input   输入图像，调用方持有内存，函数返回后可安全释放
 * @param output  推理结果，插件分配内存，调用方须通过 AiFreeResult 释放
 * @return AI_OK 表示成功；其他值见 AiErrorCode
 */
AI_EXPORT int32_t AiInfer(AiHandle handle, const AiImage* input, AiResult* output);

/**
 * 热重载模型（替换模型包后无需销毁重建实例）。
 *
 * 重载期间：
 *   - 当前 handle 不可用于推理（调用方须等待 reload 完成）
 *   - Runtime 层负责保证 reload 与正在执行的推理不冲突
 *
 * @param handle        实例 Handle
 * @param new_model_dir 新模型包目录的绝对路径
 * @return AI_OK 表示成功；其他值见 AiErrorCode
 */
AI_EXPORT int32_t AiReload(AiHandle handle, const char* new_model_dir);

/**
 * 获取能力与模型元信息（JSON 字符串）。
 *
 * 与 snprintf 行为一致：
 *   - 成功：返回写入字节数（不含 '\0'）
 *   - buf_len 不足：返回所需缓冲区大小（正整数，不含 '\0'），未写入任何内容
 *   - 出错（handle 无效等）：返回对应 AiErrorCode 的负数（如 -5001）
 * 可传 info_buf=NULL、buf_len=0 先查询所需大小，再分配缓冲区二次调用。
 *
 * @param handle   实例 Handle
 * @param info_buf 调用方分配的缓冲区，可为 NULL（配合 buf_len=0 使用）
 * @param buf_len  缓冲区长度（字节）
 * @return 见上述说明
 */
AI_EXPORT int32_t AiGetInfo(AiHandle handle, char* info_buf, int32_t buf_len);

/**
 * 销毁实例并释放全部资源（模型权重、GPU 显存、ONNX Session 等）。
 * 调用后 handle 立即失效，不得再使用。
 *
 * @param handle 实例 Handle
 */
AI_EXPORT void AiDestroy(AiHandle handle);

/**
 * 释放由 AiInfer 分配的 AiResult 内存（json_result 和 error_msg）。
 * 必须由与 AiInfer 同一插件导出的此函数释放，不得跨模块调用 free()。
 *
 * @param result 指向 AiResult 的指针；result 本身由调用方栈/堆管理，此函数仅释放其内部字段
 */
AI_EXPORT void AiFreeResult(AiResult* result);

#ifdef __cplusplus
}
#endif

#endif /* AGILESTAR_AI_CAPABILITY_H */
