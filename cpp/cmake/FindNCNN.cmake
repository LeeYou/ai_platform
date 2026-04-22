# =============================================================================
# FindNCNN.cmake
# 查找 NCNN 推理库，提供导入目标 NCNN::NCNN
#
# 搜索路径优先级（由上到下）：
#   1. cpp/third_party/ncnn/ 子模块（源码 add_subdirectory，便于版本锁定）
#   2. find_package(ncnn CONFIG)：NCNN 官方 cmake 配置（apt libncnn-dev 或自编译
#      `make install` 后提供）
#   3. 环境变量 NCNN_ROOT / CMake 变量 NCNN_ROOT：自定义二进制发行
#   4. 常见系统安装路径（/usr, /usr/local）
#
# 使用方式（在能力插件 CMakeLists 里）：
#   target_link_libraries(<plugin> PRIVATE NCNN::NCNN)
#
# 可以通过 AGFACE_NCNN_REQUIRED=ON 强制必需；否则不找到时仅发出 STATUS，
# 由调用方决定是否跳过该能力插件的构建。
# =============================================================================

if(TARGET NCNN::NCNN)
    return()
endif()

# ----------------------------------------------------------------------------
# Source 1: vendored submodule at cpp/third_party/ncnn
# ----------------------------------------------------------------------------
set(_NCNN_VENDORED_DIR "${CMAKE_SOURCE_DIR}/third_party/ncnn")
if(EXISTS "${_NCNN_VENDORED_DIR}/CMakeLists.txt" AND NOT NCNN_DISABLE_VENDORED)
    message(STATUS "FindNCNN: using vendored source at ${_NCNN_VENDORED_DIR}")

    # 关闭 NCNN 内部不需要的特性（CPU-only，最小构建面）
    set(NCNN_VULKAN         OFF CACHE BOOL "" FORCE)
    set(NCNN_PYTHON         OFF CACHE BOOL "" FORCE)
    set(NCNN_BUILD_TESTS    OFF CACHE BOOL "" FORCE)
    set(NCNN_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
    set(NCNN_BUILD_BENCHMARK OFF CACHE BOOL "" FORCE)
    set(NCNN_BUILD_TOOLS    OFF CACHE BOOL "" FORCE)
    set(NCNN_INSTALL_SDK    OFF CACHE BOOL "" FORCE)
    set(NCNN_SHARED_LIB     OFF CACHE BOOL "" FORCE)  # 静态链接到能力插件 SO
    set(NCNN_OPENMP         ${USE_OPENMP} CACHE BOOL "" FORCE)

    add_subdirectory("${_NCNN_VENDORED_DIR}" third_party_ncnn EXCLUDE_FROM_ALL)

    if(TARGET ncnn)
        set(_NCNN_VENDORED_INCLUDE_ROOT "${CMAKE_BINARY_DIR}/ncnn_vendored_include")
        file(MAKE_DIRECTORY "${_NCNN_VENDORED_INCLUDE_ROOT}")
        if(NOT EXISTS "${_NCNN_VENDORED_INCLUDE_ROOT}/ncnn")
            file(CREATE_LINK
                "${_NCNN_VENDORED_DIR}/src"
                "${_NCNN_VENDORED_INCLUDE_ROOT}/ncnn"
                SYMBOLIC
                COPY_ON_ERROR
            )
        endif()
        set_property(TARGET ncnn APPEND PROPERTY
            INTERFACE_INCLUDE_DIRECTORIES "${_NCNN_VENDORED_INCLUDE_ROOT}")
        add_library(NCNN::NCNN ALIAS ncnn)
        set(NCNN_FOUND TRUE)
        message(STATUS "FindNCNN: configured NCNN::NCNN from vendored source")
        return()
    else()
        message(WARNING "FindNCNN: vendored ncnn directory present but target 'ncnn' not created")
    endif()
endif()

# ----------------------------------------------------------------------------
# Source 2: official find_package(ncnn CONFIG) — apt libncnn-dev or make install
# ----------------------------------------------------------------------------
find_package(ncnn CONFIG QUIET)
if(ncnn_FOUND AND TARGET ncnn)
    add_library(NCNN::NCNN ALIAS ncnn)
    set(NCNN_FOUND TRUE)
    message(STATUS "FindNCNN: using ncnnConfig.cmake (system-installed)")
    return()
endif()

# ----------------------------------------------------------------------------
# Source 3/4: manual find_path + find_library
# ----------------------------------------------------------------------------
set(_NCNN_SEARCH_ROOTS
    $ENV{NCNN_ROOT}
    ${NCNN_ROOT}
    /usr/local
    /usr
)

find_path(NCNN_INCLUDE_DIR
    NAMES ncnn/net.h net.h
    PATHS ${_NCNN_SEARCH_ROOTS}
    PATH_SUFFIXES include include/ncnn
    NO_DEFAULT_PATH
)
if(NOT NCNN_INCLUDE_DIR)
    find_path(NCNN_INCLUDE_DIR NAMES ncnn/net.h PATH_SUFFIXES include)
endif()

find_library(NCNN_LIBRARY
    NAMES ncnn
    PATHS ${_NCNN_SEARCH_ROOTS}
    PATH_SUFFIXES lib lib64 lib/x86_64-linux-gnu
    NO_DEFAULT_PATH
)
if(NOT NCNN_LIBRARY)
    find_library(NCNN_LIBRARY NAMES ncnn PATH_SUFFIXES lib lib64 lib/x86_64-linux-gnu)
endif()

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(NCNN
    REQUIRED_VARS NCNN_INCLUDE_DIR NCNN_LIBRARY
)

if(NCNN_FOUND AND NOT TARGET NCNN::NCNN)
    # net.h 往往在 <prefix>/include/ncnn/net.h；若 NCNN_INCLUDE_DIR 命中的是
    # <prefix>/include/ncnn，再向上回退一级以便 #include <ncnn/net.h>
    get_filename_component(_ncnn_inc_parent "${NCNN_INCLUDE_DIR}" DIRECTORY)
    if(EXISTS "${_ncnn_inc_parent}/ncnn/net.h")
        set(NCNN_INCLUDE_DIRS "${_ncnn_inc_parent}" "${NCNN_INCLUDE_DIR}")
    else()
        set(NCNN_INCLUDE_DIRS "${NCNN_INCLUDE_DIR}")
    endif()

    add_library(NCNN::NCNN UNKNOWN IMPORTED)
    set_target_properties(NCNN::NCNN PROPERTIES
        IMPORTED_LOCATION             "${NCNN_LIBRARY}"
        INTERFACE_INCLUDE_DIRECTORIES "${NCNN_INCLUDE_DIRS}"
    )
    # NCNN 默认启用 OpenMP，链接时需带上
    if(USE_OPENMP)
        find_package(OpenMP QUIET)
        if(OpenMP_CXX_FOUND)
            set_property(TARGET NCNN::NCNN APPEND PROPERTY
                INTERFACE_LINK_LIBRARIES OpenMP::OpenMP_CXX)
        endif()
    endif()
    message(STATUS "Found NCNN: ${NCNN_LIBRARY}")
endif()

mark_as_advanced(NCNN_INCLUDE_DIR NCNN_LIBRARY)
