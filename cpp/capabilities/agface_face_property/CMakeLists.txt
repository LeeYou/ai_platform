add_capability_plugin(
    NAME         agface_face_property
    SOURCES      agface_face_property.cpp
    BACKEND      NCNN
    EXTRA_LIBS   agface_common
    DESCRIPTION  "agface 人脸属性检测（NCNN legacy face_property）"
    COMPANY      "agilestar.cn"
)
