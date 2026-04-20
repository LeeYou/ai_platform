cmake_minimum_required(VERSION 3.20)

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
option(BUILD_GPU      "兼容旧参数：能力插件会在运行时自动探测 GPU；编译期 GPU 依赖请使用 ENABLE_TENSORRT / ENABLE_CUDA_KERNELS" OFF)
option(ENABLE_TENSORRT "启用编译期 TensorRT 依赖（需要 CUDA Toolkit + TensorRT + ONNXRuntime-GPU）" OFF)
option(ENABLE_CUDA_KERNELS "启用编译期 CUDA Toolkit 依赖（例如自定义 CUDA kernels / nvcc）" OFF)
option(BUILD_JNI      "构建 JNI 接口层（libai_jni.so）" OFF)
option(BUILD_TESTS    "构建单元测试（需要 Google Test）" OFF)
option(BUILD_ALL_CAPS "构建所有能力插件" ON)

# 单独能力插件开关（BUILD_ALL_CAPS=OFF 时生效）
option(BUILD_CAP_FACE_DETECT      "构建 face_detect 能力插件" OFF)
option(BUILD_CAP_HANDWRITING_RECO "构建 handwriting_reco 能力插件" OFF)
option(BUILD_CAP_RECAPTURE_DETECT "构建 recapture_detect 能力插件" OFF)
option(BUILD_CAP_ID_CARD_CLASSIFY "构建 id_card_classify 能力插件" OFF)
option(BUILD_CAP_DESKTOP_RECAPTURE_DETECT "构建 desktop_recapture_detect 能力插件" OFF)

# agface 系列（NCNN 后端，来自旧 ai_agface 推理库迁移）
option(BUILD_ALL_AGFACE_CAPS      "构建所有 agface_* 能力插件（NCNN 后端）" OFF)
option(BUILD_CAP_AGFACE_FACE_DETECT "构建 agface_face_detect 能力插件（NCNN RetinaFace）" OFF)

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
    message(STATUS "BUILD_GPU=ON is compatibility-only; runtime GPU fallback is auto-detected by capability plugins.")
endif()

if(ENABLE_TENSORRT OR ENABLE_CUDA_KERNELS)
    include(FindCUDA)
endif()

if(ENABLE_TENSORRT)
    include(FindTensorRT)
endif()

include(FindONNXRuntime)

# ---------------------------------------------------------------------------
# 第三方依赖：nlohmann/json（header-only，已捆绑于 third_party/nlohmann/json.hpp）
# ---------------------------------------------------------------------------
if(NOT TARGET nlohmann_json::nlohmann_json)
    add_library(nlohmann_json INTERFACE)
    add_library(nlohmann_json::nlohmann_json ALIAS nlohmann_json)
    target_include_directories(nlohmann_json INTERFACE
        "${CMAKE_CURRENT_SOURCE_DIR}/third_party")
endif()

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

if(BUILD_ALL_CAPS OR BUILD_CAP_DESKTOP_RECAPTURE_DETECT)
    add_subdirectory(capabilities/desktop_recapture_detect)
endif()

# agface 系列（NCNN 后端）——注意：不纳入 BUILD_ALL_CAPS，需显式开启，
# 因为依赖 NCNN/OpenCV，避免在未配齐依赖的环境下意外失败。
set(_AGFACE_ANY_CAP_ENABLED OFF)
if(BUILD_ALL_AGFACE_CAPS OR BUILD_CAP_AGFACE_FACE_DETECT)
    set(_AGFACE_ANY_CAP_ENABLED ON)
endif()

if(_AGFACE_ANY_CAP_ENABLED
   AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/capabilities/_agface_common/CMakeLists.txt")
    add_subdirectory(capabilities/_agface_common)
endif()

if((BUILD_ALL_AGFACE_CAPS OR BUILD_CAP_AGFACE_FACE_DETECT)
   AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/capabilities/agface_face_detect/CMakeLists.txt")
    add_subdirectory(capabilities/agface_face_detect)
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
