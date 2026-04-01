cmake_minimum_required(VERSION 3.20)

# Runtime 库（libai_runtime.so）
# 职责：动态加载能力 SO、管理实例池、License 校验缓存、模型包验证
#
# 安全编译选项：
#   -DTRUSTED_PUBKEY_SHA256=<hex>   将客户公钥的 SHA-256 指纹硬编码进 SO，
#                                    防止攻击者替换公钥+伪造授权文件。
#   每个客户交付前必须用该客户公钥的指纹重新编译 SO。

# 可选：传入受信公钥 SHA-256 指纹（64 位十六进制）
set(TRUSTED_PUBKEY_SHA256 "" CACHE STRING
    "SHA-256 fingerprint of the trusted public key PEM (hex, lowercase). \
     When set, the runtime SO will reject any pubkey.pem that does not match.")

add_library(ai_runtime SHARED
    ai_runtime.cpp
    capability_loader.cpp
    instance_pool.cpp
    license_checker.cpp
    model_loader.cpp
)

target_include_directories(ai_runtime
    PUBLIC
        ${AI_SDK_INCLUDE_DIR}
        ${CMAKE_CURRENT_SOURCE_DIR}/include
)

set_target_properties(ai_runtime PROPERTIES
    OUTPUT_NAME       ai_runtime
    VERSION           ${PROJECT_VERSION}
    SOVERSION         ${PROJECT_VERSION_MAJOR}
    CXX_VISIBILITY_PRESET     hidden
    VISIBILITY_INLINES_HIDDEN ON
)

# Linux：-ldl 用于 dlopen/dlsym/dlclose
if(UNIX AND NOT APPLE)
    target_link_libraries(ai_runtime PRIVATE dl)
endif()

# OpenSSL for SHA-256 in model_loader (optional but preferred)
find_package(OpenSSL QUIET)
if(OpenSSL_FOUND)
    target_link_libraries(ai_runtime PRIVATE OpenSSL::Crypto)
    target_compile_definitions(ai_runtime PRIVATE AI_HAVE_OPENSSL=1)
endif()

ai_target_apply_flags(ai_runtime)

# Inject trusted public key fingerprint into the SO binary
if(NOT "${TRUSTED_PUBKEY_SHA256}" STREQUAL "")
    target_compile_definitions(ai_runtime PRIVATE
        TRUSTED_PUBKEY_SHA256="${TRUSTED_PUBKEY_SHA256}")
    message(STATUS "Runtime SO: TRUSTED_PUBKEY_SHA256 = ${TRUSTED_PUBKEY_SHA256}")
else()
    message(WARNING "Runtime SO: TRUSTED_PUBKEY_SHA256 is NOT set — "
                    "public key fingerprint verification DISABLED (dev/test only)")
endif()

install(TARGETS ai_runtime
    LIBRARY DESTINATION lib
    RUNTIME DESTINATION lib
)
install(FILES include/ai_runtime_impl.h DESTINATION include/agilestar)
