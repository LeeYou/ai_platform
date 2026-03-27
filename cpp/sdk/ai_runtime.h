#ifndef AGILESTAR_AI_RUNTIME_H
#define AGILESTAR_AI_RUNTIME_H

#include "ai_types.h"

#ifdef __cplusplus
extern "C" {
#endif

/* --------------------------------------------------------------------------
 * Runtime 管理接口（libai_runtime.so 导出）
 *
 * Runtime 是生产容器内的推理调度核心，负责：
 *   - 扫描并 dlopen 所有能力 SO（ABI 版本检查）
 *   - 管理每个能力的推理实例池（Acquire / Release）
 *   - 加载并缓存 License 校验结果（60 秒轮询刷新）
 *   - 验证模型包 manifest.json 完整性和 checksum
 *   - 支持热重载（reload / rollback）
 *
 * 进程生命周期：
 *   AiRuntimeInit（进程启动，调用一次）
 *   AiRuntimeAcquire / AiRuntimeRelease（每次推理请求）
 *   AiRuntimeDestroy（进程退出前，调用一次）
 * -------------------------------------------------------------------------- */

/**
 * Runtime 全局初始化（进程级，调用一次）。
 *
 * 扫描 so_dir 下所有 lib*.so 文件，调用 AiGetAbiVersion 检查兼容性，
 * 对每个合法 SO 创建最小实例数（min_instances）的推理实例，
 * 加载 license_path 指向的授权文件并完成初始校验。
 *
 * @param so_dir          能力 SO 目录（如 /app/libs 或 /mnt/ai_platform/libs）
 * @param model_base_dir  模型包根目录（如 /app/models 或 /mnt/ai_platform/models）
 * @param license_path    License 文件路径（如 /mnt/ai_platform/licenses/<id>/license.bin）
 * @return AI_OK 表示成功；其他值见 AiErrorCode
 */
int32_t AiRuntimeInit(const char* so_dir,
                      const char* model_base_dir,
                      const char* license_path);

/**
 * 获取已成功加载的能力列表（JSON 字符串）。
 *
 * 返回格式示例：
 * {
 *   "capabilities": [
 *     {"name": "face_detect",    "version": "1.0.0", "status": "loaded"},
 *     {"name": "recapture_detect","version": "1.0.0", "status": "loaded"}
 *   ]
 * }
 *
 * @param buf     调用方分配的缓冲区
 * @param buf_len 缓冲区长度（字节）
 * @return 写入字节数（不含 '\0'）；buf_len 不足时返回所需大小（正整数）
 */
int32_t AiRuntimeGetCapabilities(char* buf, int32_t buf_len);

/**
 * 从指定能力的实例池中获取一个可用推理实例。
 *
 * 若池中当前无空闲实例且未达到 max_instances 上限，则动态创建新实例。
 * 若已达上限则阻塞等待，直到有实例归还或超时。
 *
 * @param capability_name 能力标识（如 "face_detect"），必须已在 AiRuntimeInit 时加载
 * @param timeout_ms      等待超时毫秒数；0 表示立即返回（不等待）
 * @return 可用实例 Handle；超时或能力不存在返回 NULL
 */
AiHandle AiRuntimeAcquire(const char* capability_name, int32_t timeout_ms);

/**
 * 将推理实例归还到其所属能力的实例池。
 * 调用方归还后不得再使用该 handle（直到下次 Acquire）。
 *
 * @param handle 由 AiRuntimeAcquire 返回的实例 Handle
 */
void AiRuntimeRelease(AiHandle handle);

/**
 * 热重载指定能力的模型包和/或 SO（后台异步执行）。
 *
 * 触发后：
 *   1. Runtime 读取新版本目录（current 符号链接所指目录）
 *   2. 验证 manifest.json checksum 和 License 兼容性
 *   3. 验证失败 → current 回退到旧版本，旧实例继续服务
 *   4. 验证成功 → 预热新实例 → 新实例加入池 → 等待旧实例归还后销毁
 *
 * @param capability_name 需要重载的能力标识
 * @return AI_OK 表示重载流程已启动（非完成）；其他值表示启动失败
 */
int32_t AiRuntimeReload(const char* capability_name);

/**
 * 获取当前 License 状态（JSON 字符串）。
 *
 * 返回格式示例：
 * {
 *   "status": "valid",
 *   "license_id": "LS-20260327-0001",
 *   "valid_until": "2026-10-01T00:00:00Z",
 *   "days_remaining": 187,
 *   "capabilities": ["face_detect", "handwriting_reco"]
 * }
 *
 * @param buf     调用方分配的缓冲区
 * @param buf_len 缓冲区长度（字节）
 * @return 写入字节数（不含 '\0'）；buf_len 不足时返回所需大小（正整数）
 */
int32_t AiRuntimeGetLicenseStatus(char* buf, int32_t buf_len);

/**
 * Runtime 全局销毁（进程退出前调用一次）。
 * 等待所有正在执行的推理完成，销毁全部实例，卸载所有 SO。
 */
void AiRuntimeDestroy(void);

#ifdef __cplusplus
}
#endif

#endif /* AGILESTAR_AI_RUNTIME_H */
