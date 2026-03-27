cmake_minimum_required(VERSION 3.26)

project(ai_platform
    VERSION 1.0.0
    DESCRIPTION "Agile Star AI Platform - C++ Runtime & Capability Plugins"
    LANGUAGES C CXX
)

# ---------------------------------------------------------------------------
# C++ 标准
# ---------------------------------------------------------------------------
set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ---------------------------------------------------------------------------
# 顶层构建选项
# ---------------------------------------------------------------------------
option(BUILD_GPU      "启用 GPU 推理（需要 CUDA + ONNXRuntime-GPU / TensorRT）" OFF)
option(BUILD_JNI      "构建 JNI 接口层（libai_jni.so）" OFF)
option(BUILD_TESTS    "构建单元测试（需要 Google Test）" OFF)
option(BUILD_ALL_CAPS "构建所有能力插件" ON)

# 单独能力插件开关（BUILD_ALL_CAPS=OFF 时生效）
option(BUILD_CAP_FACE_DETECT      "构建 face_detect 能力插件" OFF)
option(BUILD_CAP_HANDWRITING_RECO "构建 handwriting_reco 能力插件" OFF)
option(BUILD_CAP_RECAPTURE_DETECT "构建 recapture_detect 能力插件" OFF)
option(BUILD_CAP_ID_CARD_CLASSIFY "构建 id_card_classify 能力插件" OFF)

# ---------------------------------------------------------------------------
# 输出目录
# ---------------------------------------------------------------------------
set(CMAKE_ARCHIVE_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_LIBRARY_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/lib)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY ${CMAKE_BINARY_DIR}/bin)

# ---------------------------------------------------------------------------
# CMake 模块路径
# ---------------------------------------------------------------------------
list(APPEND CMAKE_MODULE_PATH ${CMAKE_CURRENT_SOURCE_DIR}/cmake)

# ---------------------------------------------------------------------------
# 公共头文件路径（SDK）
# ---------------------------------------------------------------------------
set(AI_SDK_INCLUDE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/sdk)

# ---------------------------------------------------------------------------
# 加载 cmake 模块
# ---------------------------------------------------------------------------
include(CompilerFlags)
include(CapabilityPlugin)

if(BUILD_GPU)
    include(FindCUDA)
    include(FindTensorRT)
endif()

include(FindONNXRuntime)

# ---------------------------------------------------------------------------
# 子工程
# ---------------------------------------------------------------------------

# Runtime 库（libai_runtime.so）
add_subdirectory(runtime)

# 能力插件
if(BUILD_ALL_CAPS OR BUILD_CAP_FACE_DETECT)
    add_subdirectory(capabilities/face_detect)
endif()

if(BUILD_ALL_CAPS OR BUILD_CAP_HANDWRITING_RECO)
    add_subdirectory(capabilities/handwriting_reco)
endif()

if(BUILD_ALL_CAPS OR BUILD_CAP_RECAPTURE_DETECT)
    add_subdirectory(capabilities/recapture_detect)
endif()

if(BUILD_ALL_CAPS OR BUILD_CAP_ID_CARD_CLASSIFY)
    add_subdirectory(capabilities/id_card_classify)
endif()

# JNI 接口层
if(BUILD_JNI)
    add_subdirectory(jni)
endif()

# 单元测试
if(BUILD_TESTS)
    enable_testing()
    add_subdirectory(tests/unit)
endif()

# ---------------------------------------------------------------------------
# 安装：公共 SDK 头文件
# ---------------------------------------------------------------------------
install(FILES
    sdk/ai_types.h
    sdk/ai_capability.h
    sdk/ai_runtime.h
    DESTINATION include/agilestar
)
