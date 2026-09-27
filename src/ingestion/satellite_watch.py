"""
Satellite Watcher and Ingestion Monitor.

Monitors satellite product catalogs for newly available Sentinel-1 SAR observations
over a configured maritime area of interest (AOI).
Supports:
1. Real Copernicus Data Space OData API (CopernicusSentinel1Provider)
2. Deterministic recorded fixtures (FixtureCatalogProvider) for offline reproducibility
3. Persistent Ingestion Ledger tracking states: DISCOVERED, DOWNLOADED, PROCESSED, REJECTED, FAILED

Emits canonical normalized watch events:
- NEW_SATELLITE_PRODUCT
- NO_NEW_SATELLITE_PRODUCT
- SATELLITE_PROVIDER_ERROR
- SATELLITE_AUTH_REQUIRED
- DUPLICATE_SATELLITE_PRODUCT
"""

from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import time

from src.ingestion.ledger import IngestionLedger, IngestionStatus
from src.ingestion.sentinel1_provider import (
    CopernicusSentinel1Provider,
    ProviderStatus,
    Sentinel1ProductMetadata,
)


class SatelliteWatchStatus(str, Enum):
    """Catalog query status flags (backwards compatible)."""
    NEW_PRODUCT = "NEW_PRODUCT"
    NO_NEW_PRODUCT = "NO_NEW_PRODUCT"
    DUPLICATE_PRODUCT = "DUPLICATE_PRODUCT"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    AUTH_ERROR = "AUTH_ERROR"


class WatchEvent(str, Enum):
    """Canonical event types emitted by the Continuous Maritime Watch layer."""
    NEW_SATELLITE_PRODUCT = "NEW_SATELLITE_PRODUCT"
    NO_NEW_SATELLITE_PRODUCT = "NO_NEW_SATELLITE_PRODUCT"
    SATELLITE_PROVIDER_ERROR = "SATELLITE_PROVIDER_ERROR"
    SATELLITE_AUTH_REQUIRED = "SATELLITE_AUTH_REQUIRED"
    DUPLICATE_SATELLITE_PRODUCT = "DUPLICATE_SATELLITE_PRODUCT"


class SatelliteCatalogProvider(ABC):
    """Abstract interface for querying Earth observation catalogs."""

    @abstractmethod
    def query_catalog(
        self,
        bounding_box: Tuple[float, float, float, float],
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Query provider catalog and return list of product metadata dictionaries."""
        pass


class FixtureCatalogProvider(SatelliteCatalogProvider):
    """
    Deterministic catalog provider reading from local fixture files or memory.
    """

    def __init__(self, fixtures: Optional[List[Dict[str, Any]]] = None, fixture_path: Optional[Union[str, Path]] = None):
        self.products: List[Dict[str, Any]] = []
        if fixtures is not None:
            self.products.extend(fixtures)
        if fixture_path is not None:
            p = Path(fixture_path)
            if p.exists():
                import json
                with open(p) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self.products.extend(data)
                    elif isinstance(data, dict):
                        self.products.append(data)

    def add_product(self, product_metadata: Dict[str, Any]) -> None:
        self.products.append(product_metadata)

    def query_catalog(
        self,
        bounding_box: Tuple[float, float, float, float],
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        return list(self.products)


class SatelliteWatcher:
    """
    Continuous watcher querying Copernicus Data Space or fixture catalogs
    and tracking product ingestion state using the persistent IngestionLedger.
    """

    def __init__(
        self,
        catalog_provider: Optional[Union[SatelliteCatalogProvider, CopernicusSentinel1Provider]] = None,
        ledger: Optional[IngestionLedger] = None,
        ledger_path: Optional[Union[str, Path]] = None,
        region_bbox: Tuple[float, float, float, float] = (18.1, 34.3, 18.6, 34.7),
    ):
        if catalog_provider is not None:
            self.catalog_provider = catalog_provider
        else:
            self.catalog_provider = CopernicusSentinel1Provider()

        if ledger is not None:
            self.ledger = ledger
        elif ledger_path is not None:
            self.ledger = IngestionLedger(ledger_path)
        else:
            self.ledger = IngestionLedger(None)

        self.region_bbox = region_bbox

    def check_for_new_products(
        self,
        bounding_box: Optional[Tuple[float, float, float, float]] = None,
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
    ) -> Tuple[SatelliteWatchStatus, Optional[Dict[str, Any]]]:
        """
        Poll catalog provider for new satellite products over the AOI.

        Returns:
            Tuple of (SatelliteWatchStatus, Optional product metadata dict).
        """
        bbox = bounding_box or self.region_bbox

        # 1. Query Provider
        if isinstance(self.catalog_provider, CopernicusSentinel1Provider):
            status, products, err_msg = self.catalog_provider.search_products(
                bbox=bbox,
                start_time_iso=start_time_iso,
                end_time_iso=end_time_iso,
            )
            if status == ProviderStatus.AUTH_REQUIRED:
                return SatelliteWatchStatus.AUTH_ERROR, None
            elif status == ProviderStatus.AUTH_ERROR:
                return SatelliteWatchStatus.AUTH_ERROR, None
            elif status == ProviderStatus.NETWORK_ERROR or status == ProviderStatus.PROVIDER_ERROR:
                return SatelliteWatchStatus.PROVIDER_ERROR, None
            elif status == ProviderStatus.NO_RESULTS or not products:
                return SatelliteWatchStatus.NO_NEW_PRODUCT, None

            product_dicts = [p.to_dict() for p in products]
            source_name = "Copernicus Data Space"
        else:
            # Fallback to SatelliteCatalogProvider interface (e.g. FixtureCatalogProvider)
            try:
                raw_prods = self.catalog_provider.query_catalog(
                    bounding_box=bbox,
                    start_time_iso=start_time_iso,
                    end_time_iso=end_time_iso,
                )
                if not raw_prods:
                    return SatelliteWatchStatus.NO_NEW_PRODUCT, None
                product_dicts = list(raw_prods)
                source_name = "Fixture Catalog"
            except PermissionError:
                return SatelliteWatchStatus.AUTH_ERROR, None
            except Exception as e:
                err_str = str(e).lower()
                if "auth" in err_str or "unauthorized" in err_str or "forbidden" in err_str:
                    return SatelliteWatchStatus.AUTH_ERROR, None
                return SatelliteWatchStatus.PROVIDER_ERROR, None

        # 2. Check Products against Ingestion Ledger
        for prod in product_dicts:
            pid = prod.get("product_id")
            if not pid:
                continue

            if not self.ledger.is_seen(pid):
                # Genuinely new product discovered
                self.ledger.record_discovery(
                    product_id=pid,
                    product_name=prod.get("product_name", pid),
                    acquisition_start=prod.get("acquisition_start", ""),
                    acquisition_end=prod.get("acquisition_end", ""),
                    spatial_bbox=prod.get("spatial_bbox") or bbox,
                    source_provider=source_name,
                )
                return SatelliteWatchStatus.NEW_PRODUCT, prod

        # All products returned have already been discovered
        return SatelliteWatchStatus.DUPLICATE_PRODUCT, product_dicts[0]

    def poll_and_emit_event(
        self,
        bounding_box: Optional[Tuple[float, float, float, float]] = None,
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
    ) -> Tuple[WatchEvent, Optional[Dict[str, Any]]]:
        """
        Poll catalog and emit canonical WatchEvent enum.
        """
        status, prod = self.check_for_new_products(
            bounding_box=bounding_box,
            start_time_iso=start_time_iso,
            end_time_iso=end_time_iso,
        )

        mapping = {
            SatelliteWatchStatus.NEW_PRODUCT: WatchEvent.NEW_SATELLITE_PRODUCT,
            SatelliteWatchStatus.NO_NEW_PRODUCT: WatchEvent.NO_NEW_SATELLITE_PRODUCT,
            SatelliteWatchStatus.DUPLICATE_PRODUCT: WatchEvent.DUPLICATE_SATELLITE_PRODUCT,
            SatelliteWatchStatus.PROVIDER_ERROR: WatchEvent.SATELLITE_PROVIDER_ERROR,
            SatelliteWatchStatus.AUTH_ERROR: WatchEvent.SATELLITE_AUTH_REQUIRED,
        }

        event = mapping.get(status, WatchEvent.SATELLITE_PROVIDER_ERROR)
        return event, prod
