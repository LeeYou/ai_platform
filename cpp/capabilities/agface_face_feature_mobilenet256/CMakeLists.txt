add_capability_plugin(
    NAME         agface_face_feature_mobilenet256
    SOURCES      agface_face_feature_mobilenet256.cpp
    BACKEND      NCNN
    EXTRA_LIBS   agface_common
    DESCRIPTION  "agface 人脸特征提取 (NCNN MobileFaceNet 256-dim, output=fc1)"
    COMPANY      "agilestar.cn"
)
