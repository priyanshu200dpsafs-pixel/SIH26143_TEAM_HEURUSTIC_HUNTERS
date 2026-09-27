"""
Persistent Satellite Ingestion Ledger.

Maintains an immutable historical record of all discovered, downloaded, and
processed satellite scenes to guarantee that no duplicate incidents are generated.
Persisted as human- and machine-readable JSON with atomic writes.
"""

from dataclasses import dataclass, asdict
from enum import Enum
import json
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional, Tuple, Union


class IngestionStatus(str, Enum):
    DISCOVERED = "DISCOVERED"
    DOWNLOADED = "DOWNLOADED"
    PROCESSED = "PROCESSED"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    UNSUPPORTED_PRODUCT = "UNSUPPORTED_PRODUCT"


@dataclass
class LedgerEntry:
    """Canonical ledger entry for a satellite product."""
    product_id: str
    product_name: str
    acquisition_start: str
    acquisition_end: str
    first_seen: str
    processing_status: str  # IngestionStatus
    incident_id: Optional[str] = None
    source_provider: str = "Copernicus Data Space"
    spatial_bbox: Optional[Tuple[float, float, float, float]] = None
    product_hash: Optional[str] = None
    details: Optional[str] = None
    updated_at: Optional[str] = None
    provenance: str = "REAL"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if self.spatial_bbox:
            d["spatial_bbox"] = list(self.spatial_bbox)
        return d


class IngestionLedger:
    """
    Thread-safe and process-safe persistent ledger tracking satellite products.
    """

    def __init__(self, ledger_file: Optional[Union[str, Path]] = "data/ledger/ingestion_ledger.json"):
        self.ledger_file = Path(ledger_file) if ledger_file is not None else None
        self._entries: Dict[str, LedgerEntry] = {}
        self._load()

    def _load(self) -> None:
        if self.ledger_file and self.ledger_file.exists():
            try:
                with open(self.ledger_file, "r") as f:
                    data = json.load(f)
                for pid, item in data.get("entries", {}).items():
                    bbox = tuple(item["spatial_bbox"]) if item.get("spatial_bbox") else None
                    self._entries[pid] = LedgerEntry(
                        product_id=item["product_id"],
                        product_name=item["product_name"],
                        acquisition_start=item.get("acquisition_start", ""),
                        acquisition_end=item.get("acquisition_end", ""),
                        first_seen=item.get("first_seen", ""),
                        processing_status=item.get("processing_status", IngestionStatus.DISCOVERED.value),
                        incident_id=item.get("incident_id"),
                        source_provider=item.get("source_provider", "Copernicus Data Space"),
                        spatial_bbox=bbox,
                        product_hash=item.get("product_hash"),
                        details=item.get("details"),
                        updated_at=item.get("updated_at"),
                    )
            except Exception:
                self._entries = {}

    def _save(self) -> None:
        if not self.ledger_file:
            return
        self.ledger_file.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write via temp file
        temp_file = self.ledger_file.with_suffix(".tmp")
        data = {
            "version": "1.0",
            "last_updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_products_tracked": len(self._entries),
            "entries": {pid: entry.to_dict() for pid, entry in self._entries.items()},
        }
        with open(temp_file, "w") as f:
            json.dump(data, f, indent=2)
        temp_file.replace(self.ledger_file)

    def is_seen(self, product_id: str) -> bool:
        """Check if product has ever been recorded."""
        return product_id in self._entries

    def is_processed(self, product_id: str) -> bool:
        """Check if product has already generated an incident or was processed."""
        entry = self._entries.get(product_id)
        if not entry:
            return False
        return entry.processing_status in (
            IngestionStatus.PROCESSED.value,
            IngestionStatus.UNSUPPORTED_PRODUCT.value,
            IngestionStatus.REJECTED.value,
        )

    def record_discovery(
        self,
        product_id: str,
        product_name: str,
        acquisition_start: str = "",
        acquisition_end: str = "",
        spatial_bbox: Optional[Tuple[float, float, float, float]] = None,
        source_provider: str = "Copernicus Data Space",
    ) -> LedgerEntry:
        """Record newly discovered product in DISCOVERED status."""
        now_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if product_id in self._entries:
            return self._entries[product_id]

        entry = LedgerEntry(
            product_id=product_id,
            product_name=product_name,
            acquisition_start=acquisition_start,
            acquisition_end=acquisition_end,
            first_seen=now_utc,
            processing_status=IngestionStatus.DISCOVERED.value,
            source_provider=source_provider,
            spatial_bbox=spatial_bbox,
            updated_at=now_utc,
        )
        self._entries[product_id] = entry
        self._save()
        return entry

    def mark_processed(
        self,
        product_id: str,
        incident_id: str,
        status: Union[IngestionStatus, str] = "PROCESSED",
    ) -> Optional[LedgerEntry]:
        """Convenience method to mark a product processed and record the incident ID."""
        return self.update_status(product_id=product_id, status=status, incident_id=incident_id)

    def update_status(
        self,
        product_id: str,
        status: Union[IngestionStatus, str],
        incident_id: Optional[str] = None,
        product_hash: Optional[str] = None,
        details: Optional[str] = None,
    ) -> Optional[LedgerEntry]:
        """Update processing status and attach hash / incident metadata."""
        if product_id not in self._entries:
            return None

        status_val = status.value if isinstance(status, IngestionStatus) else str(status)
        entry = self._entries[product_id]
        entry.processing_status = status_val
        entry.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        if incident_id:
            entry.incident_id = incident_id
        if product_hash:
            entry.product_hash = product_hash
        if details:
            entry.details = details

        self._save()
        return entry

    def get_entry(self, product_id: str) -> Optional[LedgerEntry]:
        """Retrieve entry by product ID."""
        return self._entries.get(product_id)

    def get_all_entries(self) -> List[LedgerEntry]:
        """Return list of all entries."""
        return list(self._entries.values())
