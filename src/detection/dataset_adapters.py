"""
Dataset Adapters for SAR Oil Spill Segmentation.

Implements independent adapters for:
1. Krestenitis Dataset:
   Verified 4-class ontology:
     0: Background
     1: Oil Spill
     2: Look-alike / Others
     3: Water / Sea Surface
   (Do NOT create Ship or Land classes - unverified in dataset).

2. SOS Dataset (Zenodo Refined):
   Separate binary segmentation benchmark:
     0: Background
     1: Oil Spill
   (Do NOT merge labels silently with Krestenitis).
"""

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image
import torch
from torch.utils.data import Dataset

# Canonical 4-class ontology for Krestenitis
KRESTENITIS_CLASSES: Dict[int, str] = {
    0: "Background",
    1: "Oil Spill",
    2: "Look-alike / Others",
    3: "Water / Sea Surface",
}

# Verified exact RGB color map from data/sar_images/krestenitis_dataset/label_colors.txt
KRESTENITIS_COLOR_MAP: Dict[Tuple[int, int, int], int] = {
    (0, 0, 0): 0,        # Background
    (255, 0, 124): 1,    # Oil Spill
    (255, 204, 51): 2,   # Look-alike / Others
    (51, 221, 255): 3,   # Water / Sea Surface
}

# Reverse mapping for visualization
KRESTENITIS_ID_TO_COLOR: Dict[int, Tuple[int, int, int]] = {
    0: (0, 0, 0),
    1: (255, 0, 124),
    2: (255, 204, 51),
    3: (51, 221, 255),
}

# SOS Binary ontology
SOS_CLASSES: Dict[int, str] = {
    0: "Background",
    1: "Oil Spill",
}


def decode_krestenitis_rgb_mask(rgb_arr: np.ndarray) -> np.ndarray:
    """
    Convert an RGB mask from Krestenitis dataset into a 2D integer class mask {0, 1, 2, 3}.
    Uses exact RGB matching with fallback to minimum Euclidean distance.
    
    Args:
        rgb_arr: Array of shape (H, W, 3) or (H, W, 4) with uint8 RGB values.
        
    Returns:
        2D integer array of shape (H, W) with class IDs {0, 1, 2, 3}.
    """
    if rgb_arr.ndim == 2:
        return rgb_arr.astype(np.int64)
    if rgb_arr.shape[2] > 3:
        rgb_arr = rgb_arr[:, :, :3]
        
    h, w, _ = rgb_arr.shape
    cls_mask = np.zeros((h, w), dtype=np.int64)
    
    # Fast exact boolean matching
    matched = np.zeros((h, w), dtype=bool)
    for (r, g, b), cid in KRESTENITIS_COLOR_MAP.items():
        m = (rgb_arr[..., 0] == r) & (rgb_arr[..., 1] == g) & (rgb_arr[..., 2] == b)
        cls_mask[m] = cid
        matched |= m
        
    # Nearest color fallback for any antialiased edge pixels if present
    if not np.all(matched):
        unmatched_idx = ~matched
        unmatched_rgb = rgb_arr[unmatched_idx].astype(np.float32)
        ref_colors = np.array(list(KRESTENITIS_COLOR_MAP.keys()), dtype=np.float32) # (4, 3)
        ref_ids = np.array(list(KRESTENITIS_COLOR_MAP.values()), dtype=np.int64)    # (4,)
        dists = np.sum((unmatched_rgb[:, None, :] - ref_colors[None, :, :]) ** 2, axis=-1)
        nearest = ref_ids[np.argmin(dists, axis=-1)]
        cls_mask[unmatched_idx] = nearest
        
    return cls_mask


def encode_krestenitis_class_mask(class_mask: np.ndarray) -> np.ndarray:
    """
    Convert a 2D integer class mask {0, 1, 2, 3} back into an RGB image for visualization.
    """
    h, w = class_mask.shape
    rgb_arr = np.zeros((h, w, 3), dtype=np.uint8)
    for cid, (r, g, b) in KRESTENITIS_ID_TO_COLOR.items():
        m = (class_mask == cid)
        rgb_arr[m] = [r, g, b]
    return rgb_arr


class KrestenitisDataset(Dataset):
    """
    PyTorch Dataset adapter for the Krestenitis SAR oil spill dataset.
    
    Verified classes:
      0: Background
      1: Oil Spill
      2: Look-alike / Others
      3: Water / Sea Surface
    """

    def __init__(
        self,
        root_dir: Union[str, Path] = "data/sar_images/krestenitis_dataset",
        split: str = "train",
        target_size: Optional[Tuple[int, int]] = (256, 256),
        transform: Optional[Callable] = None,
        return_tensor: bool = True,
    ):
        """
        Args:
            root_dir: Root directory of krestenitis dataset containing train/val/test folders.
            split: One of 'train', 'val', or 'test'.
            target_size: Optional (height, width) to resize images and masks.
            transform: Optional augmentation transform (applied only in train).
            return_tensor: Whether to return torch.Tensor or numpy arrays.
        """
        self.root_dir = Path(root_dir)
        self.split = split.lower()
        if self.split not in ("train", "val", "test"):
            raise ValueError(f"Invalid split '{split}'. Must be 'train', 'val', or 'test'.")
            
        self.target_size = target_size
        self.transform = transform
        self.return_tensor = return_tensor
        
        self.img_dir = self.root_dir / self.split / "images"
        self.mask_dir = self.root_dir / self.split / "masks"
        
        if not self.img_dir.exists() or not self.mask_dir.exists():
            raise FileNotFoundError(f"Split directories not found under {self.root_dir / self.split}")
            
        # Discover and pair files deterministically by stem
        img_files = sorted([f for f in os.listdir(self.img_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff'))])
        mask_map = {Path(f).stem: f for f in os.listdir(self.mask_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff'))}
        
        self.pairs: List[Tuple[str, str]] = []
        for img_name in img_files:
            stem = Path(img_name).stem
            if stem in mask_map:
                self.pairs.append((img_name, mask_map[stem]))
                
        if len(self.pairs) == 0:
            raise RuntimeError(f"No matching image/mask pairs found in {self.img_dir}")

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        img_name, mask_name = self.pairs[idx]
        img_path = self.img_dir / img_name
        mask_path = self.mask_dir / mask_name
        
        # Load SAR image (RGB or grayscale)
        with Image.open(img_path) as pil_img:
            pil_img = pil_img.convert("RGB")
            if self.target_size is not None and pil_img.size != (self.target_size[1], self.target_size[0]):
                pil_img = pil_img.resize((self.target_size[1], self.target_size[0]), Image.Resampling.BILINEAR)
            img_arr = np.array(pil_img, dtype=np.float32) / 255.0  # Normalize to [0, 1]
            
        # Load mask and decode to integer class IDs
        with Image.open(mask_path) as pil_mask:
            pil_mask = pil_mask.convert("RGB")
            if self.target_size is not None and pil_mask.size != (self.target_size[1], self.target_size[0]):
                pil_mask = pil_mask.resize((self.target_size[1], self.target_size[0]), Image.Resampling.NEAREST)
            raw_mask_arr = np.array(pil_mask, dtype=np.uint8)
            cls_mask = decode_krestenitis_rgb_mask(raw_mask_arr)
            
        # Apply augmentation if provided
        if self.transform is not None:
            img_arr, cls_mask = self.transform(img_arr, cls_mask)
            
        if self.return_tensor:
            # (H, W, C) -> (C, H, W)
            img_tensor = torch.from_numpy(img_arr.transpose(2, 0, 1)).float()
            mask_tensor = torch.from_numpy(cls_mask).long()
            return {
                "image": img_tensor,
                "mask": mask_tensor,
                "filename": img_name,
                "split": self.split,
            }
        else:
            return {
                "image": img_arr,
                "mask": cls_mask,
                "filename": img_name,
                "split": self.split,
            }


class SOSDataset(Dataset):
    """
    PyTorch Dataset adapter for the SOS (Satellite Oil Spill) Refined Dataset.
    Independent binary segmentation benchmark:
      0: Background
      1: Oil Spill
    """

    def __init__(
        self,
        root_dir: Union[str, Path] = "data/sar_images/sos_dataset",
        split: str = "train",
        target_size: Optional[Tuple[int, int]] = (256, 256),
        transform: Optional[Callable] = None,
        threshold: int = 127,
        return_tensor: bool = True,
        prevent_leakage: bool = True,
    ):
        self.root_dir = Path(root_dir)
        self.split = split.lower()
        if self.split not in ("train", "val"):
            raise ValueError(f"Invalid SOS split '{split}'. Must be 'train' or 'val'.")
            
        self.target_size = target_size
        self.transform = transform
        self.threshold = threshold
        self.return_tensor = return_tensor
        self.prevent_leakage = prevent_leakage
        
        self.img_dir = self.root_dir / "images" / self.split
        self.mask_dir = self.root_dir / "masks" / self.split
        
        if not self.img_dir.exists() or not self.mask_dir.exists():
            raise FileNotFoundError(f"SOS split directories not found under {self.img_dir}")
            
        img_files = sorted([f for f in os.listdir(self.img_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff'))])
        mask_map = {Path(f).stem: f for f in os.listdir(self.mask_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.tif', '.tiff'))}
        raw_pairs = [(f, mask_map[Path(f).stem]) for f in img_files if Path(f).stem in mask_map]
        
        # In Zenodo SOS original distribution, the 1615 val images are a subset of the 6455 images in train/.
        # If prevent_leakage=True and split='train', we filter out all validation filenames to guarantee 0 data leakage.
        if self.split == "train" and self.prevent_leakage:
            val_img_dir = self.root_dir / "images" / "val"
            if val_img_dir.exists():
                val_names = set(os.listdir(val_img_dir))
                raw_pairs = [p for p in raw_pairs if p[0] not in val_names]
                
        self.pairs = raw_pairs
        if len(self.pairs) == 0:
            raise RuntimeError(f"No matching image/mask pairs found in SOS {self.split}")

    def __len__(self) -> int:
        return len(self.pairs)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        img_name, mask_name = self.pairs[idx]
        img_path = self.img_dir / img_name
        mask_path = self.mask_dir / mask_name
        
        with Image.open(img_path) as pil_img:
            pil_img = pil_img.convert("RGB")
            if self.target_size is not None and pil_img.size != (self.target_size[1], self.target_size[0]):
                pil_img = pil_img.resize((self.target_size[1], self.target_size[0]), Image.Resampling.BILINEAR)
            img_arr = np.array(pil_img, dtype=np.float32) / 255.0
            
        with Image.open(mask_path) as pil_mask:
            if self.target_size is not None and pil_mask.size != (self.target_size[1], self.target_size[0]):
                pil_mask = pil_mask.resize((self.target_size[1], self.target_size[0]), Image.Resampling.NEAREST)
            raw_mask_arr = np.array(pil_mask)
            if raw_mask_arr.ndim == 3:
                raw_mask_arr = raw_mask_arr[..., 0]
            binary_mask = (raw_mask_arr > self.threshold).astype(np.int64)
            
        if self.transform is not None:
            img_arr, binary_mask = self.transform(img_arr, binary_mask)
            
        if self.return_tensor:
            img_tensor = torch.from_numpy(img_arr.transpose(2, 0, 1)).float()
            mask_tensor = torch.from_numpy(binary_mask).long()
            return {
                "image": img_tensor,
                "mask": mask_tensor,
                "filename": img_name,
                "split": self.split,
            }
        else:
            return {
                "image": img_arr,
                "mask": binary_mask,
                "filename": img_name,
                "split": self.split,
            }
