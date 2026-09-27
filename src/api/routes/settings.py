"""
Platform Settings & Secure Configuration Router.
"""

import os
from pathlib import Path
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import yaml

from src.api.state import global_app_state
from src.api.audit import log_action

router = APIRouter(prefix="/api/settings", tags=["Settings"])


class UpdateSettingsRequest(BaseModel):
    region_name: Optional[str] = None
    min_lon: Optional[float] = None
    min_lat: Optional[float] = None
    max_lon: Optional[float] = None
    max_lat: Optional[float] = None
    watch_interval_minutes: Optional[int] = None
    auto_process_new_scene: Optional[bool] = None
    ais_mode: Optional[str] = None
    ais_buffer_hours: Optional[int] = None
    forecast_horizon_hours: Optional[int] = None


@router.get("")
def get_settings() -> Dict[str, Any]:
    # Read watch.yaml
    watch_cfg = {}
    if global_app_state.watch_config_path.exists():
        try:
            with open(global_app_state.watch_config_path) as f:
                watch_cfg = yaml.safe_load(f) or {}
        except Exception:
            pass

    # Read ais.yaml
    ais_cfg = {}
    if global_app_state.ais_config_path.exists():
        try:
            with open(global_app_state.ais_config_path) as f:
                ais_cfg = yaml.safe_load(f) or {}
        except Exception:
            pass

    # Check credentials without exposing secrets
    cdse_configured = bool(
        os.environ.get("CDSE_CLIENT_ID") or os.environ.get("COPERNICUS_API_KEY")
    )
    ais_key_name = ais_cfg.get("live", {}).get("api_key_env", "AIS_API_KEY")
    ais_configured = bool(os.environ.get(ais_key_name))
    gfw_configured = bool(os.environ.get("GFW_API_TOKEN"))

    reg = watch_cfg.get("region", {})
    reg_bbox = reg.get("bbox", {})

    return {
        "surveillance": {
            "region_name": reg.get("name", "Central Mediterranean Approaches"),
            "bbox": {
                "min_lon": float(reg_bbox.get("min_lon", 18.1)),
                "min_lat": float(reg_bbox.get("min_lat", 34.3)),
                "max_lon": float(reg_bbox.get("max_lon", 18.6)),
                "max_lat": float(reg_bbox.get("max_lat", 34.7)),
            },
            "polling_interval_minutes": watch_cfg.get("watch", {}).get("polling_interval_minutes", 60),
            "auto_process_new_scene": watch_cfg.get("processing", {}).get("auto_process_new_scene", True),
            "forecast_horizon_hours": watch_cfg.get("processing", {}).get("forecast_horizon_hours", 24),
        },
        "satellite": {
            "collection": "SENTINEL-1",
            "product_type": "GRD",
            "provider": "Copernicus Data Space Ecosystem (OData)",
            "credentials_state": "CONFIGURED" if cdse_configured else "NOT_CONFIGURED",
        },
        "ais": {
            "mode": ais_cfg.get("provider", {}).get("mode", "replay"),
            "historical_provider": ais_cfg.get("provider", {}).get("historical_provider", "gfw"),
            "buffer_hours": ais_cfg.get("buffer", {}).get("hours", 48),
            "credentials_state": "CONFIGURED" if ais_configured else "NOT_CONFIGURED",
            "gfw_credentials_state": "CONFIGURED" if gfw_configured else "NOT_CONFIGURED",
            "benchmark_dir": ais_cfg.get("replay", {}).get("benchmark_dir", "data/ais/synthetic/benchmarks"),
        },
        "model": {
            "weights_path": "models/sar_unet_baseline_best.pt",
            "status": "VALIDATED (7.76M parameters)",
        },
    }


@router.put("")
def update_settings(req: UpdateSettingsRequest) -> Dict[str, Any]:
    # Update watch.yaml
    watch_cfg = {}
    if global_app_state.watch_config_path.exists():
        try:
            with open(global_app_state.watch_config_path) as f:
                watch_cfg = yaml.safe_load(f) or {}
        except Exception:
            pass

    if req.region_name is not None:
        watch_cfg.setdefault("region", {})["name"] = req.region_name
    if req.min_lon is not None:
        watch_cfg.setdefault("region", {}).setdefault("bbox", {})["min_lon"] = req.min_lon
    if req.min_lat is not None:
        watch_cfg.setdefault("region", {}).setdefault("bbox", {})["min_lat"] = req.min_lat
    if req.max_lon is not None:
        watch_cfg.setdefault("region", {}).setdefault("bbox", {})["max_lon"] = req.max_lon
    if req.max_lat is not None:
        watch_cfg.setdefault("region", {}).setdefault("bbox", {})["max_lat"] = req.max_lat
    if req.watch_interval_minutes is not None:
        watch_cfg.setdefault("watch", {})["polling_interval_minutes"] = req.watch_interval_minutes
    if req.auto_process_new_scene is not None:
        watch_cfg.setdefault("processing", {})["auto_process_new_scene"] = req.auto_process_new_scene
    if req.forecast_horizon_hours is not None:
        watch_cfg.setdefault("processing", {})["forecast_horizon_hours"] = req.forecast_horizon_hours

    with open(global_app_state.watch_config_path, "w") as f:
        yaml.dump(watch_cfg, f)

    # Update ais.yaml
    if req.ais_mode is not None or req.ais_buffer_hours is not None:
        ais_cfg = {}
        if global_app_state.ais_config_path.exists():
            try:
                with open(global_app_state.ais_config_path) as f:
                    ais_cfg = yaml.safe_load(f) or {}
            except Exception:
                pass
        if req.ais_mode is not None:
            ais_cfg.setdefault("provider", {})["mode"] = req.ais_mode.lower()
        if req.ais_buffer_hours is not None:
            ais_cfg.setdefault("buffer", {})["hours"] = req.ais_buffer_hours
        with open(global_app_state.ais_config_path, "w") as f:
            yaml.dump(ais_cfg, f)

    log_action("UPDATE_SETTINGS", "SETTINGS", "global_config", "SUCCESS")
    return {"status": "SUCCESS", "message": "Settings persisted to configuration files."}
