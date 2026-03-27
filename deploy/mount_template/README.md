# 宿主机统一挂载目录模板

本目录提供宿主机 `/data/ai_platform/` 目录结构的创建脚本和说明，
所有 AI Platform 容器通过挂载此目录下的子目录共享数据。

---

## 目录结构

```
/data/ai_platform/
├── datasets/          # 训练数据集（只读挂载到训练容器）
│   ├── face_detect/
│   ├── handwriting_reco/
│   ├── recapture_detect/
│   └── id_card_classify/
├── models/            # 标准模型包（训练容器写入，其余只读）
│   └── <capability>/
│       ├── v1.0.0/
│       │   ├── model.onnx
│       │   ├── manifest.json
│       │   ├── preprocess.json
│       │   ├── labels.json
│       │   └── checksum.sha256
│       └── current -> v1.0.0   # 符号链接，指向当前生效版本
├── libs/              # 编译产物 SO/DLL（编译容器写入，生产只读）
│   ├── linux_x86_64/
│   │   └── <capability>/
│   │       ├── v1.0.0/
│   │       │   ├── lib<capability>.so
│   │       │   └── build_info.json
│   │       └── current -> v1.0.0
│   ├── linux_aarch64/
│   └── windows_x86_64/
│       └── <capability>/
│           └── v1.0.0/
│               └── <capability>.dll
├── licenses/          # 授权文件（授权系统生成，生产容器只读）
│   └── <customer_id>/
│       └── license.bin
├── output/            # 最终交付产物归档
│   └── <version>/
└── logs/              # 各容器日志落地目录
    ├── train/
    ├── test/
    ├── build/
    ├── license/
    └── prod/
```

---

## 快速初始化脚本

```bash
# 以 root 或 sudo 执行
bash /path/to/ai_platform/deploy/mount_template/init_host_dirs.sh
```

---

## 注意事项

- `licenses/` 目录权限建议设为 `700`（仅 root 可读），防止未授权访问
- `datasets/` 目录可设为只读（`chmod a-w`），防止训练进程误写
- `models/current` 和 `libs/current` 为符号链接，**不要**将其替换为真实目录
- 更新模型或 SO 时，先将新版本写入带版本号的子目录，再更新 `current` 符号链接
