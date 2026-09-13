"""
Spatiotemporal Interpolation Engine for Atmospheric and Hydrodynamic Forcing Fields.

Provides continuous (spatial and temporal) interpolation of:
- ERA5 10m Wind Vectors (u10, v10)
- NASA OSCAR Ocean Surface Currents (u, v)
Implemented with high-performance pure NumPy bilinear and trilinear interpolation,
handling exact grid nodes, inter-grid coordinates, domain boundaries, and missing values.
"""

from typing import Optional, Tuple, Union
import numpy as np
import pandas as pd
import xarray as xr


def _interp_1d_index(coords: np.ndarray, val: float) -> Tuple[int, float]:
    """
    Find lower index i and normalized weight fraction t in [0, 1] for 1D coordinate array.
    """
    n = len(coords)
    if val <= coords[0]:
        return 0, 0.0
    if val >= coords[-1]:
        return n - 2, 1.0

    idx = int(np.searchsorted(coords, val)) - 1
    idx = max(0, min(n - 2, idx))
    denom = coords[idx + 1] - coords[idx]
    t = float((val - coords[idx]) / denom) if denom != 0 else 0.0
    return idx, float(np.clip(t, 0.0, 1.0))


def bilinear_interp_2d(
    x_coords: np.ndarray,
    y_coords: np.ndarray,
    data_2d: np.ndarray,
    x: float,
    y: float,
) -> float:
    """
    Bilinear interpolation on a 2D regular grid data_2d of shape (len(x_coords), len(y_coords)).
    """
    ix, tx = _interp_1d_index(x_coords, x)
    iy, ty = _interp_1d_index(y_coords, y)

    f00 = data_2d[ix, iy]
    f10 = data_2d[ix + 1, iy]
    f01 = data_2d[ix, iy + 1]
    f11 = data_2d[ix + 1, iy + 1]

    val = (1.0 - tx) * (1.0 - ty) * f00 + tx * (1.0 - ty) * f10 + (1.0 - tx) * ty * f01 + tx * ty * f11
    return float(val)


def trilinear_interp_3d(
    t_coords: np.ndarray,
    y_coords: np.ndarray,
    x_coords: np.ndarray,
    data_3d: np.ndarray,
    t: float,
    y: float,
    x: float,
) -> float:
    """
    Trilinear interpolation on a 3D regular grid data_3d of shape (len(t_coords), len(y_coords), len(x_coords)).
    """
    it, tt = _interp_1d_index(t_coords, t)
    iy, ty = _interp_1d_index(y_coords, y)
    ix, tx = _interp_1d_index(x_coords, x)

    # Values at time it
    v0_00 = data_3d[it, iy, ix]
    v0_10 = data_3d[it, iy + 1, ix]
    v0_01 = data_3d[it, iy, ix + 1]
    v0_11 = data_3d[it, iy + 1, ix + 1]
    f0 = (1.0 - ty) * (1.0 - tx) * v0_00 + ty * (1.0 - tx) * v0_10 + (1.0 - ty) * tx * v0_01 + ty * tx * v0_11

    # Values at time it + 1
    v1_00 = data_3d[it + 1, iy, ix]
    v1_10 = data_3d[it + 1, iy + 1, ix]
    v1_01 = data_3d[it + 1, iy, ix + 1]
    v1_11 = data_3d[it + 1, iy + 1, ix + 1]
    f1 = (1.0 - ty) * (1.0 - tx) * v1_00 + ty * (1.0 - tx) * v1_10 + (1.0 - ty) * tx * v1_01 + ty * tx * v1_11

    val = (1.0 - tt) * f0 + tt * f1
    return float(val)


class EnvironmentalInterpolator:
    """
    Spatiotemporal interpolator for combined ocean current and wind forcing fields.
    """

    def __init__(
        self,
        era5_path: Optional[str] = None,
        oscar_path: Optional[str] = None,
        default_windage: float = 0.03,
        default_deflection_deg: float = 0.0,
    ):
        self.era5_path = era5_path
        self.oscar_path = oscar_path
        self.default_windage = default_windage
        self.default_deflection_deg = default_deflection_deg

        self._era5_times = None
        self._era5_lats = None
        self._era5_lons = None
        self._era5_u10 = None
        self._era5_v10 = None

        self._oscar_lons = None
        self._oscar_lats = None
        self._oscar_u = None
        self._oscar_v = None

        if era5_path:
            self._load_era5(era5_path)
        if oscar_path:
            self._load_oscar(oscar_path)

    def _load_era5(self, path: str):
        ds = xr.open_dataset(path)
        t_var = "valid_time" if "valid_time" in ds.coords else "time"
        
        self._era5_times = pd.to_datetime(ds[t_var].values).astype("int64") // 10**9  # epoch seconds
        lats = ds["latitude"].values.astype(float)
        lons = ds["longitude"].values.astype(float)

        # Sort coordinates to be monotonically increasing
        if lats[1] < lats[0]:
            self._era5_lats = lats[::-1]
            u10_raw = ds["u10"].values[:, ::-1, :]
            v10_raw = ds["v10"].values[:, ::-1, :]
        else:
            self._era5_lats = lats
            u10_raw = ds["u10"].values
            v10_raw = ds["v10"].values

        self._era5_lons = lons

        # Squeeze singleton dimension if present
        if u10_raw.ndim == 4:
            u10_raw = u10_raw[:, 0, :, :]
            v10_raw = v10_raw[:, 0, :, :]

        self._era5_u10 = np.nan_to_num(u10_raw, nan=0.0).astype(float)
        self._era5_v10 = np.nan_to_num(v10_raw, nan=0.0).astype(float)
        ds.close()

    def _load_oscar(self, path: str):
        ds = xr.open_dataset(path)
        lats = ds["lat"].values.astype(float) if "lat" in ds else ds["latitude"].values.astype(float)
        lons = ds["lon"].values.astype(float) if "lon" in ds else ds["longitude"].values.astype(float)

        u_raw = ds["u"].values
        v_raw = ds["v"].values

        if u_raw.ndim == 3:
            u_raw = u_raw[0]
            v_raw = v_raw[0]

        self._oscar_lons = lons
        self._oscar_lats = lats
        self._oscar_u = np.nan_to_num(u_raw, nan=0.0).astype(float)
        self._oscar_v = np.nan_to_num(v_raw, nan=0.0).astype(float)
        ds.close()

    def _to_epoch(self, timestamp: Union[str, pd.Timestamp, np.datetime64, float, int]) -> float:
        if isinstance(timestamp, (int, float)):
            return float(timestamp)
        ts = pd.to_datetime(timestamp)
        return float(ts.timestamp())

    def interpolate_wind(
        self,
        lon: float,
        lat: float,
        timestamp: Union[str, float],
        fallback_nearest: bool = True,
    ) -> Tuple[float, float]:
        """
        Interpolate 10m wind velocity (u, v) in m/s using 3D trilinear interpolation.
        """
        if self._era5_u10 is None:
            return 0.0, 0.0

        t_epoch = self._to_epoch(timestamp)

        in_lon = (self._era5_lons[0] <= lon <= self._era5_lons[-1])
        in_lat = (self._era5_lats[0] <= lat <= self._era5_lats[-1])
        in_time = (self._era5_times[0] <= t_epoch <= self._era5_times[-1])

        if not (in_lon and in_lat and in_time):
            if not fallback_nearest:
                return 0.0, 0.0
            lon = float(np.clip(lon, self._era5_lons[0], self._era5_lons[-1]))
            lat = float(np.clip(lat, self._era5_lats[0], self._era5_lats[-1]))
            t_epoch = float(np.clip(t_epoch, self._era5_times[0], self._era5_times[-1]))

        u = trilinear_interp_3d(self._era5_times, self._era5_lats, self._era5_lons, self._era5_u10, t_epoch, lat, lon)
        v = trilinear_interp_3d(self._era5_times, self._era5_lats, self._era5_lons, self._era5_v10, t_epoch, lat, lon)
        return u, v

    def interpolate_current(
        self,
        lon: float,
        lat: float,
        fallback_nearest: bool = True,
    ) -> Tuple[float, float]:
        """
        Interpolate ocean surface current velocity (u, v) in m/s using 2D bilinear interpolation.
        """
        if self._oscar_u is None:
            return 0.0, 0.0

        lon_360 = float(lon % 360.0)

        in_lon = (self._oscar_lons[0] <= lon_360 <= self._oscar_lons[-1])
        in_lat = (self._oscar_lats[0] <= lat <= self._oscar_lats[-1])

        if not (in_lon and in_lat):
            if not fallback_nearest:
                return 0.0, 0.0
            lon_360 = float(np.clip(lon_360, self._oscar_lons[0], self._oscar_lons[-1]))
            lat = float(np.clip(lat, self._oscar_lats[0], self._oscar_lats[-1]))

        u = bilinear_interp_2d(self._oscar_lons, self._oscar_lats, self._oscar_u, lon_360, lat)
        v = bilinear_interp_2d(self._oscar_lons, self._oscar_lats, self._oscar_v, lon_360, lat)
        return u, v

    def get_advective_velocity(
        self,
        lon: float,
        lat: float,
        timestamp: Union[str, float],
        windage: Optional[float] = None,
        deflection_deg: Optional[float] = None,
    ) -> Tuple[float, float]:
        """
        Compute total surface advective velocity vector (u_total, v_total) in m/s:
        V = u_current + windage * R(theta) * u_wind
        """
        cw = self.default_windage if windage is None else windage
        theta_deg = self.default_deflection_deg if deflection_deg is None else deflection_deg

        u_curr, v_curr = self.interpolate_current(lon, lat)
        u_wind, v_wind = self.interpolate_wind(lon, lat, timestamp)

        theta_rad = np.radians(theta_deg)
        cos_t = np.cos(theta_rad)
        sin_t = np.sin(theta_rad)

        # Deflected wind
        u_wind_deflected = u_wind * cos_t - v_wind * sin_t
        v_wind_deflected = u_wind * sin_t + v_wind * cos_t

        u_total = u_curr + cw * u_wind_deflected
        v_total = v_curr + cw * v_wind_deflected

        return u_total, v_total
