add_capability_plugin(
    NAME         agface_face_feature_residual256
    SOURCES      agface_face_feature_residual256.cpp
    BACKEND      NCNN
    EXTRA_LIBS   agface_common
    DESCRIPTION  "agface 人脸特征提取 (NCNN Residual 256-dim)"
    COMPANY      "agilestar.cn"
)
