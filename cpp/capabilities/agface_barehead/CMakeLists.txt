add_capability_plugin(
    NAME         agface_barehead
    SOURCES      agface_barehead.cpp
    BACKEND      NCNN
    EXTRA_LIBS   agface_common
    DESCRIPTION  "agface 裸头检测（NCNN legacy barehead）"
    COMPANY      "agilestar.cn"
)
