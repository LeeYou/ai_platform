add_executable(license_tool main.cpp)

target_link_libraries(license_tool
    PRIVATE
        ai_license_core
        OpenSSL::SSL
        OpenSSL::Crypto
)

target_compile_options(license_tool PRIVATE -Wall -Wextra)

install(TARGETS license_tool DESTINATION bin)
