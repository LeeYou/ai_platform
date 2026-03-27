cmake_minimum_required(VERSION 3.26)

# JNI 接口层（libai_jni.so）
# Phase 6 实现。此处为骨架占位。
add_library(ai_jni SHARED
    ai_jni_bridge.cpp
)

find_package(JNI REQUIRED)

target_include_directories(ai_jni
    PRIVATE
        ${AI_SDK_INCLUDE_DIR}
        ${JNI_INCLUDE_DIRS}
        ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_libraries(ai_jni
    PRIVATE
        ai_runtime
        ${JNI_LIBRARIES}
)

set_target_properties(ai_jni PROPERTIES
    OUTPUT_NAME               ai_jni
    VERSION                   ${PROJECT_VERSION}
    SOVERSION                 ${PROJECT_VERSION_MAJOR}
    CXX_VISIBILITY_PRESET     hidden
    VISIBILITY_INLINES_HIDDEN ON
)

ai_target_apply_flags(ai_jni)

install(TARGETS ai_jni
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION lib
)
install(FILES cn_agilestar_ai_AiCapability.h DESTINATION include/agilestar/jni)
