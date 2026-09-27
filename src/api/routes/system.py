"""
System Health, Status, Audit, and Mode Management Router.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import torch

from src.api.state import global_app_state, GlobalMode, AlertSeverity
from src.api.audit import get_recent_audit_logs, log_action
from src.api.jobs import global_job_manager

router = APIRouter(prefix="/api", tags=["System"])


class ModeRequest(BaseModel):
    mode: str  # LIVE | REPLAY | BENCHMARK


@router.get("/system/health")
def get_system_health() -> Dict[str, Any]:
    # 1. Storage writable check
    storage_writable = False
    try:
        test_file = Path("data/results/health_check.tmp")
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("ok")
        test_file.unlink()
        storage_writable = True
    except Exception:
        storage_writable = False

    # 2. Model status
    model_path = Path("models/sar_unet_baseline_best.pt")
    model_exists = model_path.exists()
    model_device = "cuda" if torch.cuda.is_available() else ("mps" if torch.backends.mps.is_available() else "cpu")

    # 3. Sentinel-1 Provider status
    s1_status, _ = global_app_state.s1_provider.get_auth_token()

    # 4. AIS Provider status
    ais_provider = global_app_state.get_active_ais_provider()
    ais_status = ais_provider.get_status().value

    # 5. Environment data status
    era5_ok = Path("data/weather/era5_wind_mediterranean_case_study.nc").exists()
    oscar_ok = Path("data/ocean_currents/oscar_currents_final_20240823.nc").exists()
    env_ok = era5_ok and oscar_ok

    # Calculate overall health
    # If storage writable and model exists, core functionality works
    if not storage_writable or not model_exists:
        overall_health = "NOT READY"
    elif s1_status.value == "AUTHENTICATION_FAILED" and global_app_state.mode == GlobalMode.LIVE:
        overall_health = "DEGRADED"
    elif not env_ok:
        overall_health = "DEGRADED"
    else:
        overall_health = "READY"

    return {
        "status": overall_health,
        "mode": global_app_state.mode.value,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "storage": {
            "writable": storage_writable,
            "results_dir": "data/results",
            "ledger_path": str(global_app_state.ledger_path),
        },
        "model": {
            "name": "SARSARSegmentor (U-Net 4-Class)",
            "weights_present": model_exists,
            "weights_path": str(model_path),
            "parameters": "7.76M",
            "device": model_device,
        },
        "sentinel1_provider": {
            "name": "Copernicus Data Space Ecosystem (OData)",
            "status": s1_status.value,
            "credentials_configured": global_app_state.s1_provider.has_credentials(),
        },
        "ais_provider": {
            "name": type(ais_provider).__name__,
            "mode": global_app_state.mode.value,
            "status": ais_status,
            "buffer_vessel_count": len(global_app_state.ais_buffer),
        },
        "environment_provider": {
            "era5_wind": "AVAILABLE" if era5_ok else "UNAVAILABLE",
            "oscar_currents": "AVAILABLE" if oscar_ok else "UNAVAILABLE",
            "status": "AVAILABLE" if env_ok else "UNAVAILABLE",
        },
        "workers": {
            "watch_active": global_app_state._watch_running,
            "active_async_jobs": len([j for j in global_job_manager.list_jobs() if j.status.value in ["QUEUED", "RUNNING"]]),
        },
    }


@router.get("/system/status")
def get_system_status() -> Dict[str, Any]:
    return global_app_state.get_watch_status()


@router.post("/system/mode")
def set_platform_mode(req: ModeRequest) -> Dict[str, Any]:
    mode_str = req.mode.upper().strip()
    if mode_str not in [m.value for m in GlobalMode]:
        raise HTTPException(status_code=400, detail=f"Invalid mode '{mode_str}'. Must be LIVE, REPLAY, or BENCHMARK.")
    global_app_state.set_mode(GlobalMode(mode_str))
    return {"status": "SUCCESS", "current_mode": global_app_state.mode.value}


@router.get("/system/audit")
def get_audit_logs(limit: int = 50, offset: int = 0) -> Dict[str, Any]:
    entries = get_recent_audit_logs(limit, offset)
    return {"total": len(entries), "limit": limit, "offset": offset, "entries": entries}


@router.get("/alerts")
def get_alerts(limit: int = 50) -> Dict[str, Any]:
    alerts = global_app_state.get_alerts(limit)
    return {"alerts": alerts, "unread_count": len([a for a in alerts if not a.get("read")])}


@router.post("/alerts/{alert_id}/read")
def mark_alert_read(alert_id: str) -> Dict[str, Any]:
    for alert in global_app_state.alerts:
        if alert["id"] == alert_id:
            alert["read"] = True
            return {"status": "SUCCESS", "alert_id": alert_id}
    raise HTTPException(status_code=404, detail=f"Alert {alert_id} not found")


@router.post("/alerts/clear")
def clear_alerts() -> Dict[str, Any]:
    with global_app_state._alerts_lock:
        global_app_state.alerts = [a for a in global_app_state.alerts if not a.get("read")]
    return {"status": "SUCCESS"}


@router.get("/system/metrics")
def get_system_metrics() -> Dict[str, Any]:
    import psutil
    import os

    proc = psutil.Process(os.getpid())
    mem_mb = proc.memory_info().rss / (1024 * 1024)

    # Incident counts
    inc_dir = Path("data/results/incidents")
    total_inc = 0
    open_inc = 0
    if inc_dir.exists():
        import json
        for f in inc_dir.glob("*.json"):
            if f.stem.endswith("_layers"):
                continue
            total_inc += 1
            try:
                with open(f) as fp:
                    d = json.load(fp)
                if d.get("status") == "OPEN":
                    open_inc += 1
            except Exception:
                pass

    # Ledger metrics
    ledger_summary = global_app_state.get_ledger_summary()

    # AIS metrics
    tracks = global_app_state.ais_buffer.get_vessel_tracks()
    total_vessels = len(tracks)

    # Reports metrics
    reports = global_app_state.report_compiler.list_reports()

    # Jobs metrics
    jobs = global_job_manager.list_jobs(100)
    active_jobs = [j for j in jobs if j.status.value in ["QUEUED", "RUNNING"]]
    complete_jobs = [j for j in jobs if j.status.value == "COMPLETE"]
    failed_jobs = [j for j in jobs if j.status.value == "FAILED"]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "process": {
            "pid": os.getpid(),
            "memory_rss_mb": round(mem_mb, 2),
            "threads_count": proc.num_threads(),
        },
        "incidents": {
            "total_records": total_inc,
            "open_incidents": open_inc,
        },
        "satellite": {
            "tracked_products": ledger_summary.get("total_products", 0),
            "processed_products": ledger_summary.get("processed", 0),
        },
        "ais": {
            "buffer_size_observations": len(global_app_state.ais_buffer),
            "unique_vessels": total_vessels,
            "buffer_hours": global_app_state.ais_buffer.buffer_hours,
        },
        "reports": {
            "compiled_dossiers": len(reports),
        },
        "async_jobs": {
            "total_tracked": len(jobs),
            "active_now": len(active_jobs),
            "completed": len(complete_jobs),
            "failed": len(failed_jobs),
        },
    }
