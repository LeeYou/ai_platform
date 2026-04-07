#ifndef AGILESTAR_AI_TYPES_H
#define AGILESTAR_AI_TYPES_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* --------------------------------------------------------------------------
 * 不透明实例 Handle
 * 每个 AI 能力插件内部实现，调用方不得解引用或假设其内存布局。
 * -------------------------------------------------------------------------- */
typedef void* AiHandle;

/* --------------------------------------------------------------------------
 * 输入图像结构
 * 调用方持有 data 指针所指内存，插件不得在 AiInfer 返回后继续持有该指针。
 * -------------------------------------------------------------------------- */
typedef struct {
    const uint8_t* data;      /* 图像原始字节数据 */
    int32_t        width;     /* 图像宽度（像素） */
    int32_t        height;    /* 图像高度（像素） */
    int32_t        channels;  /* 通道数：1=灰度，3=BGR/RGB */
    int32_t        data_type; /* 像素数据类型：0=uint8，1=float32 */
    int32_t        color_format; /* 色彩空间：0=BGR，1=RGB，2=GRAY */
    int32_t        stride;    /* 每行字节数；0 表示 width * channels（紧密排列） */
} AiImage;

/* --------------------------------------------------------------------------
 * 推理结果结构
 * json_result 和 error_msg 均由插件分配内存，调用方必须通过 AiFreeResult 释放。
 * 不得跨模块（跨 SO）调用 free() 直接释放这两个字段。
 * -------------------------------------------------------------------------- */
typedef struct {
    char*   json_result; /* UTF-8 JSON 格式推理结果，由插件分配 */
    int32_t result_len;  /* json_result 字节长度（不含 '\0'） */
    int32_t error_code;  /* 0=成功，非 0 见 AiErrorCode */
    char*   error_msg;   /* 错误描述字符串，由插件分配，可为 NULL */
} AiResult;

/* --------------------------------------------------------------------------
 * 统一错误码
 *
 * 分层说明：
 *   1xxx / 2xxx / 4xxx / 5xxx  — 适用于 HTTP JSON 响应和 C ABI 返回值
 *   3xxx                       — 仅用于 HTTP 服务层（实例池/调度），不在此定义
 * -------------------------------------------------------------------------- */
typedef enum {
    AI_OK                     = 0,

    /* 1xxx：输入参数与图像 */
    AI_ERR_INVALID_PARAM      = 1001,  /* 参数无效（NULL 指针、非法值等） */
    AI_ERR_IMAGE_DECODE       = 1002,  /* 图像数据解码失败 */

    /* 2xxx：能力与模型加载 */
    AI_ERR_CAPABILITY_MISSING = 2001,  /* 指定能力不存在 */
    AI_ERR_LOAD_FAILED        = 2002,  /* 能力 SO 加载失败 */
    AI_ERR_MODEL_CORRUPT      = 2003,  /* 模型文件损坏（checksum 不匹配） */
    AI_ERR_INFER_FAILED       = 2004,  /* 推理执行错误 */

    /* 4xxx：授权 */
    AI_ERR_LICENSE_INVALID        = 4001,  /* License 无效（缺失/格式错误等） */
    AI_ERR_LICENSE_EXPIRED        = 4002,  /* License 已过期 */
    AI_ERR_LICENSE_NOT_YET_VALID  = 4003,  /* License 尚未生效 */
    AI_ERR_CAP_NOT_LICENSED       = 4004,  /* 当前能力或版本未在 License 授权范围内 */
    AI_ERR_LICENSE_MISMATCH       = 4005,  /* 机器指纹不匹配 */
    AI_ERR_LICENSE_SIGNATURE_INVALID = 4006,  /* License 签名验证失败 */

    /* 5xxx：内部错误 */
    AI_ERR_INTERNAL           = 5001,  /* 不可预期的内部错误 */
} AiErrorCode;

#ifdef __cplusplus
}
#endif

#endif /* AGILESTAR_AI_TYPES_H */
