"""
Uncertainty Quantification and Spatial Dispersion Cones.

Models stochastic turbulent diffusion, environmental forcing perturbation,
and leeway variability using Monte Carlo ensembles to generate:
- Time-dependent uncertainty cones and convex hulls
- 2D spatial probability density rasters
- Multi-tier confidence regions (e.g. 50%, 80%, 95%)
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import shapely.geometry
from shapely.geometry import MultiPoint, Polygon, mapping


class UncertaintyConeGenerator:
    """
    Generates spatiotemporal uncertainty bounding geometries, convex hulls,
    and probability rasters for hindcasted particle clouds.
    """

    def __init__(self, horizontal_diffusivity_kh: float = 10.0):
        """
        Args:
            horizontal_diffusivity_kh: Horizontal turbulent diffusion coefficient (m²/s).
        """
        self.kh = horizontal_diffusivity_kh

    def build_confidence_polygon(
        self,
        particle_positions: Union[List[Tuple[float, float]], np.ndarray],
        confidence_level: float = 0.95,
        buffer_degrees: float = 0.005,
    ) -> Dict[str, Any]:
        """
        Compute minimum enclosing convex hull or buffered contour enclosing
        the target confidence quantile of particles.

        Args:
            particle_positions: Array-like of (longitude, latitude) or (latitude, longitude).
            confidence_level: Fraction of particles enclosed (e.g. 0.95 for 95%).
            buffer_degrees: Small buffer expansion around hull (degrees).

        Returns:
            Dictionary with GeoJSON polygon geometry, bounds, centroid, and particle count.
        """
        pts = np.asarray(particle_positions)
        if len(pts) == 0:
            raise ValueError("particle_positions cannot be empty")

        if len(pts) < 3:
            # Fallback for 1-2 points: expand into a small bounding box
            center_x, center_y = float(pts[:, 0].mean()), float(pts[:, 1].mean())
            delta = max(buffer_degrees, 0.01)
            poly = Polygon([
                (center_x - delta, center_y - delta),
                (center_x + delta, center_y - delta),
                (center_x + delta, center_y + delta),
                (center_x - delta, center_y + delta),
            ])
            return {
                "type": "Feature",
                "geometry": mapping(poly),
                "confidence_level": confidence_level,
                "particle_count": len(pts),
                "centroid": [center_x, center_y],
                "bounds": list(poly.bounds),
                "shapely_polygon": poly,
            }

        # Filter to the central (1 - confidence_level) quantile by distance from median
        center = np.median(pts, axis=0)
        dists = np.hypot(pts[:, 0] - center[0], pts[:, 1] - center[1])
        cutoff = np.percentile(dists, confidence_level * 100.0)
        inlier_mask = dists <= cutoff
        inlier_pts = pts[inlier_mask]

        if len(inlier_pts) < 3:
            inlier_pts = pts

        mp = MultiPoint(inlier_pts)
        hull = mp.convex_hull
        if buffer_degrees > 0.0:
            hull = hull.buffer(buffer_degrees)

        if not isinstance(hull, Polygon):
            hull = hull.convex_hull

        return {
            "type": "Feature",
            "geometry": mapping(hull),
            "confidence_level": confidence_level,
            "particle_count": int(np.sum(inlier_mask)),
            "total_particles": len(pts),
            "centroid": [float(center[0]), float(center[1])],
            "bounds": [float(b) for b in hull.bounds],
            "shapely_polygon": hull,
        }

    def compute_probability_raster(
        self,
        particle_positions: Union[List[Tuple[float, float]], np.ndarray],
        grid_resolution_deg: float = 0.02,
        padding_deg: float = 0.05,
    ) -> Dict[str, Any]:
        """
        Compute a 2D spatial probability density raster normalized to sum to 1.0.

        Args:
            particle_positions: Array-like of (longitude, latitude).
            grid_resolution_deg: Cell size in degrees.
            padding_deg: Boundary margin around particles.

        Returns:
            Dictionary with 2D probability grid, lon/lat coordinates, and peak density.
        """
        pts = np.asarray(particle_positions)
        min_lon, max_lon = pts[:, 0].min() - padding_deg, pts[:, 0].max() + padding_deg
        min_lat, max_lat = pts[:, 1].min() - padding_deg, pts[:, 1].max() + padding_deg

        lon_bins = np.arange(min_lon, max_lon + grid_resolution_deg, grid_resolution_deg)
        lat_bins = np.arange(min_lat, max_lat + grid_resolution_deg, grid_resolution_deg)

        counts, _, _ = np.histogram2d(pts[:, 0], pts[:, 1], bins=[lon_bins, lat_bins])
        total = counts.sum()
        prob_density = counts / total if total > 0 else counts

        lon_centers = 0.5 * (lon_bins[:-1] + lon_bins[1:])
        lat_centers = 0.5 * (lat_bins[:-1] + lat_bins[1:])

        # Find peak
        max_idx = np.unravel_index(np.argmax(prob_density), prob_density.shape)
        peak_lon = float(lon_centers[max_idx[0]])
        peak_lat = float(lat_centers[max_idx[1]])

        return {
            "lon_bins": lon_bins,
            "lat_bins": lat_bins,
            "lon_centers": lon_centers,
            "lat_centers": lat_centers,
            "probability_grid": prob_density,
            "peak_density": float(prob_density.max()),
            "peak_coordinate": (peak_lon, peak_lat),
            "bounds": [float(min_lon), float(min_lat), float(max_lon), float(max_lat)],
        }


def compute_monte_carlo_dispersion(
    base_velocity: Tuple[float, float],
    kh: float,
    dt: float,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[float, float]:
    """
    Compute random-walk turbulent velocity perturbation:
    u' = sqrt(2 * Kh / |dt|) * N(0, 1)

    Args:
        base_velocity: Advective velocity vector (u, v) in m/s.
        kh: Horizontal eddy diffusivity (m²/s).
        dt: Timestep in seconds.
        rng: Optional NumPy random generator.

    Returns:
        Perturbed velocity vector (u_stochastic, v_stochastic) in m/s.
    """
    if rng is None:
        rng = np.random.default_rng()
    if kh <= 0.0 or abs(dt) <= 0.0:
        return base_velocity

    sigma = np.sqrt(2.0 * kh / abs(dt))
    u_pert = rng.normal(0.0, sigma)
    v_pert = rng.normal(0.0, sigma)
    return base_velocity[0] + u_pert, base_velocity[1] + v_pert
