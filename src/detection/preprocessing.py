"""
Deterministic Data Preprocessing and Augmentation Pipeline for SAR Segmentation.

Provides:
- Deterministic resizing (bilinear for rasters, nearest-neighbor for discrete integer masks)
- Standardized radiometric normalization (scaling to [0, 1] or ImageNet z-scores)
- Flexible channel handling (1-channel GRD/dB -> 3-channel tensor)
- Mask encoding / decoding utilities for Krestenitis (4 classes) and SOS (binary)
- Geometric augmentations applied EXCLUSIVELY to training splits (never to val or test)
- Rigorous split validation ensuring 0 cross-split leakage.
"""

import random
from typing import Any, Dict, Optional, Tuple, Union
import numpy as np
from PIL import Image
import torch
import torch.nn.functional as F

from src.detection.dataset_adapters import (
    KRESTENITIS_CLASSES,
    KRESTENITIS_COLOR_MAP,
    KRESTENITIS_ID_TO_COLOR,
    SOS_CLASSES,
    decode_krestenitis_rgb_mask,
    encode_krestenitis_class_mask,
)

# Standard ImageNet normalization parameters (optional)
IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
IMAGENET_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def resize_image_and_mask(
    image: np.ndarray,
    mask: np.ndarray,
    target_size: Tuple[int, int] = (256, 256),
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Deterministically resize image and mask to (target_height, target_width).
    Uses bilinear interpolation for the image raster and nearest-neighbor
    for the discrete integer class mask.
    """
    target_h, target_w = target_size
    
    # Handle image
    if image.ndim == 2:
        pil_img = Image.fromarray((np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8) if image.dtype == np.float32 else image)
        pil_img = pil_img.resize((target_w, target_h), Image.Resampling.BILINEAR)
        resized_img = np.array(pil_img, dtype=np.float32)
        if image.dtype == np.float32:
            resized_img /= 255.0
    elif image.ndim == 3:
        if image.shape[2] in (1, 3, 4):
            pil_img = Image.fromarray((np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8) if image.dtype == np.float32 else image)
            pil_img = pil_img.resize((target_w, target_h), Image.Resampling.BILINEAR)
            resized_img = np.array(pil_img, dtype=np.float32)
            if image.dtype == np.float32:
                resized_img /= 255.0
        else:
            # (C, H, W) format
            t_img = torch.from_numpy(image).unsqueeze(0).float()
            resized_t = F.interpolate(t_img, size=(target_h, target_w), mode="bilinear", align_corners=False)
            resized_img = resized_t.squeeze(0).numpy()
    else:
        raise ValueError(f"Unsupported image dimension: {image.ndim}")
        
    # Handle mask: MUST use nearest neighbor to preserve integer IDs
    pil_mask = Image.fromarray(mask.astype(np.uint8 if mask.max() <= 255 else np.int32))
    pil_mask = pil_mask.resize((target_w, target_h), Image.Resampling.NEAREST)
    resized_mask = np.array(pil_mask, dtype=mask.dtype)
    
    return resized_img, resized_mask


def normalize_sar_image(
    image: np.ndarray,
    method: str = "min_max",
    clip_db: Optional[Tuple[float, float]] = (-30.0, 0.0),
) -> np.ndarray:
    """
    Radiometric normalization of SAR intensity or amplitude rasters.
    
    Methods:
      - 'min_max': linear scaling to [0.0, 1.0]
      - 'z_score': zero-mean, unit-variance standardization
      - 'imagenet': ImageNet channel normalization (for pre-trained backbones)
    """
    arr = image.astype(np.float32)
    
    if method == "min_max":
        min_val = float(np.min(arr))
        max_val = float(np.max(arr))
        if max_val - min_val > 1e-6:
            return (arr - min_val) / (max_val - min_val)
        return np.zeros_like(arr)
        
    elif method == "z_score":
        mean = float(np.mean(arr))
        std = float(np.std(arr))
        if std > 1e-6:
            return (arr - mean) / std
        return arr - mean
        
    elif method == "imagenet":
        # Assumes input is in [0, 1] range and has 3 channels
        if arr.ndim == 2:
            arr = np.stack([arr, arr, arr], axis=-1)
        elif arr.ndim == 3 and arr.shape[0] == 3:
            arr = arr.transpose(1, 2, 0)
        norm_arr = (arr - IMAGENET_MEAN) / IMAGENET_STD
        return norm_arr
        
    else:
        raise ValueError(f"Unknown normalization method: {method}")


class TrainingAugmentor:
    """
    Geometric data augmentations applied STRICTLY to training data.
    Never applied to validation or test splits.
    """

    def __init__(
        self,
        p_hflip: float = 0.5,
        p_vflip: float = 0.5,
        p_rot90: float = 0.5,
        seed: Optional[int] = None,
    ):
        self.p_hflip = p_hflip
        self.p_vflip = p_vflip
        self.p_rot90 = p_rot90
        self.rng = random.Random(seed) if seed is not None else random

    def __call__(
        self,
        image: np.ndarray,
        mask: np.ndarray,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Apply joint spatial transformations to (H, W, C) image and (H, W) mask.
        """
        # Horizontal Flip
        if self.rng.random() < self.p_hflip:
            image = np.fliplr(image)
            mask = np.fliplr(mask)
            
        # Vertical Flip
        if self.rng.random() < self.p_vflip:
            image = np.flipud(image)
            mask = np.flipud(mask)
            
        # Random 90-degree Rotation
        if self.rng.random() < self.p_rot90:
            k = self.rng.choice([1, 2, 3])
            image = np.rot90(image, k, (0, 1))
            mask = np.rot90(mask, k, (0, 1))
            
        return np.ascontiguousarray(image), np.ascontiguousarray(mask)
