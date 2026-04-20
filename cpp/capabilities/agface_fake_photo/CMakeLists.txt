add_capability_plugin(
    NAME         agface_fake_photo
    SOURCES      agface_fake_photo.cpp
    BACKEND      NCNN
    EXTRA_LIBS   agface_common
    DESCRIPTION  "agface 翻拍照检测（NCNN legacy fake photo）"
    COMPANY      "agilestar.cn"
)
