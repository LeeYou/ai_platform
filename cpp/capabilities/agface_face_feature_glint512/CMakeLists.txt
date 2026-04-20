add_capability_plugin(
    NAME         agface_face_feature_glint512
    SOURCES      agface_face_feature_glint512.cpp
    BACKEND      NCNN
    EXTRA_LIBS   agface_common
    DESCRIPTION  "agface 人脸特征提取 (NCNN Glint360K-R34 512-dim)"
    COMPANY      "agilestar.cn"
)
