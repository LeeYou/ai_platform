add_library(ai_license_core STATIC
    fingerprint.cpp
    rsa_utils.cpp
    license_io.cpp
    license_core.cpp
)

target_include_directories(ai_license_core
    PUBLIC
        ${CMAKE_CURRENT_SOURCE_DIR}/include
    PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
)

target_link_libraries(ai_license_core
    PUBLIC
        OpenSSL::Crypto
)

target_compile_options(ai_license_core PRIVATE -Wall -Wextra)
