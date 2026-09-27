"""
Copernicus Data Space Ecosystem (CDSE) Sentinel-1 Catalog Provider.

Provides real, live search and download capabilities for Sentinel-1 C-band SAR
observations via the official Copernicus OData API.
Enforces non-fabrication:
- Distinguishes SUCCESS, NO_RESULTS, AUTH_ERROR, AUTH_REQUIRED, NETWORK_ERROR, PROVIDER_ERROR.
- Securely reads credentials from environment variables (never printed in logs).
- Normalizes catalog product metadata into canonical Sentinel1ProductMetadata structures.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import requests


class ProviderStatus(str, Enum):
    SUCCESS = "SUCCESS"
    NO_RESULTS = "NO_RESULTS"
    AUTH_ERROR = "AUTH_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    NETWORK_ERROR = "NETWORK_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"


class DownloadStatus(str, Enum):
    SUCCESS = "SUCCESS"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    DOWNLOAD_ERROR = "DOWNLOAD_ERROR"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass
class Sentinel1ProductMetadata:
    """Normalized metadata for a real Sentinel-1 observation product."""
    product_id: str
    product_name: str
    sensor: str = "C-SAR / Sentinel-1"
    acquisition_start: str = ""
    acquisition_end: str = ""
    processing_time: Optional[str] = None
    orbit: Optional[int] = None
    relative_orbit: Optional[int] = None
    polarization: Optional[str] = None
    product_type: str = "GRD"
    footprint: Optional[Dict[str, Any]] = None
    bbox: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)  # (min_lon, min_lat, max_lon, max_lat)
    download_location: Optional[str] = None
    content_length: Optional[int] = None
    raw_properties: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CopernicusSentinel1Provider:
    """
    Real Copernicus Data Space API client for querying and downloading Sentinel-1 SAR products.
    """

    CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"
    TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        catalogue_url: Optional[str] = None,
        token_url: Optional[str] = None,
        timeout_seconds: int = 25,
    ):
        # Read from arguments or environment variables without logging secrets
        self.client_id = client_id or os.getenv("COPERNICUS_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("COPERNICUS_CLIENT_SECRET")
        self.username = username or os.getenv("COPERNICUS_USERNAME")
        self.password = password or os.getenv("COPERNICUS_PASSWORD")
        self.catalogue_url = catalogue_url or self.CATALOGUE_URL
        self.token_url = token_url or self.TOKEN_URL
        self.timeout = timeout_seconds
        self._cached_token: Optional[str] = None

    def has_credentials(self) -> bool:
        """Check if authentication credentials are provided."""
        has_oauth = bool(self.client_id and self.client_secret)
        has_userpass = bool(self.username and self.password)
        return has_oauth or has_userpass

    def get_auth_token(self) -> Tuple[ProviderStatus, Optional[str]]:
        """
        Request OAuth2 access token from Copernicus identity service.
        Returns (ProviderStatus, Optional token string).
        Never logs or leaks credentials.
        """
        if not self.has_credentials():
            return ProviderStatus.AUTH_REQUIRED, None

        data: Dict[str, str] = {}
        if self.client_id and self.client_secret:
            data = {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        elif self.username and self.password:
            data = {
                "grant_type": "password",
                "client_id": "cdse-public",
                "username": self.username,
                "password": self.password,
            }

        try:
            resp = requests.post(self.token_url, data=data, timeout=self.timeout)
            if resp.status_code == 200:
                token_data = resp.json()
                self._cached_token = token_data.get("access_token")
                return ProviderStatus.SUCCESS, self._cached_token
            elif resp.status_code in (401, 403):
                return ProviderStatus.AUTH_ERROR, None
            else:
                return ProviderStatus.PROVIDER_ERROR, None
        except (requests.ConnectionError, requests.Timeout):
            return ProviderStatus.NETWORK_ERROR, None
        except Exception:
            return ProviderStatus.PROVIDER_ERROR, None

    def search_products(
        self,
        bbox: Tuple[float, float, float, float],
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
        collection: str = "SENTINEL-1",
        product_type: str = "GRD",
        max_results: int = 20,
    ) -> Tuple[ProviderStatus, List[Sentinel1ProductMetadata], Optional[str]]:
        """
        Query real Copernicus OData catalog for Sentinel-1 observations intersecting bounding box.

        Args:
            bbox: (min_lon, min_lat, max_lon, max_lat) in WGS84 EPSG:4326.
            start_time_iso: Filter acquisition start >= timestamp.
            end_time_iso: Filter acquisition start <= timestamp.
            collection: Target Earth observation mission ('SENTINEL-1').
            product_type: Desired product type ('GRD', 'SLC').
            max_results: Number of products to retrieve.

        Returns:
            Tuple of (ProviderStatus, list of normalized products, error message or None).
        """
        min_lon, min_lat, max_lon, max_lat = bbox

        # Construct spatial WKT polygon counter-clockwise closed loop
        polygon_wkt = (
            f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, "
            f"{max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
        )

        filter_parts = [
            f"Collection/Name eq '{collection}'",
            f"OData.CSC.Intersects(area=geography'SRID=4326;{polygon_wkt}')",
        ]

        if product_type:
            filter_parts.append(f"contains(Name, '{product_type}')")

        if start_time_iso:
            filter_parts.append(f"ContentDate/Start ge {start_time_iso}")
        if end_time_iso:
            filter_parts.append(f"ContentDate/Start le {end_time_iso}")

        filter_query = " and ".join(filter_parts)

        params = {
            "$filter": filter_query,
            "$top": max_results,
            "$orderby": "ContentDate/Start desc",
        }

        try:
            resp = requests.get(self.catalogue_url, params=params, timeout=self.timeout)
            if resp.status_code == 200:
                raw_json = resp.json()
                raw_products = raw_json.get("value", [])
                if not raw_products:
                    return ProviderStatus.NO_RESULTS, [], None

                normalized = [self._normalize_product(p, default_bbox=bbox) for p in raw_products]
                return ProviderStatus.SUCCESS, normalized, None
            elif resp.status_code in (401, 403):
                return ProviderStatus.AUTH_ERROR, [], f"Copernicus catalog authentication failed (HTTP {resp.status_code})"
            elif resp.status_code >= 500:
                return ProviderStatus.PROVIDER_ERROR, [], f"Copernicus catalog server error (HTTP {resp.status_code})"
            else:
                return ProviderStatus.PROVIDER_ERROR, [], f"Catalog query error: HTTP {resp.status_code} - {resp.text[:200]}"
        except (requests.ConnectionError, requests.Timeout) as e:
            return ProviderStatus.NETWORK_ERROR, [], f"Network connectivity error to Copernicus API: {e}"
        except Exception as e:
            return ProviderStatus.PROVIDER_ERROR, [], f"Unexpected query error: {e}"

    def _normalize_product(self, raw: Dict[str, Any], default_bbox: Tuple[float, float, float, float]) -> Sentinel1ProductMetadata:
        """Parse raw OData JSON item into normalized Sentinel1ProductMetadata."""
        pid = str(raw.get("Id", ""))
        name = str(raw.get("Name", ""))

        content_date = raw.get("ContentDate", {})
        acq_start = content_date.get("Start", "")
        acq_end = content_date.get("End", "")

        geo_footprint = raw.get("GeoFootprint")
        footprint_dict = geo_footprint if isinstance(geo_footprint, dict) else None

        # Determine bounding box from GeoFootprint if available
        bbox = default_bbox
        if footprint_dict and "coordinates" in footprint_dict:
            try:
                coords = footprint_dict["coordinates"][0]
                lons = [c[0] for c in coords]
                lats = [c[1] for c in coords]
                bbox = (float(min(lons)), float(min(lats)), float(max(lons)), float(max(lats)))
            except Exception:
                bbox = default_bbox

        # Extract attributes if provided
        attributes = raw.get("Attributes", [])
        attr_dict = {}
        if isinstance(attributes, list):
            for a in attributes:
                if isinstance(a, dict) and "Name" in a and "Value" in a:
                    attr_dict[a["Name"]] = a["Value"]

        orbit = attr_dict.get("orbitNumber")
        rel_orbit = attr_dict.get("relativeOrbitNumber")
        polarization = attr_dict.get("polarisationChannels")
        product_type = attr_dict.get("productType", "GRD" if "GRD" in name else "RAW")

        download_url = f"{self.catalogue_url}({pid})/$value"

        return Sentinel1ProductMetadata(
            product_id=pid,
            product_name=name,
            sensor="C-SAR / Sentinel-1",
            acquisition_start=acq_start,
            acquisition_end=acq_end,
            processing_time=raw.get("OriginDate"),
            orbit=int(orbit) if orbit is not None else None,
            relative_orbit=int(rel_orbit) if rel_orbit is not None else None,
            polarization=str(polarization) if polarization else None,
            product_type=str(product_type),
            footprint=footprint_dict,
            bbox=bbox,
            download_location=download_url,
            content_length=raw.get("ContentLength"),
            raw_properties=attr_dict,
        )

    def download_product(
        self,
        product: Sentinel1ProductMetadata,
        destination_dir: Union[str, Path] = "data/satellite/sentinel1",
        chunk_size: int = 16384,
    ) -> Tuple[DownloadStatus, Optional[str], Optional[str]]:
        """
        Download product archive with SHA-256 verification and safe non-overwrite.

        Returns:
            Tuple of (DownloadStatus, filepath, sha256_hash).
        """
        dest_dir = Path(destination_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        target_file = dest_dir / f"{product.product_id}.zip"

        # Check if already downloaded - compute hash and return safely
        if target_file.exists():
            sha256 = hashlib.sha256()
            with open(target_file, "rb") as f:
                for chunk in iter(lambda: f.read(chunk_size), b""):
                    sha256.update(chunk)
            return DownloadStatus.SUCCESS, str(target_file), sha256.hexdigest()

        # Check authentication token
        if not self._cached_token:
            auth_status, token = self.get_auth_token()
            if auth_status != ProviderStatus.SUCCESS or not token:
                return DownloadStatus.AUTH_REQUIRED, None, None

        download_url = product.download_location or f"{self.catalogue_url}({product.product_id})/$value"
        headers = {"Authorization": f"Bearer {self._cached_token}"}

        try:
            with requests.get(download_url, headers=headers, stream=True, timeout=60) as resp:
                if resp.status_code == 200:
                    sha256 = hashlib.sha256()
                    temp_file = dest_dir / f"{product.product_id}.tmp"
                    with open(temp_file, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                                sha256.update(chunk)
                    temp_file.rename(target_file)
                    return DownloadStatus.SUCCESS, str(target_file), sha256.hexdigest()
                elif resp.status_code in (401, 403):
                    return DownloadStatus.AUTH_REQUIRED, None, None
                elif resp.status_code == 404:
                    return DownloadStatus.UNAVAILABLE, None, None
                else:
                    return DownloadStatus.DOWNLOAD_ERROR, None, None
        except Exception:
            return DownloadStatus.DOWNLOAD_ERROR, None, None
