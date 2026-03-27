cmake_minimum_required(VERSION 3.26)

# Runtime 库（libai_runtime.so）
# 职责：动态加载能力 SO、管理实例池、License 校验缓存、模型包验证
# Phase 3 实现，此处为骨架占位
add_library(ai_runtime SHARED
    capability_loader.cpp
    instance_pool.cpp
    license_checker.cpp
    model_loader.cpp
)

target_include_directories(ai_runtime
    PUBLIC
        ${AI_SDK_INCLUDE_DIR}
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

set_target_properties(ai_runtime PROPERTIES
    OUTPUT_NAME       ai_runtime
    VERSION           ${PROJECT_VERSION}
    SOVERSION         ${PROJECT_VERSION_MAJOR}
    CXX_VISIBILITY_PRESET     hidden
    VISIBILITY_INLINES_HIDDEN ON
)

# Linux：-ldl 用于 dlopen/dlsym/dlclose
if(UNIX AND NOT APPLE)
    target_link_libraries(ai_runtime PRIVATE dl)
endif()

ai_target_apply_flags(ai_runtime)

install(TARGETS ai_runtime
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION lib
)
install(FILES include/ai_runtime_impl.h DESTINATION include/agilestar)
