# =============================================================================
# agface_face_detect
# NCNN RetinaFace（SSD 头）多人脸检测能力插件
# 迁移自旧 ai_agface/src/ai_modules/face_detect/face_detect_retina.*
# =============================================================================

add_capability_plugin(
    NAME         agface_face_detect
    SOURCES      agface_face_detect.cpp
    HEADERS      agface_face_detect.h
    BACKEND      NCNN
    EXTRA_LIBS   agface_common
    DESCRIPTION  "agface 人脸检测（NCNN RetinaFace/SSD）"
    COMPANY      "agilestar.cn"
)
