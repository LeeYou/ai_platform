# =============================================================================
# FindONNXRuntime.cmake
# 查找 ONNXRuntime 库，提供导入目标 ONNXRuntime::ONNXRuntime
#
# 搜索路径优先级：
#   1. 环境变量 ONNXRUNTIME_ROOT
#   2. CMake 变量 ONNXRUNTIME_ROOT（-DONNXRUNTIME_ROOT=...）
#   3. 常见系统安装路径（/usr, /usr/local）
# =============================================================================

# 从环境变量或 CMake 变量获取根路径
set(_ORT_SEARCH_ROOTS
    $ENV{ONNXRUNTIME_ROOT}
    ${ONNXRUNTIME_ROOT}
    /usr/local
    /usr
)

# 查找头文件
find_path(ONNXRuntime_INCLUDE_DIR
    NAMES onnxruntime_cxx_api.h onnxruntime/core/session/onnxruntime_cxx_api.h
    PATHS ${_ORT_SEARCH_ROOTS}
    PATH_SUFFIXES include
    NO_DEFAULT_PATH
)
if(NOT ONNXRuntime_INCLUDE_DIR)
    find_path(ONNXRuntime_INCLUDE_DIR
        NAMES onnxruntime_cxx_api.h
        PATH_SUFFIXES include
    )
endif()

# 查找共享库
find_library(ONNXRuntime_LIBRARY
    NAMES onnxruntime
    PATHS ${_ORT_SEARCH_ROOTS}
    PATH_SUFFIXES lib lib64
    NO_DEFAULT_PATH
)
if(NOT ONNXRuntime_LIBRARY)
    find_library(ONNXRuntime_LIBRARY NAMES onnxruntime PATH_SUFFIXES lib lib64)
endif()

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(ONNXRuntime
    REQUIRED_VARS ONNXRuntime_INCLUDE_DIR ONNXRuntime_LIBRARY
)

if(ONNXRuntime_FOUND AND NOT TARGET ONNXRuntime::ONNXRuntime)
    add_library(ONNXRuntime::ONNXRuntime SHARED IMPORTED)
    set_target_properties(ONNXRuntime::ONNXRuntime PROPERTIES
        IMPORTED_LOCATION             "${ONNXRuntime_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${ONNXRuntime_INCLUDE_DIR}"
    )
    message(STATUS "Found ONNXRuntime: ${ONNXRuntime_LIBRARY}")
endif()

mark_as_advanced(ONNXRuntime_INCLUDE_DIR ONNXRuntime_LIBRARY)
