# =============================================================================
# FindTensorRT.cmake
# 查找 TensorRT 库（仅在 BUILD_GPU=ON 时使用），提供导入目标 TensorRT::TensorRT
# =============================================================================

set(_TRT_SEARCH_ROOTS
    $ENV{TENSORRT_ROOT}
    ${TENSORRT_ROOT}
    /usr/local/tensorrt
    /usr/local/TensorRT
    /opt/tensorrt
    /usr
)

find_path(TensorRT_INCLUDE_DIR
    NAMES NvInfer.h
    PATHS ${_TRT_SEARCH_ROOTS}
    PATH_SUFFIXES include
    NO_DEFAULT_PATH
)
if(NOT TensorRT_INCLUDE_DIR)
    find_path(TensorRT_INCLUDE_DIR NAMES NvInfer.h PATH_SUFFIXES include)
endif()

find_library(TensorRT_LIBRARY
    NAMES nvinfer
    PATHS ${_TRT_SEARCH_ROOTS}
    PATH_SUFFIXES lib lib64
    NO_DEFAULT_PATH
)
if(NOT TensorRT_LIBRARY)
    find_library(TensorRT_LIBRARY NAMES nvinfer PATH_SUFFIXES lib lib64)
endif()

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(TensorRT
    REQUIRED_VARS TensorRT_INCLUDE_DIR TensorRT_LIBRARY
)

if(TensorRT_FOUND AND NOT TARGET TensorRT::TensorRT)
    add_library(TensorRT::TensorRT SHARED IMPORTED)
    set_target_properties(TensorRT::TensorRT PROPERTIES
        IMPORTED_LOCATION             "${TensorRT_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${TensorRT_INCLUDE_DIR}"
    )
    message(STATUS "Found TensorRT: ${TensorRT_LIBRARY}")
endif()

mark_as_advanced(TensorRT_INCLUDE_DIR TensorRT_LIBRARY)
