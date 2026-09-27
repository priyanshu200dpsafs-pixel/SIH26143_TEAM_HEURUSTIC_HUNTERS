"""
Live Maritime AIS Provider Interface.

Connects to authenticated external maritime transponder streaming or REST services.
Pluggable architecture supporting multiple data providers (Generic REST, AISStream, Spire, etc.)
Strict security rules:
- No hardcoded secrets
- Credentials loaded only via environment variables or secure configuration
- Secrets never exposed in logs or exceptions
- If unconfigured, explicitly reports NOT_CONFIGURED (never fabricates synthetic data).
- Emitted records strictly labeled: data_status='REAL', mode='LIVE'.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import requests

from src.ingestion.ais.base_provider import AISProvider
from src.ingestion.ais.models import AISObservation, VesselTrack, ProviderStatus
from src.ais_analysis.track_builder import normalize_raw_observation, build_track

logger = logging.getLogger(__name__)


class LiveAISProvider(AISProvider):
    """
    Provider-agnostic live AIS ingestion adapter.
    """

    def __init__(
        self,
        provider_name: Optional[str] = None,
        api_url: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout_seconds: int = 15,
        session: Optional[requests.Session] = None,
    ):
        self.provider_name = (
            provider_name
            or os.getenv("AIS_PROVIDER")
            or "generic_rest"
        )
        self.api_url = (
            api_url
            or os.getenv("AIS_API_URL")
            or ""
        ).strip()
        self._api_key = (
            api_key
            or os.getenv("AIS_API_KEY")
            or ""
        ).strip()
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()
        self._data_status = "REAL"
        self._mode = "LIVE"

    @property
    def data_status(self) -> str:
        return self._data_status

    @property
    def mode(self) -> str:
        return self._mode

    def is_configured(self) -> bool:
        """Return True only if endpoint and credentials exist."""
        return bool(self.api_url and self._api_key)

    def get_status(self) -> ProviderStatus:
        """
        Evaluate connectivity and credentials against live provider.
        Returns one of: CONNECTED, AUTH_REQUIRED, NOT_CONFIGURED, PROVIDER_ERROR, NETWORK_ERROR, RATE_LIMITED.
        """
        if not self.is_configured():
            return ProviderStatus.NOT_CONFIGURED

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": "OilSpillAttribution-LiveAIS/1.0",
        }

        try:
            # Query health or ping endpoint
            health_url = f"{self.api_url.rstrip('/')}/health" if not self.api_url.endswith("/health") else self.api_url
            resp = self.session.get(health_url, headers=headers, timeout=self.timeout_seconds)

            if resp.status_code == 200:
                return ProviderStatus.CONNECTED
            elif resp.status_code in (401, 403):
                return ProviderStatus.AUTH_REQUIRED
            elif resp.status_code == 429:
                return ProviderStatus.RATE_LIMITED
            elif 500 <= resp.status_code < 600:
                return ProviderStatus.PROVIDER_ERROR
            else:
                # If health endpoint not supported, check base query endpoint with head
                base_resp = self.session.head(self.api_url, headers=headers, timeout=self.timeout_seconds)
                if base_resp.status_code in (200, 204):
                    return ProviderStatus.CONNECTED
                elif base_resp.status_code in (401, 403):
                    return ProviderStatus.AUTH_REQUIRED
                return ProviderStatus.PROVIDER_ERROR

        except requests.exceptions.Timeout:
            logger.warning("[AIS] Connection timeout to live AIS provider")
            return ProviderStatus.NETWORK_ERROR
        except requests.exceptions.ConnectionError:
            logger.warning("[AIS] Network connection error to live AIS provider")
            return ProviderStatus.NETWORK_ERROR
        except Exception as e:
            logger.error(f"[AIS] Unexpected error during status check: {type(e).__name__}")
            return ProviderStatus.PROVIDER_ERROR

    def get_positions(
        self,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
        mmsi: Optional[Union[str, int]] = None,
    ) -> List[AISObservation]:
        """
        Query live AIS observations from provider.
        Returns empty list if unconfigured or on error (never fabricates data).
        """
        if not self.is_configured():
            logger.info("[AIS] Live AIS provider not configured; 0 live observations retrieved")
            return []

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "User-Agent": "OilSpillAttribution-LiveAIS/1.0",
        }

        params: Dict[str, Any] = {}
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            params["min_lon"] = min_lon
            params["min_lat"] = min_lat
            params["max_lon"] = max_lon
            params["max_lat"] = max_lat
        if start_time_iso:
            params["start_time"] = start_time_iso
        if end_time_iso:
            params["end_time"] = end_time_iso
        if mmsi is not None:
            params["mmsi"] = str(mmsi)

        try:
            resp = self.session.get(
                self.api_url,
                headers=headers,
                params=params,
                timeout=self.timeout_seconds,
            )

            if resp.status_code != 200:
                logger.warning(f"[AIS] Live provider returned status {resp.status_code}")
                return []

            data = resp.json()
            raw_list = data if isinstance(data, list) else data.get("data", data.get("records", []))

            observations: List[AISObservation] = []
            for item in raw_list:
                obs = normalize_raw_observation(
                    raw=item,
                    source=self.provider_name,
                    data_status=self.data_status,
                    mode=self.mode,
                )
                if obs:
                    observations.append(obs)

            return observations

        except Exception as e:
            logger.error(f"[AIS] Failed to fetch live positions: {type(e).__name__}")
            return []

    def get_track(
        self,
        mmsi: Union[str, int],
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
    ) -> Optional[VesselTrack]:
        """Retrieve track for a single vessel from live stream."""
        obs = self.get_positions(
            mmsi=mmsi,
            start_time_iso=start_time_iso,
            end_time_iso=end_time_iso,
        )
        if not obs:
            return None
        return build_track(obs)

    def get_tracks(
        self,
        mmsis: Optional[List[Union[str, int]]] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
    ) -> List[VesselTrack]:
        """Retrieve tracks for all vessels in the AOI/window."""
        obs_list = self.get_positions(
            bbox=bbox,
            start_time_iso=start_time_iso,
            end_time_iso=end_time_iso,
        )
        if not obs_list:
            return []

        by_mmsi: Dict[str, List[AISObservation]] = {}
        for o in obs_list:
            if mmsis is not None and str(o.mmsi) not in [str(m) for m in mmsis]:
                continue
            by_mmsi.setdefault(o.mmsi, []).append(o)

        tracks = []
        for mmsi_key, v_obs in by_mmsi.items():
            tracks.append(build_track(v_obs))

        return tracks

    def get_vessel_static_data(self, mmsi: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Query static ship registry particulars if supported by provider."""
        if not self.is_configured():
            return None

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
        }
        url = f"{self.api_url.rstrip('/')}/vessel/{mmsi}"

        try:
            resp = self.session.get(url, headers=headers, timeout=self.timeout_seconds)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "mmsi": str(mmsi),
                    "ship_name": data.get("name") or data.get("ship_name"),
                    "ship_type": data.get("type") or data.get("ship_type"),
                    "imo": data.get("imo"),
                    "length": data.get("length"),
                    "beam": data.get("beam"),
                    "draft": data.get("draft"),
                    "source": self.provider_name,
                    "data_status": self.data_status,
                    "mode": self.mode,
                }
        except Exception:
            pass
        return None
