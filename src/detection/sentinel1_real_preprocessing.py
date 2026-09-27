from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image

try:
    import rasterio
except ImportError:
    rasterio = None


class RealSARSourceType(str, Enum):
    RAW_MEASUREMENT_TIFF = "RAW_MEASUREMENT_TIFF"
    ESA_IPF_BROWSE_RASTER = "ESA_IPF_BROWSE_RASTER"
    PROCESSED_CHIP = "PROCESSED_CHIP"


@dataclass
class PreprocessingMetadata:
    """Explicitly documents every transformation applied to real SAR imagery."""
    input_raster: str
    output_raster: str
    source_type: str
    bands: int
    shape: Tuple[int, int, int]
    resolution_meters: Tuple[float, float]
    transform: Optional[List[float]] = None
    crs: str = "WGS84 EPSG:4326 (Footprint Interpolated)"
    min_value: float = 0.0
    max_value: float = 1.0
    mean_value: float = 0.0
    std_value: float = 0.0
    nodata_pixel_count: int = 0
    valid_pixel_count: int = 0
    tiling_enabled: bool = False
    tile_count: int = 1
    tile_size: Tuple[int, int] = (256, 256)
    processing_steps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RealSARPreprocessingResult:
    """Output package from real SAR preprocessing ready for U-Net evaluation."""
    success: bool
    product_id: str
    metadata: PreprocessingMetadata
    normalized_array: Optional[np.ndarray] = None
    inference_tiles: List[np.ndarray] = field(default_factory=list)
    tile_offsets: List[Tuple[int, int]] = field(default_factory=list)
    error_message: Optional[str] = None


class Sentinel1RealPreprocessor:
    """
    Adapter between real Sentinel-1 products and the SAR U-Net detection model.
    """

    def __init__(self, tile_size: int = 256, stride: int = 256):
        self.tile_size = tile_size
        self.stride = stride

    def preprocess_scene(
        self,
        scene_path: Union[str, Path],
        product_id: Optional[str] = None,
        generate_tiles: bool = True,
    ) -> RealSARPreprocessingResult:
        p = Path(scene_path)
        pid = product_id or p.stem
        steps = []

        raster_file = None
        source_type = RealSARSourceType.ESA_IPF_BROWSE_RASTER

        if p.is_dir():
            meas_tiff = p / "measurement/iw-vv.tiff"
            quick_look = p / "preview/quick-look.png"
            if meas_tiff.exists():
                raster_file = meas_tiff
                source_type = RealSARSourceType.RAW_MEASUREMENT_TIFF
            elif quick_look.exists():
                raster_file = quick_look
                source_type = RealSARSourceType.ESA_IPF_BROWSE_RASTER
            else:
                for ext in ["*.tiff", "*.tif", "*.png", "*.jpg"]:
                    found = list(p.glob(f"**/{ext}"))
                    if found:
                        raster_file = found[0]
                        source_type = RealSARSourceType.PROCESSED_CHIP
                        break
        else:
            raster_file = p
            if p.suffix.lower() in [".tif", ".tiff"]:
                source_type = RealSARSourceType.RAW_MEASUREMENT_TIFF
            else:
                source_type = RealSARSourceType.ESA_IPF_BROWSE_RASTER

        if not raster_file or not raster_file.exists():
            return RealSARPreprocessingResult(
                success=False,
                product_id=pid,
                metadata=PreprocessingMetadata(
                    input_raster=str(p),
                    output_raster="",
                    source_type="NONE",
                    bands=0,
                    shape=(0, 0, 0),
                    resolution_meters=(0.0, 0.0),
                ),
                error_message=f"No valid SAR raster found at {p}",
            )

        steps.append(f"Located SAR raster: {raster_file.name} (Source: {source_type.value})")

        try:
            if source_type == RealSARSourceType.RAW_MEASUREMENT_TIFF and rasterio is not None:
                steps.append("Reading 16-bit GeoTIFF via Rasterio (co-polarization VV band)")
                with rasterio.open(str(raster_file)) as src:
                    h_src, w_src = src.height, src.width
                    decimation = max(1, int(max(h_src, w_src) / 2048))
                    out_h, out_w = h_src // decimation, w_src // decimation
                    steps.append(f"Decimated reading factor {decimation}x -> ({out_h}, {out_w}) px")
                    raw_data = src.read(1, out_shape=(out_h, out_w)).astype(np.float32)
                    
                    nodata_val = src.nodata if src.nodata is not None else 0.0
                    nodata_mask = (raw_data == nodata_val) | (raw_data <= 0)
                    valid_pixels = raw_data[~nodata_mask]
                    
                    if valid_pixels.size == 0:
                        raise ValueError("All raster pixels are nodata/zero")

                    p2, p98 = np.percentile(valid_pixels, [2.0, 98.0])
                    steps.append(f"Radiometric dynamic range clipping: p2={p2:.1f} DN, p98={p98:.1f} DN")
                    clipped = np.clip(raw_data, p2, p98)
                    norm_1ch = (clipped - p2) / max(1e-6, (p98 - p2))
                    norm_1ch[nodata_mask] = 0.0
                    steps.append("Normalized linear scaling to [0.0, 1.0] float32")
                    
                    norm_3ch = np.stack([norm_1ch, norm_1ch, norm_1ch], axis=-1)
                    res_m = (10.0 * decimation, 10.0 * decimation)
            else:
                steps.append("Ingesting 8-bit browse raster via PIL")
                with Image.open(str(raster_file)) as pil_img:
                    rgb_img = pil_img.convert("RGB")
                    raw_arr = np.array(rgb_img, dtype=np.float32)
                    h_src, w_src = raw_arr.shape[:2]
                    
                    nodata_mask = (raw_arr[:, :, 0] == 0) & (raw_arr[:, :, 1] == 0) & (raw_arr[:, :, 2] == 0)
                    
                    norm_3ch = raw_arr / 255.0
                    norm_3ch[nodata_mask] = 0.0
                    steps.append("Normalized uint8 [0, 255] -> float32 [0.0, 1.0]")
                    steps.append("Border nodata masking applied (zero fill)")
                    res_m = (50.0, 50.0)

            h, w, c = norm_3ch.shape
            nodata_count = int(np.sum(nodata_mask))
            valid_count = int(norm_3ch.size // 3 - nodata_count)

            v_min = float(np.min(norm_3ch))
            v_max = float(np.max(norm_3ch))
            v_mean = float(np.mean(norm_3ch))
            v_std = float(np.std(norm_3ch))

            tiles = []
            offsets = []

            if generate_tiles:
                steps.append(f"Generating {self.tile_size}x{self.tile_size} inference tiles (stride={self.stride})")
                for r in range(0, max(1, h - self.tile_size + 1), self.stride):
                    for col in range(0, max(1, w - self.tile_size + 1), self.stride):
                        tile = norm_3ch[r : r + self.tile_size, col : col + self.tile_size, :]
                        if tile.shape[0] != self.tile_size or tile.shape[1] != self.tile_size:
                            padded = np.zeros((self.tile_size, self.tile_size, 3), dtype=np.float32)
                            padded[:tile.shape[0], :tile.shape[1], :] = tile
                            tile = padded
                        tiles.append(tile)
                        offsets.append((r, col))

                with Image.fromarray((norm_3ch * 255).astype(np.uint8)) as full_pil:
                    overview_pil = full_pil.resize((self.tile_size, self.tile_size), Image.Resampling.BILINEAR)
                    overview_arr = np.array(overview_pil, dtype=np.float32) / 255.0
                    tiles.insert(0, overview_arr)
                    offsets.insert(0, (0, 0))
                    steps.append("Added whole-scene resized 256x256 overview tile at index 0")
            else:
                with Image.fromarray((norm_3ch * 255).astype(np.uint8)) as full_pil:
                    overview_pil = full_pil.resize((self.tile_size, self.tile_size), Image.Resampling.BILINEAR)
                    overview_arr = np.array(overview_pil, dtype=np.float32) / 255.0
                    tiles = [overview_arr]
                    offsets = [(0, 0)]
                    steps.append("Single whole-scene resized 256x256 tile generated")

            meta = PreprocessingMetadata(
                input_raster=str(raster_file),
                output_raster=f"memory://preprocessed_tiles/{pid}",
                source_type=source_type.value,
                bands=c,
                shape=(h, w, c),
                resolution_meters=res_m,
                crs="WGS84 EPSG:4326 (Footprint Interpolated)",
                min_value=v_min,
                max_value=v_max,
                mean_value=v_mean,
                std_value=v_std,
                nodata_pixel_count=nodata_count,
                valid_pixel_count=valid_count,
                tiling_enabled=generate_tiles,
                tile_count=len(tiles),
                tile_size=(self.tile_size, self.tile_size),
                processing_steps=steps,
            )

            return RealSARPreprocessingResult(
                success=True,
                product_id=pid,
                metadata=meta,
                normalized_array=norm_3ch,
                inference_tiles=tiles,
                tile_offsets=offsets,
            )

        except Exception as e:
            return RealSARPreprocessingResult(
                success=False,
                product_id=pid,
                metadata=PreprocessingMetadata(
                    input_raster=str(raster_file),
                    output_raster="",
                    source_type=source_type.value,
                    bands=0,
                    shape=(0, 0, 0),
                    resolution_meters=(0.0, 0.0),
                    processing_steps=steps,
                ),
                error_message=f"Preprocessing failure: {e}",
            )
