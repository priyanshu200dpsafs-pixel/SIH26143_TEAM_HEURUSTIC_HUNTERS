"""
Global Command Center Search Router.
"""

from pathlib import Path
import json
import re
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Query

from src.api.state import global_app_state

router = APIRouter(prefix="/api/search", tags=["Search"])


@router.get("")
def global_search(q: str = Query(..., min_length=1)) -> Dict[str, Any]:
    query = q.strip()
    term = query.lower()

    incident_results = []
    vessel_results = []
    satellite_results = []
    coordinate_match = None

    # Check coordinate pattern (e.g. "34.5, 18.3" or "34.5 18.3")
    coord_pattern = r"^([+-]?\d+(?:\.\d+)?)[,\s]+([+-]?\d+(?:\.\d+)?)$"
    match = re.match(coord_pattern, query)
    if match:
        lat = float(match.group(1))
        lon = float(match.group(2))
        coordinate_match = {
            "type": "COORDINATES",
            "latitude": lat,
            "longitude": lon,
            "label": f"Coordinates: {lat:.4f}°, {lon:.4f}°",
            "url": f"/operations?lat={lat}&lon={lon}&zoom=10",
        }

    # Search Incidents
    inc_dir = Path("data/results/incidents")
    if inc_dir.exists():
        for f in inc_dir.glob("*.json"):
            if f.stem.endswith("_layers"):
                continue
            if term in f.stem.lower():
                try:
                    with open(f) as fp:
                        data = json.load(fp)
                    spill = data.get("spill_observation") or {}
                    top_c = data.get("top_candidate") or {}
                    incident_results.append({
                        "id": data.get("incident_id", f.stem),
                        "title": f"Incident {data.get('incident_id', f.stem)}",
                        "subtitle": f"Area: {spill.get('area_km2', 0.0):.1f} km² | Status: {data.get('status', 'OPEN')}",
                        "confidence": spill.get("confidence_tier", "UNVERIFIED"),
                        "top_suspect": top_c.get("vessel_name", "None"),
                        "url": f"/incidents/{data.get('incident_id', f.stem)}",
                    })
                except Exception:
                    pass

    # Search AIS Vessels in buffer
    tracks = global_app_state.ais_buffer.get_vessel_tracks()
    for track in tracks:
        mmsi = track.mmsi
        v_name = track.vessel_name or "Unknown"
        v_imo = str(track.imo) if track.imo else ""
        if term in str(mmsi) or term in v_name.lower() or (v_imo and term in v_imo):
            vessel_results.append({
                "mmsi": mmsi,
                "title": f"{v_name} (MMSI: {mmsi})",
                "subtitle": f"Type: {track.vessel_type or 'Vessel'} | IMO: {v_imo or 'N/A'}",
                "anomalies": len(track.anomalies),
                "url": f"/ais?mmsi={mmsi}",
            })

    # Search Satellite Products in ledger
    for entry in global_app_state.ledger.get_all_entries():
        pid = entry.product_id
        pname = entry.product_name or ""
        if term in pid.lower() or term in pname.lower():
            satellite_results.append({
                "id": pid,
                "title": pname or pid,
                "subtitle": f"Acquired: {entry.acquisition_start or entry.first_seen} | Status: {entry.processing_status}",
                "status": entry.processing_status.value if hasattr(entry.processing_status, "value") else str(entry.processing_status),
                "url": f"/satellite?product={pid}",
            })

    return {
        "query": query,
        "coordinate_match": coordinate_match,
        "results": {
            "INCIDENTS": incident_results[:10],
            "VESSELS": vessel_results[:10],
            "SATELLITE_PRODUCTS": satellite_results[:10],
        },
        "total_matches": len(incident_results) + len(vessel_results) + len(satellite_results) + (1 if coordinate_match else 0),
    }
