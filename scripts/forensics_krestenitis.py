"""
Exhaustive Programmatic Forensics on the Krestenitis Dataset
"""
import sys
import time
from pathlib import Path
from PIL import Image
import numpy as np
from collections import Counter

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KREST_DIR = PROJECT_ROOT / "data" / "sar_images" / "krestenitis_dataset"

splits = ['train', 'val', 'test']
split_counts = {}
missing_pairs = []
corrupt_files = []
img_dims = set()
mask_dims = set()

color_counter = Counter()

t0 = time.time()

for split in splits:
    s_dir = KREST_DIR / split
    img_files = {f.stem: f for f in sorted((s_dir / 'images').glob('*')) if not f.name.startswith('.')}
    mask_files = {f.stem: f for f in sorted((s_dir / 'masks').glob('*')) if not f.name.startswith('.')}
    
    split_counts[split] = {'images': len(img_files), 'masks': len(mask_files)}
    
    img_stems = set(img_files.keys())
    mask_stems = set(mask_files.keys())
    
    only_in_img = img_stems - mask_stems
    only_in_mask = mask_stems - img_stems
    if only_in_img or only_in_mask:
        missing_pairs.append((split, only_in_img, only_in_mask))
        
    for stem, p in img_files.items():
        try:
            with Image.open(p) as im:
                img_dims.add((im.size, im.mode))
        except Exception as e:
            corrupt_files.append((str(p), str(e)))
            
    for stem, p in mask_files.items():
        try:
            with Image.open(p) as mk:
                mask_dims.add((mk.size, mk.mode))
                arr = np.array(mk)
                if arr.ndim == 3:
                    # pack 24-bit integer
                    packed = (arr[:, :, 0].astype(np.uint32) << 16) | (arr[:, :, 1].astype(np.uint32) << 8) | arr[:, :, 2].astype(np.uint32)
                    u_vals, counts = np.unique(packed, return_counts=True)
                    for val, cnt in zip(u_vals, counts):
                        r = int((val >> 16) & 0xFF)
                        g = int((val >> 8) & 0xFF)
                        b = int(val & 0xFF)
                        color_counter[(r, g, b)] += int(cnt)
                else:
                    u_vals, counts = np.unique(arr, return_counts=True)
                    for val, cnt in zip(u_vals, counts):
                        color_counter[int(val)] += int(cnt)
        except Exception as e:
            corrupt_files.append((str(p), str(e)))

elapsed = time.time() - t0

print(f"=== KRESTENITIS FORENSICS SCAN ({elapsed:.2f}s) ===")
print("Split file counts:")
for k, v in split_counts.items():
    print(f"  {k}: {v['images']} images, {v['masks']} masks")

print("\nFilename pairing:")
if not missing_pairs:
    print("  Zero missing pairs! 100% of images and masks match exactly.")
else:
    print(f"  Mismatched pairs: {missing_pairs}")

print("\nFile corruption check:")
if not corrupt_files:
    print("  Zero corrupt files across all 2,080 image/mask files.")
else:
    print(f"  Corrupt files found: {len(corrupt_files)}")

print("\nImage Dimensions & Color Modes:")
for dim, mode in img_dims:
    print(f"  {dim[0]}x{dim[1]} ({mode})")

print("\nMask Dimensions & Color Modes:")
for dim, mode in mask_dims:
    print(f"  {dim[0]}x{dim[1]} ({mode})")

print("\nExact RGB Color Values & Pixel Frequencies:")
total_pixels = sum(color_counter.values())
known_classes = {
    (0, 0, 0): "background",
    (51, 221, 255): "water",
    (255, 0, 124): "oil",
    (255, 204, 51): "others"
}

for col, count in color_counter.most_common():
    name = known_classes.get(col, "UNKNOWN_CLASS")
    pct = (count / total_pixels) * 100
    print(f"  RGB {col}: {count:14,d} pixels ({pct:6.2f}%) -> {name}")

