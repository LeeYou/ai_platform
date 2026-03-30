#!/usr/bin/env python3
"""Convert WIDER FACE dataset to YOLO format for YOLOv8 training.

Reads the standard WIDER FACE annotation files and produces a directory
tree compatible with Ultralytics YOLOv8:

    <output>/
        images/train/   – training images
        images/val/     – validation images
        labels/train/   – one .txt per training image
        labels/val/     – one .txt per validation image
        data.yaml       – dataset descriptor

Two classes are emitted:
    0  face            (occlusion == 0 in the source annotation)
    1  occluded_face   (occlusion >= 1)

Usage
-----
    python convert_widerface.py \\
        --widerface-root /data/WIDER_FACE \\
        --output /data/widerface_yolo

The expected layout under --widerface-root is:

    WIDER_train/images/          – training JPEGs
    WIDER_val/images/            – validation JPEGs
    wider_face_split/
        wider_face_train_bbx_gt.txt
        wider_face_val_bbx_gt.txt
"""

import argparse
import os
import shutil
import sys

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# -------------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------------

_CLASSES = {0: "face", 1: "occluded_face"}

_SPLITS = {
    "train": {
        "annotation": os.path.join(
            "wider_face_split", "wider_face_train_bbx_gt.txt",
        ),
        "image_root": os.path.join("WIDER_train", "images"),
    },
    "val": {
        "annotation": os.path.join(
            "wider_face_split", "wider_face_val_bbx_gt.txt",
        ),
        "image_root": os.path.join("WIDER_val", "images"),
    },
}

_MIN_BOX_PX = 1  # skip boxes smaller than this in either dimension


# -------------------------------------------------------------------------
# Argument parsing
# -------------------------------------------------------------------------

def _parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Convert WIDER FACE dataset to YOLO format.",
    )
    parser.add_argument(
        "--widerface-root",
        required=True,
        help="Path to the extracted WIDER FACE root directory.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to the output YOLO-format dataset directory.",
    )
    return parser.parse_args()


# -------------------------------------------------------------------------
# Annotation parser
# -------------------------------------------------------------------------

def _parse_annotation_file(path):
    """Yield (image_path, list_of_boxes) from a WIDER FACE annotation file.

    Each box is a dict with keys: x1, y1, w, h, occlusion.
    """
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()

    idx = 0
    total = len(lines)
    while idx < total:
        image_path = lines[idx].strip()
        idx += 1
        if idx >= total:
            break

        num_faces = int(lines[idx].strip())
        idx += 1

        boxes = []
        # WIDER FACE uses 0 faces with a single dummy line of all zeros.
        rows_to_read = max(num_faces, 1) if num_faces == 0 else num_faces
        for _ in range(rows_to_read):
            if idx >= total:
                break
            parts = lines[idx].strip().split()
            idx += 1
            if len(parts) < 10:
                continue
            if num_faces == 0:
                # Dummy row for images with zero annotated faces – skip.
                continue
            x1, y1, w, h = (int(parts[i]) for i in range(4))
            occlusion = int(parts[8])
            boxes.append({
                "x1": x1, "y1": y1, "w": w, "h": h,
                "occlusion": occlusion,
            })

        yield image_path, boxes


# -------------------------------------------------------------------------
# Conversion helpers
# -------------------------------------------------------------------------

def _wider_to_yolo(box, img_w, img_h):
    """Convert a single WIDER FACE box to YOLO format.

    Returns (class_id, cx, cy, bw, bh) with normalised coordinates,
    or *None* if the box should be skipped.
    """
    x1, y1, w, h = box["x1"], box["y1"], box["w"], box["h"]

    if w < _MIN_BOX_PX or h < _MIN_BOX_PX:
        return None

    # Clamp to image boundaries.
    x1 = max(0, x1)
    y1 = max(0, y1)
    x2 = min(img_w, x1 + w)
    y2 = min(img_h, y1 + h)
    w = x2 - x1
    h = y2 - y1
    if w < _MIN_BOX_PX or h < _MIN_BOX_PX:
        return None

    cx = (x1 + w / 2.0) / img_w
    cy = (y1 + h / 2.0) / img_h
    bw = w / img_w
    bh = h / img_h

    class_id = 1 if box["occlusion"] >= 1 else 0
    return class_id, cx, cy, bw, bh


def _image_dimensions(path):
    """Return (width, height) for an image without heavy dependencies."""
    try:
        import cv2
        img = cv2.imread(path)
        if img is None:
            return None
        h, w = img.shape[:2]
        return w, h
    except ImportError:
        pass

    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.size  # (width, height)
    except ImportError:
        pass

    print(
        "[ERROR] Neither OpenCV nor Pillow is available to read image "
        "dimensions.  Install one of them:\n"
        "        pip install opencv-python-headless   OR\n"
        "        pip install Pillow",
        file=sys.stderr,
    )
    sys.exit(1)


# -------------------------------------------------------------------------
# Per-split conversion
# -------------------------------------------------------------------------

def _convert_split(widerface_root, output_root, split_name):
    """Convert one split (train or val) and return summary counters."""
    cfg = _SPLITS[split_name]
    ann_path = os.path.join(widerface_root, cfg["annotation"])
    img_root = os.path.join(widerface_root, cfg["image_root"])

    if not os.path.isfile(ann_path):
        print(
            f"[WARN] Annotation file not found, skipping {split_name}: "
            f"{ann_path}",
            file=sys.stderr,
        )
        return 0, 0, 0

    out_img_dir = os.path.join(output_root, "images", split_name)
    out_lbl_dir = os.path.join(output_root, "labels", split_name)
    os.makedirs(out_img_dir, exist_ok=True)
    os.makedirs(out_lbl_dir, exist_ok=True)

    entries = list(_parse_annotation_file(ann_path))
    iterator = tqdm(entries, desc=f"[{split_name}]") if tqdm else entries

    n_images = 0
    n_boxes = 0
    n_skipped = 0

    for rel_path, boxes in iterator:
        src_img = os.path.join(img_root, rel_path)
        if not os.path.isfile(src_img):
            print(
                f"[WARN] Image not found, skipping: {src_img}",
                file=sys.stderr,
            )
            n_skipped += 1
            continue

        dims = _image_dimensions(src_img)
        if dims is None:
            print(
                f"[WARN] Cannot read image, skipping: {src_img}",
                file=sys.stderr,
            )
            n_skipped += 1
            continue

        img_w, img_h = dims

        # Flatten sub-folder structure: 0--Parade/0_Parade_xxx.jpg -> flat.
        base_name = os.path.basename(rel_path)
        dst_img = os.path.join(out_img_dir, base_name)
        stem, _ = os.path.splitext(base_name)
        dst_lbl = os.path.join(out_lbl_dir, stem + ".txt")

        shutil.copy2(src_img, dst_img)

        yolo_lines = []
        for box in boxes:
            result = _wider_to_yolo(box, img_w, img_h)
            if result is None:
                continue
            cls, cx, cy, bw, bh = result
            yolo_lines.append(f"{cls} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}")

        with open(dst_lbl, "w", encoding="utf-8") as fh:
            fh.write("\n".join(yolo_lines))
            if yolo_lines:
                fh.write("\n")

        n_images += 1
        n_boxes += len(yolo_lines)

    return n_images, n_boxes, n_skipped


# -------------------------------------------------------------------------
# data.yaml generation
# -------------------------------------------------------------------------

def _write_data_yaml(output_root):
    """Write a YOLOv8-compatible data.yaml."""
    yaml_path = os.path.join(output_root, "data.yaml")
    names_block = "\n".join(
        f"  {cid}: {name}" for cid, name in sorted(_CLASSES.items())
    )
    content = (
        f"path: {os.path.abspath(output_root)}\n"
        f"train: images/train\n"
        f"val: images/val\n"
        f"\n"
        f"nc: {len(_CLASSES)}\n"
        f"names:\n"
        f"{names_block}\n"
    )
    with open(yaml_path, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"[INFO] data.yaml written to {yaml_path}", flush=True)


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

def main():
    args = _parse_args()
    widerface_root = args.widerface_root
    output_root = args.output

    if not os.path.isdir(widerface_root):
        print(
            f"[ERROR] WIDER FACE root not found: {widerface_root}",
            file=sys.stderr,
        )
        sys.exit(1)

    os.makedirs(output_root, exist_ok=True)

    total_images = 0
    total_boxes = 0
    total_skipped = 0

    for split in ("train", "val"):
        print(f"[INFO] Converting {split} split ...", flush=True)
        n_img, n_box, n_skip = _convert_split(
            widerface_root, output_root, split,
        )
        total_images += n_img
        total_boxes += n_box
        total_skipped += n_skip
        print(
            f"[INFO] {split}: {n_img} images, {n_box} boxes "
            f"({n_skip} skipped)",
            flush=True,
        )

    _write_data_yaml(output_root)

    print(
        f"[DONE] Converted {total_images} images with {total_boxes} boxes "
        f"({total_skipped} skipped).",
        flush=True,
    )


if __name__ == "__main__":
    main()
