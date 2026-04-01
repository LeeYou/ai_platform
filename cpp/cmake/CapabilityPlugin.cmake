# =============================================================================
# CapabilityPlugin.cmake
# 能力插件统一 CMake 宏
#
# 用法：
#   add_capability_plugin(
#       NAME         face_detect
#       SOURCES      face_detect.cpp face_detect_impl.cpp
#       HEADERS      face_detect.h
#       DESCRIPTION  "人脸检测 AI 能力插件"
#       COMPANY      "agilestar.cn"
#   )
#
# 宏自动完成：
#   - 创建 shared library 目标（lib<NAME>.so / <NAME>.dll）
#   - 链接公共 SDK 头文件
#   - 链接 ONNXRuntime（必选）
#   - 链接 TensorRT / CUDA（当 BUILD_GPU=ON 时）
#   - 链接 License 校验库（libai_license）
#   - 应用统一编译选项
#   - 配置安装规则（输出到 CMAKE_INSTALL_PREFIX/lib/）
# =============================================================================

function(add_capability_plugin)
    # 解析关键字参数
    cmake_parse_arguments(
        CAP             # 前缀
        ""              # 选项（无）
        "NAME;DESCRIPTION;COMPANY"  # 单值关键字
        "SOURCES;HEADERS"           # 多值关键字
        ${ARGN}
    )

    if(NOT CAP_NAME)
        message(FATAL_ERROR "add_capability_plugin: NAME is required")
    endif()
    if(NOT CAP_SOURCES)
        message(FATAL_ERROR "add_capability_plugin: SOURCES is required")
    endif()

    set(TARGET_NAME ${CAP_NAME})
    set(LIB_NAME    "lib${CAP_NAME}")

    # -------------------------------------------------------------------
    # 创建 shared library 目标
    # -------------------------------------------------------------------
    add_library(${TARGET_NAME} SHARED ${CAP_SOURCES})

    # 设置输出名称（Windows 输出 <NAME>.dll，Linux 输出 lib<NAME>.so）
    set_target_properties(${TARGET_NAME} PROPERTIES
        OUTPUT_NAME   ${CAP_NAME}
        VERSION       ${PROJECT_VERSION}
        SOVERSION     ${PROJECT_VERSION_MAJOR}
        C_VISIBILITY_PRESET   hidden
        CXX_VISIBILITY_PRESET hidden
        VISIBILITY_INLINES_HIDDEN ON
    )

    # -------------------------------------------------------------------
    # 头文件
    # -------------------------------------------------------------------
    target_include_directories(${TARGET_NAME}
        PRIVATE
            ${AI_SDK_INCLUDE_DIR}
            ${CMAKE_CURRENT_SOURCE_DIR}
    )

    # -------------------------------------------------------------------
    # 链接依赖
    # -------------------------------------------------------------------
    # ONNXRuntime（通过 FindONNXRuntime.cmake 提供的导入目标）
    if(TARGET ONNXRuntime::ONNXRuntime)
        target_link_libraries(${TARGET_NAME} PRIVATE ONNXRuntime::ONNXRuntime)
    else()
        message(WARNING "add_capability_plugin(${CAP_NAME}): ONNXRuntime not found, "
                        "inference will not work")
    endif()

    # TensorRT（可选 GPU 加速）
    if(BUILD_GPU AND TARGET TensorRT::TensorRT)
        target_link_libraries(${TARGET_NAME} PRIVATE TensorRT::TensorRT)
        target_compile_definitions(${TARGET_NAME} PRIVATE AI_ENABLE_TENSORRT=1)
    endif()

    # License 校验库（Phase 1 实现后由 license/ 子工程提供）
    if(TARGET ai_license)
        target_link_libraries(${TARGET_NAME} PRIVATE ai_license)
    endif()

    # -------------------------------------------------------------------
    # 编译宏：能力标识和版本信息
    # -------------------------------------------------------------------
    target_compile_definitions(${TARGET_NAME} PRIVATE
        AI_CAPABILITY_NAME="${CAP_NAME}"
        AI_CAPABILITY_VERSION="${PROJECT_VERSION}"
        AI_COMPANY="${CAP_COMPANY}"
    )

    # -------------------------------------------------------------------
    # 应用统一编译选项
    # -------------------------------------------------------------------
    ai_target_apply_flags(${TARGET_NAME})

    # -------------------------------------------------------------------
    # 安装规则
    # -------------------------------------------------------------------
    install(TARGETS ${TARGET_NAME}
        LIBRARY DESTINATION lib   # Linux SO
        RUNTIME DESTINATION lib   # Windows DLL（放在 lib/ 而非 bin/，与 SO 统一）
    )
    if(CAP_HEADERS)
        install(FILES ${CAP_HEADERS} DESTINATION include/agilestar/capabilities)
    endif()

    message(STATUS "Capability plugin registered: ${CAP_NAME} "
                   "(${CAP_DESCRIPTION})")
endfunction()
