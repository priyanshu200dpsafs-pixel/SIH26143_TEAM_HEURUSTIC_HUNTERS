"""
Visualize sample SAR imagery and ground-truth segmentation masks
from the Krestenitis et al. benchmark dataset.
"""

import sys
import shutil
from pathlib import Path
from PIL import Image
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAR_DIR = PROJECT_ROOT / "data" / "sar_images" / "krestenitis_dataset"
ARTIFACT_DIR = Path("/Users/priyanshu/.gemini/antigravity-ide/brain/8aa6b193-2a41-408c-803d-950a73f64bf4")

def plot_sample(sample_name="Oil (467)", split="train"):
    img_path = SAR_DIR / split / "images" / f"{sample_name}.jpg"
    mask_path = SAR_DIR / split / "masks" / f"{sample_name}.png"
    
    if not img_path.exists() or not mask_path.exists():
        print(f"[!] File not found: {img_path} or {mask_path}")
        return
        
    img = np.array(Image.open(img_path))
    mask = np.array(Image.open(mask_path))
    
    # Check dimensions
    h, w, c = img.shape
    print(f"Loaded {sample_name}: {w}x{h}, {c} channels")
    
    # Classes:
    # background: [0, 0, 0]
    # oil: [255, 0, 124] (magenta-red)
    # lookalike: [255, 204, 51] (yellow/orange)
    # water: [51, 221, 255] (cyan)
    
    oil_pixels = ((mask[:, :, 0] == 255) & (mask[:, :, 1] == 0) & (mask[:, :, 2] == 124)).sum()
    water_pixels = ((mask[:, :, 0] == 51) & (mask[:, :, 1] == 221) & (mask[:, :, 2] == 255)).sum()
    lookalike_pixels = ((mask[:, :, 0] == 255) & (mask[:, :, 1] == 204) & (mask[:, :, 2] == 51)).sum()
    bg_pixels = ((mask[:, :, 0] == 0) & (mask[:, :, 1] == 0) & (mask[:, :, 2] == 0)).sum()
    total = h * w
    
    print(f"Pixel stats for {sample_name}:")
    print(f"  - Water:      {water_pixels:9,d} ({water_pixels/total*100:.1f}%)")
    print(f"  - Oil Spill:  {oil_pixels:9,d} ({oil_pixels/total*100:.1f}%)")
    print(f"  - Look-alike: {lookalike_pixels:9,d} ({lookalike_pixels/total*100:.1f}%)")
    print(f"  - Background: {bg_pixels:9,d} ({bg_pixels/total*100:.1f}%)")
    
    # Create figure
    fig, axes = plt.subplots(1, 3, figsize=(18, 6), dpi=150)
    
    # 1. Raw SAR Image
    axes[0].imshow(img)
    axes[0].set_title(f"Raw Sentinel-1 SAR ({w}x{h})\nSample: {sample_name}", fontsize=12, fontweight="bold")
    axes[0].axis("off")
    
    # 2. Ground Truth Mask
    axes[1].imshow(mask)
    axes[1].set_title(f"Ground Truth Semantic Mask\n(CERTH Krestenitis Benchmark)", fontsize=12, fontweight="bold")
    axes[1].axis("off")
    
    # Legend for mask
    legend_patches = [
        mpatches.Patch(color=(51/255, 221/255, 255/255), label="Water / Sea Surface"),
        mpatches.Patch(color=(255/255, 0/255, 124/255), label="Oil Spill (Verified)"),
        mpatches.Patch(color=(255/255, 204/255, 51/255), label="Look-alike / Other"),
        mpatches.Patch(color=(0, 0, 0), label="Background / Unlabeled"),
    ]
    axes[1].legend(handles=legend_patches, loc="lower right", framealpha=0.8, fontsize=9)
    
    # 3. Blended Overlay
    # Create highlighted overlay where oil is bright crimson red and semi-transparent
    overlay = img.copy().astype(float)
    oil_mask = (mask[:, :, 0] == 255) & (mask[:, :, 1] == 0) & (mask[:, :, 2] == 124)
    look_mask = (mask[:, :, 0] == 255) & (mask[:, :, 1] == 204) & (mask[:, :, 2] == 51)
    
    # Red highlight for oil
    overlay[oil_mask] = overlay[oil_mask] * 0.4 + np.array([255, 20, 60]) * 0.6
    # Yellow highlight for lookalikes
    overlay[look_mask] = overlay[look_mask] * 0.5 + np.array([255, 215, 0]) * 0.5
    overlay = np.clip(overlay, 0, 255).astype(np.uint8)
    
    axes[2].imshow(overlay)
    axes[2].set_title(f"Attribution Overlay (Oil Spill Highlighted)\n{oil_pixels:,} Oil Pixels Detected", fontsize=12, fontweight="bold")
    axes[2].axis("off")
    
    safe_name = sample_name.replace(" ", "_").replace("(", "").replace(")", "")
    out_file = PROJECT_ROOT / "data" / "sar_images" / f"sar_inspection_{safe_name}.png"
    plt.tight_layout()
    plt.savefig(out_file, bbox_inches="tight", dpi=150)
    plt.close()
    print(f"[+] Saved visual inspection plot: {out_file}")
    
    # Copy to artifacts directory
    if ARTIFACT_DIR.exists():
        art_out = ARTIFACT_DIR / f"sar_inspection_{safe_name}.png"
        shutil.copy(out_file, art_out)
        print(f"[+] Copied to artifact directory: {art_out}")

if __name__ == "__main__":
    plot_sample("Oil (467)", "train")
    plot_sample("Oil (934)", "train")
