"""
Attribution Analysis & Forensic Counterfactuals Router.
"""

from pathlib import Path
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.api.state import global_app_state
from src.api.jobs import global_job_manager
from src.api.audit import log_action
from src.pipeline.incident_pipeline import run_incident_pipeline

router = APIRouter(prefix="/api/analysis", tags=["Attribution"])


class CounterfactualSimulationRequest(BaseModel):
    incident_id: str
    mmsi: int
    wind_jitter_pct: Optional[float] = 0.0
    current_jitter_pct: Optional[float] = 0.0


@router.get("/incident/{incident_id}")
def get_attribution_workspace(incident_id: str) -> Dict[str, Any]:
    json_path = Path("data/results/incidents") / f"{incident_id}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"Incident {incident_id} not found.")

    with open(json_path) as f:
        inc = json.load(f)

    candidates = inc.get("candidates") or []
    top_cand = inc.get("top_candidate") or (candidates[0] if candidates else None)

    return {
        "incident_id": incident_id,
        "region_name": inc.get("region_name"),
        "top_candidate": top_cand,
        "candidates": candidates,
        "hindcast": inc.get("hindcast_result"),
        "environmental": inc.get("environmental_evidence"),
        "counterfactual": inc.get("counterfactual_result"),
        "attribution_status": inc.get("attribution_status", "COMPLETED"),
    }


@router.post("/counterfactual")
def run_counterfactual_simulation(req: CounterfactualSimulationRequest) -> Dict[str, Any]:
    json_path = Path("data/results/incidents") / f"{req.incident_id}.json"
    if not json_path.exists():
        raise HTTPException(status_code=404, detail=f"Incident {req.incident_id} not found.")

    def _execute():
        log_action("COUNTERFACTUAL_TEST", "ANALYSIS", f"{req.incident_id}_{req.mmsi}", "RUNNING")
        with open(json_path) as f:
            inc_data = json.load(f)

        sat = inc_data.get("satellite_observation") or {}
        scene_meta = {
            "incident_id": req.incident_id,
            "product_id": sat.get("product_id", f"S1_{req.incident_id}"),
            "acquisition_time": sat.get("acquisition_time", "2024-08-23T09:41:12Z"),
            "bounding_box": sat.get("bounding_box", [18.1, 34.3, 18.6, 34.7]),
        }
        res = run_incident_pipeline(
            scene_metadata=scene_meta,
            ais_provider=global_app_state.get_active_ais_provider(),
        )
        cf = res.to_dict().get("counterfactual_result")
        log_action("COUNTERFACTUAL_TEST", "ANALYSIS", f"{req.incident_id}_{req.mmsi}", "COMPLETE", cf)
        return cf

    job = global_job_manager.submit_job("COUNTERFACTUAL_SIMULATION", f"{req.incident_id}_{req.mmsi}", _execute)
    return {
        "status": "QUEUED",
        "job_id": job.job_id,
        "message": f"Counterfactual forward drift run queued for MMSI {req.mmsi}.",
    }
