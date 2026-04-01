/**
 * cn_agilestar_ai_AiCapability.h
 * JNI 原生接口声明（对应 Java 类 cn.agilestar.ai.AiCapability）
 *
 * 此文件通常由 javah 或 javac -h 自动生成，此处手工维护以供骨架阶段使用。
 */

#ifndef CN_AGILESTAR_AI_AICAPABILITY_H
#define CN_AGILESTAR_AI_AICAPABILITY_H

#include <jni.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * 创建能力实例。
 * Java: private native long nativeCreate(String modelDir, String configJson);
 */
JNIEXPORT jlong JNICALL Java_cn_agilestar_ai_AiCapability_nativeCreate(
    JNIEnv* env, jobject thiz, jstring modelDir, jstring configJson);

/**
 * 初始化实例（加载模型、校验 License）。
 * Java: private native int nativeInit(long handle);
 */
JNIEXPORT jint JNICALL Java_cn_agilestar_ai_AiCapability_nativeInit(
    JNIEnv* env, jobject thiz, jlong handle);

/**
 * 执行单次推理，返回 JSON 结果字符串。
 * Java: private native String nativeInfer(long handle, byte[] imageData,
 *                                         int width, int height, int channels);
 */
JNIEXPORT jstring JNICALL Java_cn_agilestar_ai_AiCapability_nativeInfer(
    JNIEnv* env, jobject thiz, jlong handle,
    jbyteArray imageData, jint width, jint height, jint channels);

/**
 * 销毁实例，释放所有资源。
 * Java: private native void nativeDestroy(long handle);
 */
JNIEXPORT void JNICALL Java_cn_agilestar_ai_AiCapability_nativeDestroy(
    JNIEnv* env, jobject thiz, jlong handle);

#ifdef __cplusplus
}
#endif

#endif /* CN_AGILESTAR_AI_AICAPABILITY_H */
