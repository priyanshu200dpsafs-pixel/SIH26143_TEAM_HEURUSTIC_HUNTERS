"""
Verify and process the original Krestenitis et al. 5-class SAR Oil Spill Dataset.

Checks data/sar_images/ for zip archives or extracted folders containing:
- 5 Classes:
    1. Sea Surface
    2. Oil Spill
    3. Look-alike
    4. Ship
    5. Land
Verifies image integrity and prints class file distribution.
"""

import sys
import zipfile
from pathlib import Path
from PIL import Image
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SAR_DIR = PROJECT_ROOT / "data" / "sar_images"

CLASS_NAMES = {
    0: "Sea Surface",
    1: "Oil Spill",
    2: "Look-alike",
    3: "Ship",
    4: "Land",
}


def unpack_any_zip():
    """Extract any zip archives placed into data/sar_images/."""
    zip_files = list(SAR_DIR.glob("*.zip")) + list(SAR_DIR.glob("*.tar.gz")) + list(SAR_DIR.glob("*.7z"))
    for zf in zip_files:
        print(f"[*] Found archive: {zf.name}. Extracting into {SAR_DIR}...")
        if zf.name.endswith(".zip"):
            with zipfile.ZipFile(zf, "r") as z:
                z.extractall(SAR_DIR)
            print(f"[+] Successfully extracted {zf.name}")


def scan_and_verify():
    unpack_any_zip()
    
    all_images = list(SAR_DIR.rglob("*.jpg")) + list(SAR_DIR.rglob("*.png")) + list(SAR_DIR.rglob("*.tif"))
    all_images = [f for f in all_images if not f.name.startswith("._")]

    if not all_images:
        print(f"[!] No image files found yet in {SAR_DIR}.")
        print("Please place the downloaded Krestenitis dataset zip or folder into:")
        print(f"👉 {SAR_DIR}")
        return False

    print(f"\n[*] Found {len(all_images)} total image/mask files in {SAR_DIR}.")
    
    # Check for subdirectories matching classes or mask values
    class_counts = {c: 0 for c in ["sea", "oil_spill", "look_alike", "ship", "land", "masks", "raw_sar"]}
    
    sample_tested = 0
    corrupt_count = 0

    for img_path in all_images:
        path_lower = str(img_path).lower()
        if "oil" in path_lower and "look" not in path_lower:
            class_counts["oil_spill"] += 1
        elif "look" in path_lower:
            class_counts["look_alike"] += 1
        elif "ship" in path_lower:
            class_counts["ship"] += 1
        elif "land" in path_lower:
            class_counts["land"] += 1
        elif "sea" in path_lower or "water" in path_lower:
            class_counts["sea"] += 1
        elif "mask" in path_lower:
            class_counts["masks"] += 1
        else:
            class_counts["raw_sar"] += 1

        # Test sample of images for non-corruption
        if sample_tested < 25:
            try:
                with Image.open(img_path) as im:
                    im.verify()
                sample_tested += 1
            except Exception:
                corrupt_count += 1

    print("\n" + "=" * 65)
    print("KRESTENITIS SAR OIL SPILL DATASET VERIFICATION REPORT")
    print("=" * 65)
    print(f"Directory:           {SAR_DIR}")
    print(f"Total Files Found:   {len(all_images):,}")
    print(f"Sample Integrity:    {sample_tested} checked, {corrupt_count} corrupt")
    print("\nClass/Category Breakdown:")
    for cat, count in class_counts.items():
        if count > 0:
            print(f"  - {cat:15s}: {count:5d} files")
    print("=" * 65)
    return True


if __name__ == "__main__":
    scan_and_verify()
