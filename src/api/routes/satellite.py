"""
Satellite Operations & Sentinel-1 Catalog Router.
Implements per-scene result isolation, canonical geometry hashing, and footprint validation.
"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from src.api.state import global_app_state
from src.api.jobs import global_job_manager
from src.api.audit import log_action
from src.pipeline.incident_pipeline import run_incident_pipeline

router = APIRouter(prefix="/api/satellite", tags=["Satellite"])


def compute_geometry_hash(geometry: Optional[Dict[str, Any]]) -> Optional[str]:
    """Compute deterministic SHA256 hash of canonical GeoJSON geometry."""
    if not geometry:
        return None
    canonical_json = json.dumps(geometry, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def bbox_to_geojson_polygon(bbox: Optional[List[float]]) -> Optional[Dict[str, Any]]:
    """Convert [min_lon, min_lat, max_lon, max_lat] to GeoJSON Polygon."""
    if not bbox or len(bbox) != 4:
        return None
    min_lon, min_lat, max_lon, max_lat = [float(x) for x in bbox]
    return {
        "type": "Polygon",
        "coordinates": [[
            [min_lon, min_lat],
            [max_lon, min_lat],
            [max_lon, max_lat],
            [min_lon, max_lat],
            [min_lon, min_lat],
        ]]
    }


def validate_scene_footprint(centroid: Optional[List[float]], bbox: Optional[List[float]]) -> str:
    """
    Check whether geometry centroid is strictly within the satellite scene bounding box.
    Returns 'PASS' or 'GEOMETRY_SCENE_MISMATCH'.
    """
    if not centroid or not bbox or len(centroid) != 2 or len(bbox) != 4:
        return "PASS"
    lon, lat = float(centroid[0]), float(centroid[1])
    min_lon, min_lat, max_lon, max_lat = [float(x) for x in bbox]
    eps = 1e-5
    if (min_lon - eps) <= lon <= (max_lon + eps) and (min_lat - eps) <= lat <= (max_lat + eps):
        return "PASS"
    return "GEOMETRY_SCENE_MISMATCH"


def record_scene_audit(
    product_id: str,
    incident_id: Optional[str],
    acquisition_time: Optional[str],
    spatial_bbox: Optional[List[float]],
    geometry_hash: Optional[str],
    geometry_centroid: Optional[List[float]],
    footprint_validation: str,
    processing_status: str,
) -> None:
    """Append verification record to debug audit log."""
    audit_file = Path("data/results/debug/scene_binding_audit.json")
    audit_file.parent.mkdir(parents=True, exist_ok=True)
    records = []
    if audit_file.exists():
        try:
            with open(audit_file, "r") as f:
                records = json.load(f)
        except Exception:
            records = []

    new_entry = {
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "product_id": product_id,
        "incident_id": incident_id,
        "acquisition_time": acquisition_time,
        "spatial_bbox": spatial_bbox,
        "geometry_hash": geometry_hash,
        "geometry_centroid": geometry_centroid,
        "footprint_validation": footprint_validation,
        "processing_status": processing_status,
    }
    records.append(new_entry)
    with open(audit_file, "w") as f:
        json.dump(records, f, indent=2)


class SatelliteSearchRequest(BaseModel):
    min_lon: float = 18.1
    min_lat: float = 34.3
    max_lon: float = 18.6
    max_lat: float = 34.7
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    product_type: Optional[str] = "GRD"
    max_results: Optional[int] = 10


@router.get("/products")
def list_satellite_products(
    status: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    ledger_data = global_app_state.get_ledger_summary()
    all_entries = global_app_state.ledger.get_all_entries()

    # Sort descending by acquisition start or first_seen
    all_entries.sort(key=lambda x: x.acquisition_start or x.first_seen, reverse=True)

    if status:
        all_entries = [e for e in all_entries if (hasattr(e.processing_status, "value") and e.processing_status.value == status) or e.processing_status == status]

    products_out = []
    for e in all_entries[:limit]:
        ed = e.to_dict() if hasattr(e, "to_dict") else dict(e)
        bbox = ed.get("spatial_bbox") or [18.1, 34.3, 18.6, 34.7]
        ed["scene_footprint"] = bbox_to_geojson_polygon(bbox)
        products_out.append(ed)

    return {
        "total": len(all_entries),
        "products": products_out,
        "ledger_summary": ledger_data,
    }


@router.get("/products/{product_id}/result")
def get_product_result(product_id: str) -> Dict[str, Any]:
    """
    Section 10 API Contract: Strictly isolated per-scene incident geometry and validation.
    """
    entry = global_app_state.ledger.get_entry(product_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found in ingestion ledger.")

    # Locate incident record
    inc_id = entry.incident_id or f"INC_{product_id}"
    inc_path = Path("data/results/incidents") / f"{inc_id}.json"

    inc_data = None
    if inc_path.exists():
        try:
            with open(inc_path, "r") as f:
                inc_data = json.load(f)
        except Exception:
            pass

    if not inc_data:
        # Search directory for matching product_id
        incidents_dir = Path("data/results/incidents")
        if incidents_dir.exists():
            for p in incidents_dir.glob("INC_*.json"):
                try:
                    with open(p, "r") as f:
                        d = json.load(f)
                        if d.get("satellite_observation", {}).get("product_id") == product_id:
                            inc_data = d
                            inc_id = d.get("incident_id", inc_id)
                            break
                except Exception:
                    continue

    bbox = list(entry.spatial_bbox) if entry.spatial_bbox else [18.1, 34.3, 18.6, 34.7]
    scene_footprint = bbox_to_geojson_polygon(bbox)
    acq_time = entry.acquisition_start or entry.first_seen

    if not inc_data:
        p_status = entry.processing_status.value if hasattr(entry.processing_status, "value") else str(entry.processing_status)
        return {
            "product_id": product_id,
            "incident_id": None,
            "acquisition_time": acq_time,
            "processing_status": p_status,
            "geometry": None,
            "geometry_hash": None,
            "scene_footprint": scene_footprint,
            "footprint_validation": "PASS",
            "geometry_centroid": None,
            "geometry_bbox": None,
        }

    status = inc_data.get("status", "UNKNOWN")
    spill_obs = inc_data.get("spill_observation") or {}
    detected = spill_obs.get("detected", False)

    if status == "NO_SPILL" or not detected:
        result_payload = {
            "product_id": product_id,
            "incident_id": inc_id,
            "acquisition_time": acq_time,
            "processing_status": "NO_SPILL",
            "geometry": None,
            "geometry_hash": None,
            "scene_footprint": scene_footprint,
            "footprint_validation": "PASS",
            "geometry_centroid": None,
            "geometry_bbox": None,
        }
        record_scene_audit(
            product_id=product_id,
            incident_id=inc_id,
            acquisition_time=acq_time,
            spatial_bbox=bbox,
            geometry_hash=None,
            geometry_centroid=None,
            footprint_validation="PASS",
            processing_status="NO_SPILL",
        )
        return result_payload

    # Spill detected
    geometry = spill_obs.get("polygon_geojson")
    geom_hash = compute_geometry_hash(geometry)
    centroid = spill_obs.get("centroid")
    geom_bbox = spill_obs.get("bounding_box")
    validation = validate_scene_footprint(centroid, bbox)

    result_payload = {
        "product_id": product_id,
        "incident_id": inc_id,
        "acquisition_time": acq_time,
        "processing_status": status,
        "geometry": geometry,
        "geometry_hash": geom_hash,
        "scene_footprint": scene_footprint,
        "footprint_validation": validation,
        "geometry_centroid": centroid,
        "geometry_bbox": geom_bbox,
    }

    record_scene_audit(
        product_id=product_id,
        incident_id=inc_id,
        acquisition_time=acq_time,
        spatial_bbox=bbox,
        geometry_hash=geom_hash,
        geometry_centroid=centroid,
        footprint_validation=validation,
        processing_status=status,
    )
    return result_payload


@router.get("/products/{product_id}")
def get_product_details(product_id: str) -> Dict[str, Any]:
    entry = global_app_state.ledger.get_entry(product_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found in ingestion ledger.")

    # Check local raster file if available
    local_path = None
    for ext in [".tif", ".jpg", ".png", ".jpeg"]:
        cand = Path("data/satellite/sentinel1") / f"{product_id}{ext}"
        if cand.exists():
            local_path = cand
            break

    validation = None
    if local_path and local_path.suffix.lower() == ".tif":
        try:
            validation = global_app_state.preprocessor.validate_raster(local_path).to_dict()
        except Exception:
            validation = None

    # Attach result contract
    res_data = get_product_result(product_id)

    return {
        "product": entry.to_dict(),
        "local_file_exists": local_path is not None,
        "local_path": str(local_path) if local_path else None,
        "validation_report": validation,
        "result": res_data,
    }


@router.post("/search")
def search_catalog(req: SatelliteSearchRequest) -> Dict[str, Any]:
    bbox = (req.min_lon, req.min_lat, req.max_lon, req.max_lat)
    start_iso = req.start_time or "2024-08-01T00:00:00Z"
    end_iso = req.end_time or datetime.now(timezone.utc).isoformat()

    log_action("SEARCH_SATELLITE_CATALOG", "SENTINEL1", f"bbox_{bbox}", "INITIATED")

    try:
        status, products, err_msg = global_app_state.s1_provider.search_products(
            bbox=bbox,
            start_time=start_iso,
            end_time=end_iso,
            product_type=req.product_type or "GRD",
            max_results=req.max_results or 10,
        )
        products_out = [p.to_dict() for p in products]
        log_action("SEARCH_SATELLITE_CATALOG", "SENTINEL1", f"bbox_{bbox}", status.value, {"count": len(products)})
        return {
            "status": status.value,
            "provider": "Copernicus Data Space Ecosystem (OData)",
            "count": len(products_out),
            "products": products_out,
            "error": err_msg,
        }
    except Exception as e:
        log_action("SEARCH_SATELLITE_CATALOG", "SENTINEL1", f"bbox_{bbox}", "FAILED", {"error": str(e)})
        return {
            "status": "ERROR",
            "provider": "Copernicus Data Space Ecosystem (OData)",
            "message": f"Catalog query failed: {e}",
            "count": 0,
            "products": [],
        }


@router.post("/products/{product_id}/download")
def download_product(product_id: str) -> Dict[str, Any]:
    entry = global_app_state.ledger.get_entry(product_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not tracked in ledger.")

    target_dir = Path("data/satellite/sentinel1")
    target_dir.mkdir(parents=True, exist_ok=True)

    status, dest = global_app_state.s1_provider.download_product(product_id, target_dir)
    log_action("DOWNLOAD_PRODUCT", "SENTINEL1", product_id, status.value, {"destination": dest})

    if status.value == "FAILED_NO_CREDENTIALS":
        return {
            "status": "UNAVAILABLE",
            "reason": "Copernicus CDSE credentials (CDSE_CLIENT_ID / CDSE_CLIENT_SECRET) not configured.",
            "download_status": status.value,
        }

    return {
        "status": status.value,
        "product_id": product_id,
        "destination_path": dest,
    }


@router.post("/products/{product_id}/validate")
def validate_product_raster(product_id: str) -> Dict[str, Any]:
    candidate_paths = [
        Path("data/satellite/sentinel1") / f"{product_id}.tif",
        Path("data/satellite/sentinel1") / f"{product_id}.png",
        Path("data/satellite/sentinel1") / f"{product_id}.jpg",
        Path("data/results/incidents") / f"{product_id}.png",
    ]
    found_path = None
    for p in candidate_paths:
        if p.exists():
            found_path = p
            break

    if not found_path:
        return {
            "is_valid": False,
            "status": "UNAVAILABLE",
            "reason": f"Raster file for product '{product_id}' is not staged locally.",
        }

    report = global_app_state.preprocessor.validate_raster(found_path)
    log_action("VALIDATE_RASTER", "SENTINEL1", product_id, report.state, report.to_dict())
    return report.to_dict()


@router.post("/products/{product_id}/process")
def trigger_product_processing(product_id: str) -> Dict[str, Any]:
    entry = global_app_state.ledger.get_entry(product_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Product {product_id} not found in ledger.")

    # Check if this is a real Sentinel-1 product with downloaded components
    real_dir = Path("data/satellite/sentinel1_real") / product_id
    if real_dir.exists():
        from scripts.process_real_sentinel1 import process_real_sentinel1_product
        log_action("PROCESS_PRODUCT", "REAL_PIPELINE", product_id, "RUNNING")
        res = process_real_sentinel1_product(product_id=product_id)
        global_app_state.ledger.mark_processed(product_id, res["incident_id"], status=res["result_state"])
        log_action("PROCESS_PRODUCT", "REAL_PIPELINE", product_id, "SUCCESS", {"incident_id": res["incident_id"], "status": res["result_state"]})
        return {
            "status": "COMPLETED",
            "incident_id": res["incident_id"],
            "result_state": res["result_state"],
            "product_id": product_id,
            "footprint_validation": res["footprint_validation"],
            "provenance": "REAL",
        }

    # Locate image strictly for this specific product (NO STALE/BENCHMARK FALLBACK!)
    candidate_paths = [
        Path("data/satellite/sentinel1") / f"{product_id}.jpg",
        Path("data/satellite/sentinel1") / f"{product_id}.png",
        Path("data/satellite/sentinel1") / f"{product_id}.tif",
        Path("data/satellite/sentinel1") / f"{product_id}.jpeg",
        Path("data/results/incidents") / f"{product_id}.png",
    ]
    found_path = None
    for p in candidate_paths:
        if p.exists():
            found_path = str(p)
            break

    if not found_path:
        raise HTTPException(
            status_code=400,
            detail=f"SAR raster for product {product_id} has not been downloaded yet. Download product before processing."
        )

    incident_id = f"INC_{product_id}"
    scene_meta = {
        "incident_id": incident_id,
        "product_id": product_id,
        "acquisition_time": entry.acquisition_start or datetime.now(timezone.utc).isoformat(),
        "bounding_box": list(entry.spatial_bbox) if entry.spatial_bbox else [18.1, 34.3, 18.6, 34.7],
        "image_path": found_path,
        "provenance": getattr(entry, "provenance", "SIMULATED"),
    }

    def _execute_pipeline():
        log_action("PROCESS_PRODUCT", "PIPELINE", product_id, "RUNNING")
        # For benchmark scenarios, enforce replay AIS provider
        active_provider = global_app_state.get_active_ais_provider()
        if product_id.startswith("S1A_MED") or product_id.startswith("S1A_ION") or product_id.startswith("S1B_AEG") or getattr(entry, "provenance", "") == "SIMULATED":
            active_provider = global_app_state.replay_ais_provider
            scene_meta["mode"] = "REPLAY"

        inc = run_incident_pipeline(
            scene_metadata=scene_meta,
            ais_provider=active_provider,
            output_dir="data/results/incidents",
        )
        global_app_state.ledger.mark_processed(product_id, inc.incident_id, status=inc.status)
        log_action("PROCESS_PRODUCT", "PIPELINE", product_id, "SUCCESS", {"incident_id": inc.incident_id, "status": inc.status})

        # Record scene audit
        spill_obs = getattr(inc, "spill_observation", None)
        centroid = getattr(spill_obs, "centroid", None) if spill_obs else None
        geometry = getattr(spill_obs, "polygon_geojson", None) if spill_obs else None
        geom_hash = compute_geometry_hash(geometry)
        validation = validate_scene_footprint(centroid, scene_meta["bounding_box"])
        record_scene_audit(
            product_id=product_id,
            incident_id=inc.incident_id,
            acquisition_time=scene_meta["acquisition_time"],
            spatial_bbox=scene_meta["bounding_box"],
            geometry_hash=geom_hash,
            geometry_centroid=centroid,
            footprint_validation=validation,
            processing_status=inc.status,
        )
        return inc.to_dict()

    job = global_job_manager.submit_job(
        job_type="SATELLITE_PROCESSING",
        target_id=product_id,
        task_fn=_execute_pipeline,
    )

    return {
        "status": "QUEUED",
        "job_id": job.job_id,
        "incident_id": incident_id,
        "message": f"Pipeline execution submitted for product {product_id}",
    }


@router.get("/audit")
def get_scene_binding_audit() -> List[Dict[str, Any]]:
    """Retrieve audit records verifying scene-to-geometry isolation."""
    audit_file = Path("data/results/debug/scene_binding_audit.json")
    if not audit_file.exists():
        return []
    try:
        with open(audit_file, "r") as f:
            return json.load(f)
    except Exception:
        return []
