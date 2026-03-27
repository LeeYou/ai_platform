# =============================================================================
# CompilerFlags.cmake
# 统一编译选项（Google C++ 风格 + 公司定制）
# =============================================================================

# ---------------------------------------------------------------------------
# 通用警告 & 安全选项
# ---------------------------------------------------------------------------
set(AI_COMMON_COMPILE_OPTIONS
    -Wall
    -Wextra
    -Wpedantic
    -Wno-unused-parameter        # 接口实现中未使用参数很常见
    -Wno-missing-field-initializers
    -fvisibility=hidden          # 默认隐藏所有符号，只有 AI_EXPORT 标记的符号可见
    -fvisibility-inlines-hidden
)

# ---------------------------------------------------------------------------
# Release 模式：开启优化，去掉调试信息
# ---------------------------------------------------------------------------
set(AI_RELEASE_COMPILE_OPTIONS
    -O2
    -DNDEBUG
    -fstack-protector-strong
    -D_FORTIFY_SOURCE=2
)

# ---------------------------------------------------------------------------
# Debug 模式：AddressSanitizer + UBSan
# ---------------------------------------------------------------------------
set(AI_DEBUG_COMPILE_OPTIONS
    -O0
    -g3
    -fsanitize=address,undefined
    -fno-omit-frame-pointer
)

set(AI_DEBUG_LINK_OPTIONS
    -fsanitize=address,undefined
)

# ---------------------------------------------------------------------------
# 应用到所有目标的工具函数
# ---------------------------------------------------------------------------
function(ai_target_apply_flags target)
    target_compile_options(${target} PRIVATE
        ${AI_COMMON_COMPILE_OPTIONS}
        $<$<CONFIG:Release>:${AI_RELEASE_COMPILE_OPTIONS}>
        $<$<CONFIG:Debug>:${AI_DEBUG_COMPILE_OPTIONS}>
    )

    target_link_options(${target} PRIVATE
        $<$<CONFIG:Debug>:${AI_DEBUG_LINK_OPTIONS}>
    )

    # 确保代码以 UTF-8 处理（Linux GCC 默认，但显式声明）
    target_compile_options(${target} PRIVATE -finput-charset=UTF-8 -fexec-charset=UTF-8)
endfunction()

# ---------------------------------------------------------------------------
# Windows MSVC 编译选项覆盖
# ---------------------------------------------------------------------------
if(MSVC)
    set(AI_COMMON_COMPILE_OPTIONS
        /W4
        /WX-              # 警告不当错误，生产后期可改为 /WX
        /utf-8            # UTF-8 源文件编码
        /wd4100           # 与 GCC -Wno-unused-parameter 等价
        /wd4505           # 未使用的本地函数
    )

    function(ai_target_apply_flags target)
        target_compile_options(${target} PRIVATE
            ${AI_COMMON_COMPILE_OPTIONS}
            $<$<CONFIG:Release>:/O2 /DNDEBUG>
            $<$<CONFIG:Debug>:/Od /Zi /RTC1>
        )
    endfunction()
endif()
