"""
AIS Operations & Live Vessel Traffic Router.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
import yaml

from src.api.state import global_app_state, GlobalMode
from src.api.audit import log_action
from src.ingestion.ais.models import AISObservation, VesselTrack

router = APIRouter(prefix="/api/ais", tags=["AIS"])


class AISConfigRequest(BaseModel):
    mode: Optional[str] = None  # replay | live
    buffer_hours: Optional[int] = 48
    query_max_distance_km: Optional[float] = 100.0


@router.get("/status")
def get_ais_status() -> Dict[str, Any]:
    provider = global_app_state.get_active_ais_provider()
    status = provider.get_status()

    # Load quality report if present
    quality_file = Path("data/results/ais/live_quality_report.json")
    quality_report = None
    if quality_file.exists():
        try:
            with open(quality_file) as f:
                quality_report = json.load(f)
        except Exception:
            pass

    metrics = {}
    if hasattr(provider, "get_metrics"):
        metrics = provider.get_metrics()
    elif hasattr(global_app_state.live_ais_provider, "get_metrics"):
        metrics = global_app_state.live_ais_provider.get_metrics()

    live_prov = global_app_state.live_ais_provider

    return {
        "mode": global_app_state.mode.value,
        "provider_mode": getattr(provider, "mode", "REPLAY").upper(),
        "provider_class": type(provider).__name__,
        "connection_status": status.value,
        "is_configured": getattr(provider, "is_configured", lambda: True)(),
        "buffer_size_observations": len(global_app_state.ais_buffer),
        "buffer_history_hours": global_app_state.ais_buffer.buffer_hours,
        "quality_report": quality_report,
        "metrics": metrics,
        "live_provider": {
            "name": live_prov.get_provider_name(),
            "status": live_prov.get_status().value,
            "is_running": live_prov._is_running,
            "is_configured": live_prov.is_configured(),
            "metrics": live_prov.get_metrics(),
        },
        "provenance": "REAL / LIVE" if (global_app_state.mode == GlobalMode.LIVE and status.value == "CONNECTED" and live_prov._is_running) else "SIMULATED / REPLAY",
    }


@router.post("/connect")
def connect_ais() -> Dict[str, Any]:
    global_app_state.set_mode(GlobalMode.LIVE)
    res = global_app_state.start_live_ais()
    log_action("CONNECT_AIS", "AIS_PROVIDER", "AISStream", res.get("status"))
    return res


@router.post("/disconnect")
def disconnect_ais() -> Dict[str, Any]:
    global_app_state.set_mode(GlobalMode.REPLAY)
    res = global_app_state.stop_live_ais()
    log_action("DISCONNECT_AIS", "AIS_PROVIDER", "AISStream", res.get("status"))
    return res


@router.post("/test")
def test_ais_connection() -> Dict[str, Any]:
    provider = global_app_state.get_active_ais_provider()
    status = provider.get_status()
    log_action("TEST_AIS_CONNECTION", "AIS_PROVIDER", type(provider).__name__, status.value)

    if status.value == "CONNECTED":
        return {
            "success": True,
            "status": "CONNECTED",
            "message": "AIS provider connected and transmitting valid telemetry.",
        }
    elif status.value == "NOT_CONFIGURED":
        return {
            "success": False,
            "status": "NOT_CONFIGURED",
            "message": "AIS provider credentials / endpoint not configured in config/ais.yaml.",
        }
    else:
        return {
            "success": False,
            "status": status.value,
            "message": f"Connection returned state: {status.value}",
        }


@router.get("/vessels")
def list_vessels(
    search: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    # Extract unique vessels from live buffer
    tracks = global_app_state.ais_buffer.get_vessel_tracks()
    vessels = []
    for track in tracks:
        mmsi = track.mmsi
        latest = track.observations[-1] if track.observations else None
        v_name = track.vessel_name or (latest.vessel_name if latest else "Unknown")
        v_type = track.vessel_type or (latest.vessel_type if latest else "Unknown")

        if search:
            s = search.lower()
            if not (s in str(mmsi).lower() or s in v_name.lower()):
                continue

        vessels.append({
            "mmsi": mmsi,
            "vessel_name": v_name,
            "imo": track.imo or (latest.imo if latest else None),
            "vessel_type": v_type,
            "latitude": latest.latitude if latest else 0.0,
            "longitude": latest.longitude if latest else 0.0,
            "speed_over_ground": latest.speed_over_ground if latest else 0.0,
            "course_over_ground": latest.course_over_ground if latest else 0.0,
            "timestamp": latest.timestamp if latest else "",
            "observations_count": len(track.observations),
            "anomalies_count": len(track.anomalies),
            "gaps_count": len(track.gaps),
            "integrity_state": "ANOMALOUS" if track.anomalies else ("GAPS_DETECTED" if track.gaps else "NORMAL"),
            "source": track.source_provider or "REPLAY_BUFFER",
        })

    vessels.sort(key=lambda x: x["timestamp"], reverse=True)
    return {
        "total": len(vessels),
        "vessels": vessels[:limit],
    }


@router.get("/debug/map")
def get_ais_debug_map() -> Dict[str, Any]:
    tracks = global_app_state.ais_buffer.get_vessel_tracks()
    vessel_count = len(tracks)
    unique_mmsis = set()
    invalid_coords = 0
    duplicate_coords = 0
    seen_coords = set()
    features = []
    lats = []
    lons = []
    
    for t in tracks:
        unique_mmsis.add(str(t.mmsi))
        latest = t.observations[-1] if t.observations else None
        if not latest:
            invalid_coords += 1
            continue
        lat = latest.latitude
        lon = latest.longitude
        if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            invalid_coords += 1
            continue
        coord_pair = (round(lat, 5), round(lon, 5))
        if coord_pair in seen_coords:
            duplicate_coords += 1
        else:
            seen_coords.add(coord_pair)
        lats.append(lat)
        lons.append(lon)
        features.append({
            "type": "Feature",
            "id": str(t.mmsi),
            "geometry": {
                "type": "Point",
                "coordinates": [lon, lat],
            },
            "properties": {
                "mmsi": str(t.mmsi),
                "ship_name": t.vessel_name or (latest.vessel_name if latest else "Unknown"),
                "latitude": lat,
                "longitude": lon,
                "timestamp": latest.timestamp if latest else "",
            }
        })
        
    return {
        "vessel_count": vessel_count,
        "feature_count": len(features),
        "unique_mmsi_count": len(unique_mmsis),
        "invalid_coordinate_count": invalid_coords,
        "duplicate_coordinate_count": duplicate_coords,
        "coordinate_range": {
            "min_lat": min(lats) if lats else None,
            "max_lat": max(lats) if lats else None,
            "min_lon": min(lons) if lons else None,
            "max_lon": max(lons) if lons else None,
        },
        "sample_features": features[:3],
    }


@router.get("/vessels/{mmsi}")
def get_vessel_detail(mmsi: str) -> Dict[str, Any]:
    matched = [t for t in global_app_state.ais_buffer.get_vessel_tracks() if str(t.mmsi) == str(mmsi)]
    if not matched:
        raise HTTPException(status_code=404, detail=f"Vessel with MMSI {mmsi} not found in active buffer.")
    track = matched[0]
    latest = track.observations[-1] if track.observations else None

    # Find relevant incidents where this vessel was evaluated as candidate
    inc_dir = Path("data/results/incidents")
    relevant_incidents = []
    if inc_dir.exists():
        for f in inc_dir.glob("*.json"):
            if f.stem.endswith("_layers"):
                continue
            try:
                with open(f) as fp:
                    inc_data = json.load(fp)
                for cand in inc_data.get("candidates", []):
                    if str(cand.get("mmsi")) == str(mmsi):
                        relevant_incidents.append({
                            "incident_id": inc_data.get("incident_id"),
                            "created_at": inc_data.get("created_at"),
                            "composite_score": cand.get("composite_score"),
                            "attribution_decision": cand.get("attribution_decision"),
                            "min_distance_nm": cand.get("min_distance_nm"),
                        })
            except Exception:
                pass

    return {
        "mmsi": mmsi,
        "vessel_name": track.vessel_name or (latest.vessel_name if latest else "Unknown"),
        "imo": track.imo,
        "vessel_type": track.vessel_type,
        "callsign": track.callsign,
        "length_m": track.length_m,
        "width_m": track.width_m,
        "draft_m": track.draft_m,
        "latest_observation": latest.to_dict() if latest else None,
        "total_points": len(track.observations),
        "anomalies": [a.to_dict() for a in track.anomalies],
        "gaps": [g.to_dict() for g in track.gaps],
        "relevant_incidents": relevant_incidents,
        "track_geojson": track.to_geojson(),
    }


@router.get("/vessels/{mmsi}/track")
def get_vessel_track(mmsi: str) -> Dict[str, Any]:
    matched = [t for t in global_app_state.ais_buffer.get_vessel_tracks() if str(t.mmsi) == str(mmsi)]
    if not matched:
        raise HTTPException(status_code=404, detail=f"Vessel with MMSI {mmsi} not found.")
    track = matched[0]
    return {
        "mmsi": mmsi,
        "vessel_name": track.vessel_name,
        "observations": [o.to_dict() for o in track.observations],
        "geojson": track.to_geojson(),
    }


@router.post("/refresh")
def refresh_buffer() -> Dict[str, Any]:
    # Prune rolling window and re-fetch if needed
    pruned = global_app_state.ais_buffer.prune_rolling_window()
    global_app_state._init_ais_data()
    return {
        "status": "SUCCESS",
        "buffer_size": len(global_app_state.ais_buffer),
        "pruned_count": pruned,
    }


@router.post("/config")
def update_ais_config(cfg: AISConfigRequest) -> Dict[str, Any]:
    if cfg.mode:
        m = cfg.mode.lower()
        if m in ["replay", "live"]:
            # Update yaml
            try:
                data = {}
                if global_app_state.ais_config_path.exists():
                    with open(global_app_state.ais_config_path) as f:
                        data = yaml.safe_load(f) or {}
                data.setdefault("provider", {})["mode"] = m
                if cfg.buffer_hours:
                    data.setdefault("buffer", {})["hours"] = cfg.buffer_hours
                with open(global_app_state.ais_config_path, "w") as f:
                    yaml.dump(data, f)
                log_action("UPDATE_AIS_CONFIG", "CONFIG", "ais.yaml", "SUCCESS", data)
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to write ais.yaml: {e}")

    return {"status": "SUCCESS", "message": "AIS configuration updated."}
