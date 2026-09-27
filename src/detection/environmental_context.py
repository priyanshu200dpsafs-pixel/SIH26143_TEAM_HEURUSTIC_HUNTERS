"""
Environmental Context Module (ERA5 10m Wind Integration).

Associates SAR observations with meteorological wind forcing from ECMWF ERA5.
Provides contextual evidence for capillary wave dampening physics:
- Bragg scattering requires sufficient surface wind (>= 3.0 m/s) to produce roughness.
- Low winds (< 3.0 m/s) produce mirror-like specular sea reflection, yielding false look-alikes.
- High winds (> 12.0 m/s) cause wave breaking, emulsification, and contrast washout.

DO NOT USE WIND AS A MAGICAL CLASSIFIER.
Wind is physical contextual evidence documenting observation quality.
"""

import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
import numpy as np

try:
    from src.drift_model.environmental_interpolator import EnvironmentalInterpolator
except ImportError:
    EnvironmentalInterpolator = None


class EnvironmentalContextExtractor:
    """
    Retrieves and formats ERA5 atmospheric wind forcing for candidate SAR detections.
    """

    def __init__(
        self,
        era5_netcdf_path: Union[str, Path] = "data/weather/era5_wind_mediterranean_case_study.nc",
    ):
        self.era5_path = Path(era5_netcdf_path)
        self.interpolator: Optional[Any] = None
        
        if self.era5_path.exists() and EnvironmentalInterpolator is not None:
            try:
                self.interpolator = EnvironmentalInterpolator(era5_path=str(self.era5_path))
            except Exception as e:
                self.interpolator = None

    def get_context(
        self,
        lat: float,
        lon: float,
        timestamp_epoch: float,
    ) -> Dict[str, Any]:
        """
        Interpolate ERA5 wind at (lat, lon, timestamp) and return structured contextual evidence.
        """
        if self.interpolator is not None:
            try:
                u, v = self.interpolator.interpolate_wind(lat, lon, timestamp_epoch)
                speed = math.sqrt(u**2 + v**2)
                # Meteorological wind direction: degrees FROM which wind blows
                direction_deg = (180.0 + math.degrees(math.atan2(u, v))) % 360.0
                
                # Closest ERA5 time step offset
                era5_times = self.interpolator._era5_times
                closest_t = era5_times[np.argmin(np.abs(era5_times - timestamp_epoch))]
                temporal_offset = abs(float(timestamp_epoch - closest_t))
                
                # Physical dampening window assessment
                if 3.0 <= speed <= 12.0:
                    dampening_regime = "OPTIMAL_BRAGG_DAMPENING"
                    plausibility_factor = 1.00
                    assessment = (
                        f"Wind speed {speed:.1f} m/s is within the [3.0, 12.0] m/s window. "
                        f"Capillary-gravity Bragg waves are active and dampened by surface film."
                    )
                elif speed < 3.0:
                    dampening_regime = "CALM_SEA_LOOKALIKE_RISK"
                    plausibility_factor = 0.50
                    assessment = (
                        f"Low wind speed {speed:.1f} m/s. High risk of natural calm sea look-alikes "
                        f"due to specular reflection in clean surrounding waters."
                    )
                else:
                    dampening_regime = "HIGH_WIND_DISPERSION_RISK"
                    plausibility_factor = 0.60
                    assessment = (
                        f"High wind speed {speed:.1f} m/s. Wave breaking and turbulence wash out "
                        f"slick contrast; physical dispersion likely active."
                    )
                    
                return {
                    "status": "ERA5_CONTEXT_AVAILABLE",
                    "wind_u_ms": round(float(u), 3),
                    "wind_v_ms": round(float(v), 3),
                    "wind_speed_ms": round(float(speed), 3),
                    "wind_direction_deg": round(float(direction_deg), 1),
                    "temporal_offset_seconds": round(temporal_offset, 1),
                    "dampening_regime": dampening_regime,
                    "plausibility_factor": plausibility_factor,
                    "assessment": assessment,
                    "source_provenance": "ECMWF ERA5 Reanalysis 10m Wind (0.25° resolution, hourly)",
                    "physical_assumptions": [
                        "Surface hydrocarbon films dampen short capillary-gravity waves (wavelength 1-10 cm).",
                        "SAR backscatter contrast requires background wind-roughened sea (3 to 12 m/s).",
                        "Wind is contextual evidence only; it does not replace multi-spectral or spatial morphology."
                    ],
                }
            except Exception as e:
                pass
                
        # Graceful fallback when outside domain or unavailable
        return {
            "status": "ERA5_CONTEXT_UNAVAILABLE",
            "wind_u_ms": None,
            "wind_v_ms": None,
            "wind_speed_ms": None,
            "wind_direction_deg": None,
            "temporal_offset_seconds": None,
            "dampening_regime": "UNKNOWN",
            "plausibility_factor": 0.80,
            "assessment": "ERA5 wind reanalysis data not available for this spatiotemporal coordinate.",
            "source_provenance": "UNAVAILABLE",
            "physical_assumptions": [
                "Assumes standard marine boundary layer conditions in absence of in-situ measurements."
            ],
        }
