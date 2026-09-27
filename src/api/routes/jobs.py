"""
Async Job Tracking Router.
"""

from typing import Any, Dict, List
from fastapi import APIRouter, HTTPException

from src.api.jobs import global_job_manager

router = APIRouter(prefix="/api/jobs", tags=["Jobs"])


@router.get("")
def list_jobs(limit: int = 50) -> Dict[str, Any]:
    jobs = global_job_manager.list_jobs(limit)
    return {
        "total": len(jobs),
        "jobs": [j.to_dict() for j in jobs],
    }


@router.get("/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    job = global_job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job.to_dict()
