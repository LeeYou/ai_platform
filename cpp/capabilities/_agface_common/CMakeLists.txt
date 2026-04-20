# =============================================================================
# _agface_common
# 共享静态库：供 agface_* 能力插件复用
#   - NCNN 会话 + 实例池（移植自旧 ai_agface/infra）
#   - manifest.json 解析
#   - AiImage ↔ cv::Mat ↔ ncnn::Mat 转换
#   - 统一 JSON 结果填充 + AiFreeResult 释放约定
#
# 目标：agface_common（STATIC，带 -fPIC，供每个 agface_* 能力插件 PRIVATE 链接）
# 不导出符号、不安装 —— 仅在构建期对能力插件可见。
# =============================================================================

if(TARGET agface_common)
    return()
endif()

add_library(agface_common STATIC
    src/manifest.cpp
    src/image_utils.cpp
    src/json_result.cpp
)

set_target_properties(agface_common PROPERTIES
    POSITION_INDEPENDENT_CODE ON
    C_VISIBILITY_PRESET   hidden
    CXX_VISIBILITY_PRESET hidden
    VISIBILITY_INLINES_HIDDEN ON
)

target_include_directories(agface_common
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
    PRIVATE
        ${AI_SDK_INCLUDE_DIR}
)

# 依赖：nlohmann/json（header-only，通过 cpp/third_party/nlohmann/json.hpp 提供）
if(TARGET nlohmann_json::nlohmann_json)
    target_link_libraries(agface_common PUBLIC nlohmann_json::nlohmann_json)
endif()

# NCNN + OpenCV（由 FindNCNN / find_package(OpenCV) 提供，作为 PUBLIC 传递给能力插件）
if(NOT TARGET NCNN::NCNN)
    include(FindNCNN)
endif()
if(TARGET NCNN::NCNN)
    target_link_libraries(agface_common PUBLIC NCNN::NCNN)
else()
    message(FATAL_ERROR "agface_common requires NCNN::NCNN (install libncnn-dev, set NCNN_ROOT, or vendor cpp/third_party/ncnn)")
endif()

find_package(OpenCV REQUIRED COMPONENTS core imgproc imgcodecs)
target_include_directories(agface_common PUBLIC ${OpenCV_INCLUDE_DIRS})
target_link_libraries(agface_common PUBLIC ${OpenCV_LIBS})

# 统一编译选项
if(COMMAND ai_target_apply_flags)
    ai_target_apply_flags(agface_common)
endif()

message(STATUS "agface_common: configured (STATIC, PIC, NCNN + OpenCV)")
