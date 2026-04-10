# =============================================================================
# FindCUDA.cmake（包装器）
# 优先使用 CMake 3.17+ 内置的 FindCUDAToolkit，回退到旧 FindCUDA
# =============================================================================

if(CMAKE_VERSION VERSION_GREATER_EQUAL "3.17")
    find_package(CUDAToolkit QUIET)
    if(CUDAToolkit_FOUND)
        message(STATUS "Found CUDA Toolkit: ${CUDAToolkit_VERSION} "
                       "(${CUDAToolkit_LIBRARY_DIR})")
    else()
        message(FATAL_ERROR
            "CUDA Toolkit is required for the requested compile-time GPU features. "
            "Use a GPU builder image with nvcc and /usr/local/cuda available."
        )
    endif()
else()
    find_package(CUDA QUIET)
    if(CUDA_FOUND)
        message(STATUS "Found CUDA: ${CUDA_VERSION}")
    else()
        message(FATAL_ERROR
            "CUDA Toolkit is required for the requested compile-time GPU features. "
            "Use a GPU builder image with CUDA installed."
        )
    endif()
endif()
