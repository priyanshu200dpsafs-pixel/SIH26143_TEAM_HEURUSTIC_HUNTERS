"""
Forensic Reports & Prosecutor Briefs Router.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.api.state import global_app_state, AlertSeverity
from src.api.audit import log_action

router = APIRouter(prefix="/api/reports", tags=["Reports"])


class CompileReportRequest(BaseModel):
    incident_id: str
    operator_notes: Optional[str] = None


class VerifyReportRequest(BaseModel):
    report_id: str


@router.get("")
def list_reports() -> Dict[str, Any]:
    reports = global_app_state.report_compiler.list_reports()
    return {
        "total": len(reports),
        "reports": reports,
    }


@router.get("/{report_id}")
def get_report(report_id: str) -> Dict[str, Any]:
    record = global_app_state.report_compiler.get_report(report_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found.")

    html_content = ""
    html_path = Path(record["html_path"])
    if html_path.exists():
        with open(html_path, "r", encoding="utf-8") as f:
            html_content = f.read()

    return {
        "report": record,
        "html_content": html_content,
    }


@router.get("/{report_id}/download")
def download_report(report_id: str, format: str = "html"):
    if ".." in report_id or "/" in report_id or "\\" in report_id:
        raise HTTPException(status_code=400, detail="Invalid report identifier format.")
    record = global_app_state.report_compiler.get_report(report_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Report '{report_id}' not found.")

    target_path = Path(record["json_path"] if format.lower() == "json" else record["html_path"])
    if not target_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found on disk: {target_path}")

    media_type = "application/json" if format.lower() == "json" else "text/html"
    return FileResponse(
        path=str(target_path),
        media_type=media_type,
        filename=target_path.name,
    )


@router.post("/compile")
def compile_report(req: CompileReportRequest) -> Dict[str, Any]:
    inc_path = Path("data/results/incidents") / f"{req.incident_id}.json"
    if not inc_path.exists():
        raise HTTPException(status_code=404, detail=f"Incident '{req.incident_id}' not found.")

    import json
    with open(inc_path) as f:
        inc = json.load(f)

    rec = global_app_state.report_compiler.compile_incident_report(inc, operator_notes=req.operator_notes)
    log_action("COMPILE_REPORT", "REPORT", rec.report_id, "SUCCESS", {"sha256": rec.sha256_hash})

    global_app_state.add_alert(
        AlertSeverity.INFO,
        "Forensic Report Compiled",
        f"Evidentiary dossier {rec.report_id} generated for incident {req.incident_id}.",
        "/reports",
    )

    return {
        "status": "SUCCESS",
        "report": rec.to_dict(),
    }


@router.post("/verify")
def verify_report(req: VerifyReportRequest) -> Dict[str, Any]:
    result = global_app_state.report_compiler.verify_report_hash(req.report_id)
    log_action("VERIFY_REPORT_HASH", "REPORT", req.report_id, "VALID" if result.get("valid") else "INVALID", result)
    return result
