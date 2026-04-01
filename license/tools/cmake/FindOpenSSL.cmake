# FindOpenSSL.cmake
# Tries to locate OpenSSL 3.x on the system.
# Falls back to pkg-config if the built-in CMake module finds an older version.
#
# Exported targets (same as the built-in module):
#   OpenSSL::SSL
#   OpenSSL::Crypto

if(NOT OpenSSL_FOUND)
    # Temporarily remove this directory from the module path to avoid
    # infinite recursion when delegating to the built-in CMake module.
    set(_saved_module_path "${CMAKE_MODULE_PATH}")
    list(REMOVE_ITEM CMAKE_MODULE_PATH "${CMAKE_CURRENT_LIST_DIR}")
    find_package(OpenSSL QUIET)
    set(CMAKE_MODULE_PATH "${_saved_module_path}")

    if(OpenSSL_FOUND AND OPENSSL_VERSION VERSION_LESS "3.0")
        message(STATUS "System OpenSSL (${OPENSSL_VERSION}) is too old; trying pkg-config")
        set(OpenSSL_FOUND FALSE)
    endif()
endif()

if(NOT OpenSSL_FOUND)
    find_package(PkgConfig QUIET)
    if(PkgConfig_FOUND)
        pkg_check_modules(OPENSSL_PKG QUIET openssl>=3.0)
        if(OPENSSL_PKG_FOUND)
            set(OPENSSL_VERSION "${OPENSSL_PKG_VERSION}")
            set(OPENSSL_INCLUDE_DIR "${OPENSSL_PKG_INCLUDE_DIRS}")
            set(OPENSSL_LIBRARIES "${OPENSSL_PKG_LIBRARIES}")

            if(NOT TARGET OpenSSL::Crypto)
                add_library(OpenSSL::Crypto INTERFACE IMPORTED)
                target_include_directories(OpenSSL::Crypto INTERFACE ${OPENSSL_PKG_INCLUDE_DIRS})
                target_link_libraries(OpenSSL::Crypto INTERFACE ${OPENSSL_PKG_LINK_LIBRARIES})
            endif()

            if(NOT TARGET OpenSSL::SSL)
                add_library(OpenSSL::SSL INTERFACE IMPORTED)
                target_include_directories(OpenSSL::SSL INTERFACE ${OPENSSL_PKG_INCLUDE_DIRS})
                target_link_libraries(OpenSSL::SSL INTERFACE ${OPENSSL_PKG_LINK_LIBRARIES})
            endif()

            set(OpenSSL_FOUND TRUE)
            message(STATUS "Found OpenSSL ${OPENSSL_VERSION} via pkg-config")
        endif()
    endif()
endif()

if(NOT OpenSSL_FOUND)
    if(OpenSSL_FIND_REQUIRED)
        message(FATAL_ERROR "Could not find OpenSSL >= 3.0")
    else()
        message(WARNING "Could not find OpenSSL >= 3.0")
    endif()
endif()
