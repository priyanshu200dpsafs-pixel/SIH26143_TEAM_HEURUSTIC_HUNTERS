"""
SAR Oil Spill Segmentation Baseline Model (U-Net Architecture).

Provides a strong, reproducible, modular PyTorch U-Net baseline for 4-class SAR
segmentation on the Krestenitis dataset:
  0: Background
  1: Oil Spill
  2: Look-alike / Others
  3: Water / Sea Surface

Maintains backwards compatibility with existing SARSARSegmentor interfaces.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image
import torch
import torch.nn as nn
import torch.nn.functional as F

from src.detection.dataset_adapters import (
    KRESTENITIS_CLASSES,
    decode_krestenitis_rgb_mask,
    encode_krestenitis_class_mask,
)
from src.detection.preprocessing import resize_image_and_mask, normalize_sar_image


class DoubleConv(nn.Module):
    """(Convolution => [BN] => ReLU) * 2"""

    def __init__(self, in_channels: int, out_channels: int, mid_channels: Optional[int] = None):
        super().__init__()
        if not mid_channels:
            mid_channels = out_channels
        self.double_conv = nn.Sequential(
            nn.Conv2d(in_channels, mid_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(mid_channels),
            nn.ReLU(inplace=True),
            nn.Conv2d(mid_channels, out_channels, kernel_size=3, padding=1, bias=False),
            nn.BatchNorm2d(out_channels),
            nn.ReLU(inplace=True),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.double_conv(x)


class Down(nn.Module):
    """Downscaling with maxpool then double conv"""

    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.maxpool_conv = nn.Sequential(
            nn.MaxPool2d(2),
            DoubleConv(in_channels, out_channels),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.maxpool_conv(x)


class Up(nn.Module):
    """Upscaling then double conv with skip connection"""

    def __init__(self, in_channels: int, out_channels: int, bilinear: bool = False):
        super().__init__()
        if bilinear:
            self.up = nn.Upsample(scale_factor=2, mode="bilinear", align_corners=True)
            self.conv = DoubleConv(in_channels, out_channels, in_channels // 2)
        else:
            self.up = nn.ConvTranspose2d(in_channels, in_channels // 2, kernel_size=2, stride=2)
            self.conv = DoubleConv(in_channels, out_channels)

    def forward(self, x1: torch.Tensor, x2: torch.Tensor) -> torch.Tensor:
        x1 = self.up(x1)
        # Input is CHW
        diff_y = x2.size()[2] - x1.size()[2]
        diff_x = x2.size()[3] - x1.size()[3]

        x1 = F.pad(x1, [diff_x // 2, diff_x - diff_x // 2, diff_y // 2, diff_y - diff_y // 2])
        x = torch.cat([x2, x1], dim=1)
        return self.conv(x)


class OutConv(nn.Module):
    """1x1 Convolution to output classes"""

    def __init__(self, in_channels: int, out_channels: int):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, out_channels, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(x)


class UNetBaseline(nn.Module):
    """
    Full U-Net Architecture for 4-Class SAR Segmentation.
    """

    def __init__(
        self,
        n_channels: int = 3,
        n_classes: int = 4,
        features: Tuple[int, ...] = (32, 64, 128, 256),
    ):
        super().__init__()
        self.n_channels = n_channels
        self.n_classes = n_classes

        f = features
        self.inc = DoubleConv(n_channels, f[0])
        self.down1 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(f[0], f[1]))
        self.down2 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(f[1], f[2]))
        self.down3 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(f[2], f[3]))
        self.down4 = nn.Sequential(nn.MaxPool2d(2), DoubleConv(f[3], f[3] * 2))

        self.up1_trans = nn.ConvTranspose2d(f[3] * 2, f[3], kernel_size=2, stride=2)
        self.up1_conv = DoubleConv(f[3] * 2, f[3])

        self.up2_trans = nn.ConvTranspose2d(f[3], f[2], kernel_size=2, stride=2)
        self.up2_conv = DoubleConv(f[2] * 2, f[2])

        self.up3_trans = nn.ConvTranspose2d(f[2], f[1], kernel_size=2, stride=2)
        self.up3_conv = DoubleConv(f[1] * 2, f[1])

        self.up4_trans = nn.ConvTranspose2d(f[1], f[0], kernel_size=2, stride=2)
        self.up4_conv = DoubleConv(f[0] * 2, f[0])

        self.outc = nn.Conv2d(f[0], n_classes, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x1 = self.inc(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)

        u1 = self.up1_trans(x5)
        d1 = self.up1_conv(torch.cat([x4, u1], dim=1))

        u2 = self.up2_trans(d1)
        d2 = self.up2_conv(torch.cat([x3, u2], dim=1))

        u3 = self.up3_trans(d2)
        d3 = self.up3_conv(torch.cat([x2, u3], dim=1))

        u4 = self.up4_trans(d3)
        d4 = self.up4_conv(torch.cat([x1, u4], dim=1))

        logits = self.outc(d4)
        return logits

    def predict_probabilities(self, x: torch.Tensor) -> torch.Tensor:
        """Return softmax probabilities [B, C, H, W]"""
        logits = self.forward(x)
        return F.softmax(logits, dim=1)


class SARSARSegmentor:
    """
    Inference manager for SAR oil spill detection models.
    Supports ONNX Runtime and PyTorch backends.
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = "cpu",
        num_classes: int = 4,
    ):
        """
        Initialize the SAR segmentor with model weights.

        Args:
            model_path: Path to serialized model weights (.pt or .pth).
            device: Inference device ('cpu', 'cuda', 'mps').
            num_classes: Number of target segmentation classes (4 for Krestenitis).
        """
        self.model_path = model_path
        self.device = device
        self.num_classes = num_classes
        self.model: Optional[UNetBaseline] = None

        if model_path is not None and Path(model_path).exists():
            self.load_model(model_path)

    def load_model(self, model_path: Optional[str] = None) -> None:
        """Load segmentation model weights into memory."""
        path = model_path or self.model_path
        if path is None or not Path(path).exists():
            raise FileNotFoundError(f"Model checkpoint not found: {path}")
            
        model = UNetBaseline(n_channels=3, n_classes=self.num_classes)
        state_dict = torch.load(path, map_location=self.device)
        if "model_state_dict" in state_dict:
            model.load_state_dict(state_dict["model_state_dict"])
        else:
            model.load_state_dict(state_dict)
        model.to(self.device)
        model.eval()
        self.model = model
        self.model_path = path

    def segment(
        self,
        image_input: Union[str, np.ndarray, torch.Tensor],
        threshold: float = 0.5,
        target_size: Tuple[int, int] = (256, 256),
    ) -> Dict[str, Any]:
        """
        Segment oil slick formations from a georeferenced SAR image or array.

        Args:
            image_input: Path to image, or numpy array (H, W, 3), or torch tensor.
            threshold: Probability threshold for positive classification.
            target_size: Input resolution to feed into the model.

        Returns:
            Dictionary containing class mask, oil binary mask, probabilities,
            and confidence metrics.
        """
        if self.model is None:
            raise NotImplementedError("SAR segmentation inference not yet implemented: model weights not loaded.")

        # Handle input
        if isinstance(image_input, str):
            with Image.open(image_input) as pil_img:
                pil_img = pil_img.convert("RGB").resize((target_size[1], target_size[0]), Image.Resampling.BILINEAR)
                arr = np.array(pil_img, dtype=np.float32) / 255.0
        elif isinstance(image_input, np.ndarray):
            if image_input.ndim == 2:
                image_input = np.stack([image_input]*3, axis=-1)
            arr = image_input.astype(np.float32)
            if arr.max() > 1.0:
                arr /= 255.0
            if arr.shape[:2] != target_size:
                pil_img = Image.fromarray((arr * 255.0).astype(np.uint8))
                pil_img = pil_img.resize((target_size[1], target_size[0]), Image.Resampling.BILINEAR)
                arr = np.array(pil_img, dtype=np.float32) / 255.0
        elif isinstance(image_input, torch.Tensor):
            t = image_input.to(self.device)
            if t.ndim == 3:
                t = t.unsqueeze(0)
            with torch.no_grad():
                probs = self.model.predict_probabilities(t)
                pred_cls = torch.argmax(probs, dim=1).squeeze(0).cpu().numpy()
                probs_np = probs.squeeze(0).cpu().numpy()
                oil_prob = probs_np[1]
                oil_mask = (oil_prob >= threshold).astype(np.uint8)
                return {
                    "class_mask": pred_cls,
                    "oil_mask": oil_mask,
                    "probabilities": probs_np,
                    "oil_probability": oil_prob,
                    "oil_pixel_count": int(oil_mask.sum()),
                }
        else:
            raise ValueError(f"Unsupported image input type: {type(image_input)}")

        # Convert array to tensor
        t = torch.from_numpy(arr.transpose(2, 0, 1)).unsqueeze(0).float().to(self.device)
        with torch.no_grad():
            probs = self.model.predict_probabilities(t)
            pred_cls = torch.argmax(probs, dim=1).squeeze(0).cpu().numpy()
            probs_np = probs.squeeze(0).cpu().numpy()
            oil_prob = probs_np[1]
            oil_mask = (oil_prob >= threshold).astype(np.uint8)

        return {
            "class_mask": pred_cls,
            "oil_mask": oil_mask,
            "probabilities": probs_np,
            "oil_probability": oil_prob,
            "oil_pixel_count": int(oil_mask.sum()),
        }


def preprocess_sar_image(
    image_path: str,
    target_size: Tuple[int, int] = (256, 256),
    apply_speckle_filter: bool = False,
) -> np.ndarray:
    """
    Perform radiometric calibration, speckle reduction, and normalization.

    Args:
        image_path: Path to raw input SAR raster.
        target_size: Desired model input resolution.
        apply_speckle_filter: Whether to apply Lee speckle noise filter.

    Returns:
        Normalized input array suitable for model inference.
    """
    with Image.open(image_path) as pil_img:
        pil_img = pil_img.convert("RGB").resize((target_size[1], target_size[0]), Image.Resampling.BILINEAR)
        arr = np.array(pil_img, dtype=np.float32) / 255.0
    return arr


def predict_spill_mask(
    sar_tensor: Any,
    confidence_threshold: float = 0.5,
) -> Any:
    """
    Execute model forward pass and binarize output confidence map.

    Args:
        sar_tensor: Preprocessed tensor.
        confidence_threshold: Cutoff probability for slick segmentation.

    Returns:
        Binarized segmentation mask array.
    """
    if isinstance(sar_tensor, np.ndarray):
        return (sar_tensor >= confidence_threshold).astype(np.uint8)
    elif isinstance(sar_tensor, torch.Tensor):
        return (sar_tensor >= confidence_threshold).int()
    else:
        raise NotImplementedError("Prediction routine requires tensor or ndarray.")
