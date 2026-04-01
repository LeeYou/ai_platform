/**
 * ai_jni_bridge.cpp
 * JNI 接口层 — 封装 C ABI 供 Java 调用（cn.agilestar.ai 包）
 *
 * 此桥接层将 Java 调用透传到 C ABI（ai_capability.h），使 Android / Java
 * 应用能通过 System.loadLibrary("ai_jni") 使用本平台 AI 能力。
 *
 * 线程安全性：每个 AiHandle 不可跨线程并发使用；Java 层应借助
 *             同步机制（或实例池）保证单句柄单线程。
 */

#include "cn_agilestar_ai_AiCapability.h"
#include "ai_capability.h"

#include <cstring>
#include <string>

/* ──────────────────────────────────────────────────────────────────────────
 * 辅助函数
 * ────────────────────────────────────────────────────────────────────────── */

/**
 * 将 jstring 转换为 UTF-8 std::string；若 jstr 为 nullptr 则返回空字符串。
 */
static std::string jstringToUtf8(JNIEnv* env, jstring jstr) {
    if (!jstr) return {};
    const char* chars = env->GetStringUTFChars(jstr, nullptr);
    if (!chars) return {};
    std::string result(chars);
    env->ReleaseStringUTFChars(jstr, chars);
    return result;
}

/* ──────────────────────────────────────────────────────────────────────────
 * JNI 原生接口实现
 * ────────────────────────────────────────────────────────────────────────── */

JNIEXPORT jlong JNICALL Java_cn_agilestar_ai_AiCapability_nativeCreate(
    JNIEnv* env, jobject /* thiz */, jstring modelDir, jstring configJson) {

    std::string model_dir  = jstringToUtf8(env, modelDir);
    std::string config_json = jstringToUtf8(env, configJson);

    AiHandle handle = AiCreate(model_dir.c_str(), config_json.c_str());
    /* AiHandle 是指针，转为 jlong 传回 Java 层 */
    return reinterpret_cast<jlong>(handle);
}

JNIEXPORT jint JNICALL Java_cn_agilestar_ai_AiCapability_nativeInit(
    JNIEnv* /* env */, jobject /* thiz */, jlong handle) {

    return static_cast<jint>(
        AiInit(reinterpret_cast<AiHandle>(handle)));
}

JNIEXPORT jstring JNICALL Java_cn_agilestar_ai_AiCapability_nativeInfer(
    JNIEnv* env, jobject /* thiz */, jlong handle,
    jbyteArray imageData, jint width, jint height, jint channels) {

    /* 获取 Java byte[] 数据指针 */
    jbyte* data = env->GetByteArrayElements(imageData, nullptr);
    if (!data) {
        return env->NewStringUTF("{\"error\":\"failed to access image data\"}");
    }
    jsize data_len = env->GetArrayLength(imageData);

    /* 构造 AiImage 输入结构 */
    AiImage image;
    std::memset(&image, 0, sizeof(image));
    image.data     = reinterpret_cast<const uint8_t*>(data);
    image.width    = static_cast<int32_t>(width);
    image.height   = static_cast<int32_t>(height);
    image.channels = static_cast<int32_t>(channels);

    /* 调用 C ABI 推理接口 */
    AiResult result;
    std::memset(&result, 0, sizeof(result));
    int32_t ret = AiInfer(reinterpret_cast<AiHandle>(handle), &image, &result);

    env->ReleaseByteArrayElements(imageData, data, JNI_ABORT);

    /* 返回 JSON 结果字符串 */
    if (ret != AI_OK || !result.json_result) {
        return env->NewStringUTF("{\"error\":\"inference failed\"}");
    }

    jstring jresult = env->NewStringUTF(result.json_result);

    /* 释放 C ABI 分配的结果内存（若平台 ABI 提供 AiFreeResult） */
    AiFreeResult(&result);

    return jresult;
}

JNIEXPORT void JNICALL Java_cn_agilestar_ai_AiCapability_nativeDestroy(
    JNIEnv* /* env */, jobject /* thiz */, jlong handle) {

    AiDestroy(reinterpret_cast<AiHandle>(handle));
}
