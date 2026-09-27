"""
Watch Management Router.

Exposes REST controls for continuous maritime AOI surveillance,
background worker thread lifecycle, and catalog polling parameters.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import yaml

from src.api.state import global_app_state
from src.api.audit import log_action

router = APIRouter(prefix="/api/watch", tags=["Watch"])


class BBoxModel(BaseModel):
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float


class WatchConfigModel(BaseModel):
    name: Optional[str] = "Central Mediterranean Approaches"
    bbox: BBoxModel
    polling_interval_minutes: Optional[int] = 60
    satellite_enabled: Optional[bool] = True
    ais_enabled: Optional[bool] = True
    environmental_enabled: Optional[bool] = True
    auto_process: Optional[bool] = True
    confidence_threshold: Optional[float] = 0.5
    forecast_horizon_hours: Optional[int] = 24


@router.get("")
def get_watch_info() -> Dict[str, Any]:
    status = global_app_state.get_watch_status()

    # Load active watch config
    cfg: Dict[str, Any] = {}
    if global_app_state.watch_config_path.exists():
        try:
            with open(global_app_state.watch_config_path) as f:
                cfg = yaml.safe_load(f) or {}
        except Exception:
            cfg = {}

    ledger_summary = global_app_state.get_ledger_summary()

    return {
        "status": status,
        "config": cfg,
        "ledger": ledger_summary,
    }


@router.post("")
def update_watch_config(cfg: WatchConfigModel) -> Dict[str, Any]:
    config_dict = {
        "watch": {
            "enabled": True,
            "polling_interval_minutes": cfg.polling_interval_minutes,
        },
        "region": {
            "name": cfg.name,
            "bbox": {
                "min_lon": cfg.bbox.min_lon,
                "min_lat": cfg.bbox.min_lat,
                "max_lon": cfg.bbox.max_lon,
                "max_lat": cfg.bbox.max_lat,
            },
        },
        "satellite": {
            "sentinel1": {
                "enabled": cfg.satellite_enabled,
                "collection": "SENTINEL-1",
                "product_type": "GRD",
                "max_scene_age_hours": 168,
            }
        },
        "processing": {
            "auto_process_new_scene": cfg.auto_process,
            "auto_download": False,
            "confidence_threshold": cfg.confidence_threshold,
            "forecast_horizon_hours": cfg.forecast_horizon_hours,
            "storage_dir": "data/satellite/sentinel1",
            "ledger_path": "data/ledger/ingestion_ledger.json",
        },
    }

    global_app_state.watch_config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(global_app_state.watch_config_path, "w") as f:
        yaml.dump(config_dict, f)

    log_action("UPDATE_WATCH_CONFIG", "CONFIG", "watch.yaml", "SUCCESS", config_dict)
    return {"status": "SUCCESS", "message": "Watch configuration updated.", "config": config_dict}


@router.post("/start")
def start_watch() -> Dict[str, Any]:
    return global_app_state.start_watch()


@router.post("/stop")
def stop_watch() -> Dict[str, Any]:
    return global_app_state.stop_watch()


@router.post("/pause")
def pause_watch() -> Dict[str, Any]:
    return global_app_state.pause_watch()


@router.post("/resume")
def resume_watch() -> Dict[str, Any]:
    return global_app_state.resume_watch()


@router.post("/run-once")
def run_watch_once() -> Dict[str, Any]:
    return global_app_state.run_watch_once()


@router.delete("")
def delete_watch() -> Dict[str, Any]:
    if global_app_state._watch_running:
        global_app_state.stop_watch()
    log_action("RESET_WATCH_CONFIG", "CONFIG", "watch.yaml", "SUCCESS")
    return {"status": "SUCCESS", "message": "Watch service stopped and configuration reset."}
