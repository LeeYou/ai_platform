cmake_minimum_required(VERSION 3.20)

# 单元测试（Google Test）
# Phase 3 起陆续添加测试用例

find_package(GTest QUIET)
if(NOT GTest_FOUND)
    message(WARNING "Google Test not found, skipping unit tests")
    return()
endif()

add_executable(test_capability_loader
    test_capability_loader.cpp
)

target_include_directories(test_capability_loader PRIVATE
    ${AI_SDK_INCLUDE_DIR}
)

target_link_libraries(test_capability_loader
    PRIVATE
        ai_runtime
        GTest::GTest
        GTest::Main
)

ai_target_apply_flags(test_capability_loader)

include(GoogleTest)
gtest_discover_tests(test_capability_loader)
