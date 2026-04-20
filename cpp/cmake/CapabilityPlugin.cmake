# =============================================================================
# CapabilityPlugin.cmake
# 能力插件统一 CMake 宏
#
# 用法：
#   add_capability_plugin(
#       NAME         face_detect
#       SOURCES      face_detect.cpp face_detect_impl.cpp
#       HEADERS      face_detect.h
#       BACKEND      ONNX                # 可选：ONNX（默认）/ NCNN / NONE
#       EXTRA_LIBS   agface_common       # 可选：追加 target_link_libraries PRIVATE
#       DESCRIPTION  "人脸检测 AI 能力插件"
#       COMPANY      "agilestar.cn"
#   )
#
# 宏自动完成：
#   - 创建 shared library 目标（lib<NAME>.so / <NAME>.dll）
#   - 链接公共 SDK 头文件
#   - 按 BACKEND 自动挂接推理引擎：
#       ONNX  → 链 ONNXRuntime::ONNXRuntime（+ TensorRT，若 ENABLE_TENSORRT=ON）
#       NCNN  → 链 NCNN::NCNN 与 OpenCV（core/imgproc/imgcodecs）
#       NONE  → 不链任何推理引擎（适用于纯 CPU 后处理型能力）
#   - 链接 License 校验库（libai_license，若存在）
#   - 应用统一编译选项
#   - 配置安装规则（输出到 CMAKE_INSTALL_PREFIX/lib/）
# =============================================================================

function(add_capability_plugin)
    # 解析关键字参数
    cmake_parse_arguments(
        CAP             # 前缀
        ""              # 选项（无）
        "NAME;DESCRIPTION;COMPANY;BACKEND"  # 单值关键字
        "SOURCES;HEADERS;EXTRA_LIBS"        # 多值关键字
        ${ARGN}
    )

    # BACKEND 默认值：ONNX（与历史插件兼容）
    if(NOT CAP_BACKEND)
        set(CAP_BACKEND "ONNX")
    endif()
    string(TOUPPER "${CAP_BACKEND}" CAP_BACKEND)
    if(NOT CAP_BACKEND MATCHES "^(ONNX|NCNN|NONE)$")
        message(FATAL_ERROR "add_capability_plugin(${CAP_NAME}): BACKEND must be one of ONNX / NCNN / NONE (got '${CAP_BACKEND}')")
    endif()

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
    # 按 BACKEND 链接推理引擎依赖
    # -------------------------------------------------------------------
    if(CAP_BACKEND STREQUAL "ONNX")
        if(TARGET ONNXRuntime::ONNXRuntime)
            target_link_libraries(${TARGET_NAME} PRIVATE ONNXRuntime::ONNXRuntime)
        else()
            message(WARNING "add_capability_plugin(${CAP_NAME}): BACKEND=ONNX but "
                            "ONNXRuntime not found, inference will not work")
        endif()

        # TensorRT（可选 GPU 加速，仅对 ONNX 后端生效）
        if(ENABLE_TENSORRT AND TARGET TensorRT::TensorRT)
            target_link_libraries(${TARGET_NAME} PRIVATE TensorRT::TensorRT)
            target_compile_definitions(${TARGET_NAME} PRIVATE AI_ENABLE_TENSORRT=1)
        endif()

        target_compile_definitions(${TARGET_NAME} PRIVATE AI_BACKEND_ONNX=1)

    elseif(CAP_BACKEND STREQUAL "NCNN")
        # 懒加载：仅当有插件真正使用 NCNN 后端时才解析查找
        if(NOT TARGET NCNN::NCNN)
            include(FindNCNN)
        endif()
        if(TARGET NCNN::NCNN)
            target_link_libraries(${TARGET_NAME} PRIVATE NCNN::NCNN)
        else()
            message(FATAL_ERROR "add_capability_plugin(${CAP_NAME}): BACKEND=NCNN but "
                                "NCNN::NCNN not found. Install libncnn-dev, set NCNN_ROOT, "
                                "or add cpp/third_party/ncnn submodule.")
        endif()

        # OpenCV 作为 NCNN 能力的标准图像处理依赖（core/imgproc/imgcodecs）
        find_package(OpenCV QUIET COMPONENTS core imgproc imgcodecs)
        if(OpenCV_FOUND)
            target_include_directories(${TARGET_NAME} PRIVATE ${OpenCV_INCLUDE_DIRS})
            target_link_libraries(${TARGET_NAME} PRIVATE ${OpenCV_LIBS})
        else()
            message(FATAL_ERROR "add_capability_plugin(${CAP_NAME}): BACKEND=NCNN requires OpenCV "
                                "(core/imgproc/imgcodecs). Install libopencv-dev or set OpenCV_DIR.")
        endif()

        target_compile_definitions(${TARGET_NAME} PRIVATE AI_BACKEND_NCNN=1)

    elseif(CAP_BACKEND STREQUAL "NONE")
        # 纯 CPU 后处理型能力（如余弦相似度、仿射对齐等），无需推理引擎
        target_compile_definitions(${TARGET_NAME} PRIVATE AI_BACKEND_NONE=1)
    endif()

    # License 校验库（Phase 1 实现后由 license/ 子工程提供）
    if(TARGET ai_license)
        target_link_libraries(${TARGET_NAME} PRIVATE ai_license)
    endif()

    # 调用方显式追加的额外依赖（如 agface_common 等静态适配层）
    if(CAP_EXTRA_LIBS)
        target_link_libraries(${TARGET_NAME} PRIVATE ${CAP_EXTRA_LIBS})
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
                   "[backend=${CAP_BACKEND}] (${CAP_DESCRIPTION})")
endfunction()
