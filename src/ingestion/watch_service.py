"""
Continuous Maritime Watch Service.

Executes autonomous surveillance loop monitoring configured areas of interest (AOI)
for newly available Sentinel-1 SAR observations.
Handles catalog polling, metadata validation, ledger registration, optional product download,
raster compatibility assessment, and automated incident pipeline triggering.
Supports clean, graceful shutdown via thread event flags.
"""

from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import yaml

from src.ingestion.ledger import IngestionLedger, IngestionStatus
from src.ingestion.sentinel1_provider import CopernicusSentinel1Provider, DownloadStatus
from src.ingestion.satellite_watch import (
    SatelliteWatcher,
    SatelliteWatchStatus,
    WatchEvent,
    SatelliteCatalogProvider,
)
from src.detection.sentinel1_preprocessing import Sentinel1Preprocessor, PreprocessingState
from src.pipeline.models import Incident


class WatchService:
    """
    Autonomous watch agent executing the continuous monitoring loop.
    """

    def __init__(
        self,
        config_path: Union[str, Path] = "config/watch.yaml",
        config_dict: Optional[Dict[str, Any]] = None,
        watcher: Optional[SatelliteWatcher] = None,
        ledger: Optional[IngestionLedger] = None,
        preprocessor: Optional[Sentinel1Preprocessor] = None,
    ):
        self.config_path = Path(config_path)
        self.config = config_dict or self._load_config()
        self._stop_event = threading.Event()

        # Ingestion ledger
        ledger_file = self.config.get("processing", {}).get("ledger_path", "data/ledger/ingestion_ledger.json")
        self.ledger = ledger or IngestionLedger(ledger_file)

        # Preprocessor
        self.preprocessor = preprocessor or Sentinel1Preprocessor()

        # AOI bounding box
        reg = self.config.get("region", {}).get("bbox", {})
        self.aoi_bbox = (
            float(reg.get("min_lon", 18.1)),
            float(reg.get("min_lat", 34.3)),
            float(reg.get("max_lon", 18.6)),
            float(reg.get("max_lat", 34.7)),
        )

        # Watcher initialization
        if watcher is not None:
            self.watcher = watcher
        else:
            provider = CopernicusSentinel1Provider()
            self.watcher = SatelliteWatcher(
                catalog_provider=provider,
                ledger=self.ledger,
                region_bbox=self.aoi_bbox,
            )

        self.storage_dir = Path(self.config.get("processing", {}).get("storage_dir", "data/satellite/sentinel1"))
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _load_config(self) -> Dict[str, Any]:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    return yaml.safe_load(f) or {}
            except Exception:
                pass
        return {}

    def stop(self) -> None:
        """Signal graceful shutdown of the watch loop."""
        self._stop_event.set()

    def is_running(self) -> bool:
        """Check if service is active."""
        return not self._stop_event.is_set()

    def run_once(self) -> Dict[str, Any]:
        """
        Execute a single polling iteration of the watch cycle.

        Returns:
            Dictionary detailing cycle outcome, emitted event, and processing status.
        """
        event, prod = self.watcher.poll_and_emit_event(bounding_box=self.aoi_bbox)

        if event == WatchEvent.NO_NEW_SATELLITE_PRODUCT:
            return {
                "event": event.value,
                "status": "NO_NEW_PRODUCT",
                "message": "No new Sentinel-1 products available in catalog for AOI.",
            }

        if event == WatchEvent.DUPLICATE_SATELLITE_PRODUCT:
            pid = prod.get("product_id") if prod else "unknown"
            return {
                "event": event.value,
                "status": "DUPLICATE_PRODUCT",
                "product_id": pid,
                "message": f"Product {pid} already processed in ledger; skipping.",
            }

        if event in (WatchEvent.SATELLITE_PROVIDER_ERROR, WatchEvent.SATELLITE_AUTH_REQUIRED):
            return {
                "event": event.value,
                "status": "ERROR",
                "message": f"Catalog provider reported: {event.value}",
            }

        # NEW_SATELLITE_PRODUCT
        pid = prod.get("product_id", "")
        pname = prod.get("product_name", pid)
        image_path = prod.get("image_path")

        # Check if download is required
        auto_download = self.config.get("processing", {}).get("auto_download", False)
        if auto_download and isinstance(self.watcher.catalog_provider, CopernicusSentinel1Provider):
            status, dl_path, sha256_hash = self.watcher.catalog_provider.download_product(
                product=self.watcher.catalog_provider._normalize_product(prod, self.aoi_bbox),
                destination_dir=self.storage_dir,
            )
            if status == DownloadStatus.SUCCESS and dl_path:
                image_path = dl_path
                self.ledger.update_status(
                    product_id=pid,
                    status=IngestionStatus.DOWNLOADED,
                    product_hash=sha256_hash,
                )

        # Preprocessing validation check
        auto_process = self.config.get("processing", {}).get("auto_process_new_scene", True)
        if not auto_process:
            return {
                "event": event.value,
                "status": "CATALOG_DISCOVERED",
                "product_id": pid,
                "message": "Discovered product registered in ledger (auto_process disabled).",
            }

        if not image_path or not Path(image_path).exists():
            # Mark unsupported product since raster file is not directly present locally
            self.ledger.update_status(
                product_id=pid,
                status=IngestionStatus.UNSUPPORTED_PRODUCT,
                details="Product metadata discovered, but raster binary is not locally staged.",
            )
            return {
                "event": event.value,
                "status": "UNSUPPORTED_PRODUCT",
                "product_id": pid,
                "message": "Raster binary not staged locally for U-Net inference.",
            }

        report = self.preprocessor.validate_raster(image_path)
        if not report.is_valid or report.state == PreprocessingState.UNSUPPORTED_PRODUCT.value:
            self.ledger.update_status(
                product_id=pid,
                status=IngestionStatus.UNSUPPORTED_PRODUCT,
                details=report.unsupported_reason,
            )
            return {
                "event": event.value,
                "status": "UNSUPPORTED_PRODUCT",
                "product_id": pid,
                "report": report.to_dict(),
                "message": f"Product incompatible with current U-Net: {report.unsupported_reason}",
            }

        # Run Incident Pipeline
        conf_thresh = float(self.config.get("processing", {}).get("confidence_threshold", 0.5))
        allow_low_conf = bool(self.config.get("processing", {}).get("allow_low_confidence", True))

        scene_meta = {
            "incident_id": f"INC_{pid[:12]}",
            "product_id": pid,
            "product_name": pname,
            "image_path": str(image_path),
            "acquisition_time": prod.get("acquisition_start", "2024-08-23T09:41:12Z"),
            "bounding_box": prod.get("bbox", self.aoi_bbox),
            "provenance": "REAL",
        }

        from src.pipeline.incident_pipeline import run_incident_pipeline
        incident = run_incident_pipeline(
            scene_metadata=scene_meta,
            output_dir="data/results/incidents",
            confidence_threshold=conf_thresh,
            allow_low_confidence=allow_low_conf,
        )

        self.ledger.update_status(
            product_id=pid,
            status=IngestionStatus.PROCESSED,
            incident_id=incident.incident_id,
            details=f"Processed with status: {incident.status}",
        )

        return {
            "event": event.value,
            "status": "PROCESSED",
            "product_id": pid,
            "incident_id": incident.incident_id,
            "incident_status": incident.status,
            "spill_detected": incident.spill_observation.detected if incident.spill_observation else False,
        }

    def run_loop(
        self,
        max_iterations: Optional[int] = None,
        poll_interval_seconds: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute continuous surveillance loop until stopped.
        """
        interval = poll_interval_seconds or (self.config.get("watch", {}).get("polling_interval_minutes", 60) * 60)
        iterations = 0
        results = []

        while not self._stop_event.is_set():
            res = self.run_once()
            results.append(res)
            iterations += 1

            if max_iterations is not None and iterations >= max_iterations:
                break

            if self._stop_event.wait(timeout=interval):
                break

        return results
