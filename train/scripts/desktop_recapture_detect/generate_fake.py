"""Template-driven fake sample synthesis for desktop recapture detection.

Uses user-provided assets:
  - desktop screenshots:        <dataset>/desktop_screen/
  - viewer blank templates:     <dataset>/pic_viewer/
  - viewer real-image templates:<dataset>/pic_viewer_temp2/
  - manual fake screenshots:    <dataset>/desktop_screen_temp/

It auto-detects a paste region, then composites random real portraits into
templates to produce realistic fake samples.

Usage (inside the train container):
    python generate_fake.py --dataset /workspace/datasets/desktop_recapture_detect/ \\
                            --config config.json

    # preview only (writes to /tmp)
    python generate_fake.py --dataset /workspace/datasets/desktop_recapture_detect/ \\
                            --preview

Migrated from LeeYou/recapture_detect (dev branch) for ai_platform integration.
"""

import argparse
import io
import json
import random
import shutil
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _load_images(folder: Path) -> List[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXTS)


def _safe_open(path: Path) -> Optional[Image.Image]:
    try:
        return Image.open(path).convert("RGB")
    except Exception:
        return None


def _longest_segment(indices: np.ndarray) -> Optional[Tuple[int, int]]:
    if len(indices) == 0:
        return None
    start = prev = int(indices[0])
    best = (start, start)
    best_len = 1
    for v in indices[1:]:
        v = int(v)
        if v == prev + 1:
            prev = v
            continue
        cur_len = prev - start + 1
        if cur_len > best_len:
            best = (start, prev)
            best_len = cur_len
        start = prev = v
    cur_len = prev - start + 1
    if cur_len > best_len:
        best = (start, prev)
    return best


def _clip_rect(x0, y0, x1, y1, w, h):
    x0 = max(0, min(x0, w - 2))
    y0 = max(0, min(y0, h - 2))
    x1 = max(x0 + 1, min(x1, w - 1))
    y1 = max(y0 + 1, min(y1, h - 1))
    return x0, y0, x1, y1


def _detect_gray_client_area(img):
    arr = np.asarray(img, dtype=np.uint8)
    h, w, _ = arr.shape
    mean = arr.mean(axis=2)
    spread = arr.max(axis=2) - arr.min(axis=2)
    mask = (mean >= 235) & (mean <= 255) & (spread <= 10)
    row_ratio = mask.mean(axis=1)
    col_ratio = mask.mean(axis=0)
    row_idx = np.where(row_ratio > 0.55)[0]
    col_idx = np.where(col_ratio > 0.55)[0]
    rs = _longest_segment(row_idx)
    cs = _longest_segment(col_idx)
    if rs is None or cs is None:
        return None
    y0, y1 = rs
    x0, x1 = cs
    rect_w, rect_h = (x1 - x0 + 1), (y1 - y0 + 1)
    if rect_w < w * 0.35 or rect_h < h * 0.30:
        return None
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    if abs(cx - w / 2) > w * 0.18 or abs(cy - h / 2) > h * 0.20:
        return None
    return int(x0), int(y0), int(rect_w), int(rect_h)


def _detect_low_edge_area(img):
    gray = img.convert("L")
    edge = gray.filter(ImageFilter.FIND_EDGES)
    arr = np.asarray(edge, dtype=np.float32)
    h, w = arr.shape
    row_score = arr.mean(axis=1)
    col_score = arr.mean(axis=0)
    row_thr = np.percentile(row_score, 58)
    col_thr = np.percentile(col_score, 58)
    row_idx = np.where(row_score <= row_thr)[0]
    col_idx = np.where(col_score <= col_thr)[0]
    rs = _longest_segment(row_idx)
    cs = _longest_segment(col_idx)
    if rs is None or cs is None:
        return None
    y0, y1 = rs
    x0, x1 = cs
    x0 = max(x0, int(w * 0.08))
    x1 = min(x1, int(w * 0.92))
    y0 = max(y0, int(h * 0.10))
    y1 = min(y1, int(h * 0.92))
    x0, y0, x1, y1 = _clip_rect(x0, y0, x1, y1, w, h)
    rect_w, rect_h = (x1 - x0 + 1), (y1 - y0 + 1)
    if rect_w < w * 0.30 or rect_h < h * 0.25:
        return None
    return int(x0), int(y0), int(rect_w), int(rect_h)


def _fallback_center_rect(img):
    w, h = img.size
    x0 = int(w * 0.12)
    y0 = int(h * 0.14)
    rw = int(w * 0.76)
    rh = int(h * 0.74)
    return x0, y0, rw, rh


def _detect_paste_rect(img, prefer_gray):
    if prefer_gray:
        rect = _detect_gray_client_area(img)
        if rect is not None:
            return rect
    rect = _detect_low_edge_area(img)
    if rect is not None:
        return rect
    return _fallback_center_rect(img)


def _fit_letterbox(src, w, h, bg=(0, 0, 0)):
    sw, sh = src.size
    scale = min(w / sw, h / sh)
    nw, nh = max(1, int(sw * scale)), max(1, int(sh * scale))
    resized = src.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (w, h), bg)
    canvas.paste(resized, ((w - nw) // 2, (h - nh) // 2))
    return canvas


def _jpeg_like(img, rng):
    if rng.random() < 0.45:
        img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(0.2, 0.9)))
    quality = rng.randint(76, 95)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    buf.seek(0)
    return Image.open(buf).convert("RGB")


def _compose_on_viewer(portrait, viewer_template, rng, prefer_gray):
    base = viewer_template.copy().convert("RGB")
    x, y, rw, rh = _detect_paste_rect(base, prefer_gray=prefer_gray)
    inset_x = int(rw * rng.uniform(0.00, 0.04))
    inset_y = int(rh * rng.uniform(0.00, 0.04))
    x += inset_x
    y += inset_y
    rw = max(20, int(rw * rng.uniform(0.92, 1.0)))
    rh = max(20, int(rh * rng.uniform(0.92, 1.0)))
    paste = _fit_letterbox(portrait, rw, rh, bg=(10, 10, 10))
    base.paste(paste, (x, y))
    return _jpeg_like(base, rng)


def _compose_on_desktop(portrait, desktop_template, rng):
    base = desktop_template.copy().convert("RGB")
    w, h = base.size
    win_w = int(w * rng.uniform(0.45, 0.78))
    win_h = int(h * rng.uniform(0.48, 0.80))
    win_x = rng.randint(int(w * 0.04), max(int(w * 0.05), w - win_w - int(w * 0.04)))
    win_y = rng.randint(int(h * 0.03), max(int(h * 0.04), h - win_h - int(h * 0.08)))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rectangle([win_x + 8, win_y + 10, win_x + win_w + 8, win_y + win_h + 10],
                 fill=(0, 0, 0, 90))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=5))
    base = Image.alpha_composite(base.convert("RGBA"), shadow).convert("RGB")
    draw = ImageDraw.Draw(base)
    title_h = max(24, int(h * 0.028))
    draw.rectangle([win_x, win_y, win_x + win_w, win_y + win_h],
                   fill=(16, 16, 16), outline=(70, 70, 70), width=1)
    draw.rectangle([win_x, win_y, win_x + win_w, win_y + title_h],
                   fill=(36, 36, 38))
    content_y = win_y + title_h
    content_h = max(10, win_h - title_h)
    paste = _fit_letterbox(portrait, win_w, content_h, bg=(0, 0, 0))
    base.paste(paste, (win_x, content_y))
    return _jpeg_like(base, rng)


def _copy_manual_fakes(manual_paths, out_dir):
    copied = 0
    for p in manual_paths:
        dst = out_dir / f"manual_{p.name}"
        if dst.exists():
            continue
        shutil.copy2(p, dst)
        copied += 1
    return copied


def _pick_mode(rng, weights, available_modes):
    names, vals = [], []
    for m in available_modes:
        names.append(m)
        vals.append(float(weights.get(m, 0.0)))
    s = sum(vals)
    if s <= 0:
        return rng.choice(names)
    vals = [v / s for v in vals]
    return rng.choices(names, weights=vals, k=1)[0]


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Generate fake desktop-screenshot samples")
    parser.add_argument(
        "--dataset",
        default="/workspace/datasets/desktop_recapture_detect/",
        help="Dataset root directory",
    )
    parser.add_argument("--config", default="config.json")
    parser.add_argument("--variants", type=int, default=None)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--clear-output", action="store_true")
    return parser.parse_args()


def main():
    args = _parse_args()

    if args.config and Path(args.config).exists():
        with open(args.config) as f:
            cfg = json.load(f)
    else:
        cfg = {}

    gen_cfg = cfg.get("generate", {})
    rng = random.Random(gen_cfg.get("seed", 42))

    dataset_root = Path(args.dataset)
    real_dir = dataset_root / "real"
    output_dir = dataset_root / "fake"

    desktop_paths = _load_images(dataset_root / "desktop_screen")
    viewer_blank_paths = _load_images(dataset_root / "pic_viewer")
    viewer_real_paths = _load_images(dataset_root / "pic_viewer_temp2")
    manual_fake_paths = _load_images(dataset_root / "desktop_screen_temp")

    real_paths = _load_images(real_dir)
    if not real_paths:
        print(f"[ERROR] No real portraits found: {real_dir}", file=sys.stderr)
        sys.exit(1)

    n_variants = args.variants or int(gen_cfg.get("variants_per_image", 2))

    available_modes = []
    if viewer_blank_paths:
        available_modes.append("viewer_blank")
    if viewer_real_paths:
        available_modes.append("viewer_real")
    if desktop_paths:
        available_modes.append("desktop")

    if not available_modes:
        print("[ERROR] No generation templates found.", file=sys.stderr)
        sys.exit(1)

    output_dir.mkdir(parents=True, exist_ok=True)

    if args.clear_output or gen_cfg.get("clear_output", False):
        for p in output_dir.iterdir():
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
                p.unlink()

    print(f"Real portraits     : {len(real_paths)}")
    print(f"Viewer blank tmpls : {len(viewer_blank_paths)}")
    print(f"Viewer real tmpls  : {len(viewer_real_paths)}")
    print(f"Desktop tmpls      : {len(desktop_paths)}")
    print(f"Manual fake tmpls  : {len(manual_fake_paths)}")
    print(f"Output dir         : {output_dir}")
    print(f"Variants per real  : {n_variants}")
    print(f"Modes available    : {available_modes}")

    mode_weights = gen_cfg.get("mode_weights", {})
    total_gen = 0
    failures = 0
    preview_dir = Path("/tmp")

    targets = real_paths if not args.preview else rng.sample(
        real_paths, min(6, len(real_paths)))
    for idx, rp in enumerate(targets):
        portrait = _safe_open(rp)
        if portrait is None:
            failures += 1
            continue

        loops = n_variants if not args.preview else 1
        for v in range(loops):
            mode = _pick_mode(rng, mode_weights, available_modes)
            try:
                if mode == "viewer_blank":
                    vt = _safe_open(rng.choice(viewer_blank_paths))
                    if vt is None:
                        failures += 1
                        continue
                    out = _compose_on_viewer(portrait, vt, rng, prefer_gray=True)
                elif mode == "viewer_real":
                    vt = _safe_open(rng.choice(viewer_real_paths))
                    if vt is None:
                        failures += 1
                        continue
                    out = _compose_on_viewer(portrait, vt, rng, prefer_gray=False)
                else:
                    dt = _safe_open(rng.choice(desktop_paths))
                    if dt is None:
                        failures += 1
                        continue
                    out = _compose_on_desktop(portrait, dt, rng)

                name = f"{rp.stem}_fake_{mode}_{v}.jpg"
                dst = (preview_dir if args.preview else output_dir) / name
                out.save(dst, quality=92)
                total_gen += 1
            except Exception:
                failures += 1

        if (idx + 1) % 50 == 0 or (idx + 1) == len(targets):
            print(f"Progress: {idx + 1}/{len(targets)} portraits processed")

    copied_manual = 0
    if gen_cfg.get("include_manual_fake", True) and not args.preview:
        copied_manual = _copy_manual_fakes(manual_fake_paths, output_dir)

    if args.preview:
        print("\nPreview generation finished. See /tmp/*_fake_*.jpg")
        return

    print(f"\nGeneration complete:")
    print(f"  Auto generated  : {total_gen}")
    print(f"  Manual copied   : {copied_manual}")
    print(f"  Failures        : {failures}")
    print(f"  Final fake size : {len(_load_images(output_dir))}")


if __name__ == "__main__":
    main()
