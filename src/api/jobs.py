"""
Asynchronous Job Management & Execution Engine.

Executes scientific workloads (Lagrangian hindcast, SAR segmentation,
counterfactual simulation, report generation) asynchronously without blocking
FastAPI HTTP request threads.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
import threading
import time
from typing import Any, Callable, Dict, List, Optional
import uuid


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


@dataclass
class JobRecord:
    job_id: str
    job_type: str
    target_id: str
    status: JobStatus
    progress: float = 0.0
    progress_message: str = "Queued for processing"
    result: Optional[Any] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d


class JobManager:
    """
    Thread-pool backed async job coordinator.
    """

    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="AegisWorker")
        self.jobs: Dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._callbacks: List[Callable[[JobRecord], None]] = []

    def register_listener(self, cb: Callable[[JobRecord], None]) -> None:
        self._callbacks.append(cb)

    def _notify(self, job: JobRecord) -> None:
        for cb in self._callbacks:
            try:
                cb(job)
            except Exception:
                pass

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            return self.jobs.get(job_id)

    def list_jobs(self, limit: int = 50) -> List[JobRecord]:
        with self._lock:
            job_list = list(self.jobs.values())
        job_list.sort(key=lambda j: j.created_at, reverse=True)
        return job_list[:limit]

    def update_progress(self, job_id: str, progress: float, message: str) -> None:
        with self._lock:
            job = self.jobs.get(job_id)
            if job:
                job.progress = max(0.0, min(1.0, progress))
                job.progress_message = message
                self._notify(job)

    def submit_job(
        self,
        job_type: str,
        target_id: str,
        task_fn: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> JobRecord:
        job_id = f"job_{uuid.uuid4().hex[:10]}"
        job = JobRecord(
            job_id=job_id,
            job_type=job_type,
            target_id=target_id,
            status=JobStatus.QUEUED,
            progress=0.0,
            progress_message="Job submitted to queue",
        )
        with self._lock:
            self.jobs[job_id] = job
        self._notify(job)

        def _runner():
            job.status = JobStatus.RUNNING
            job.started_at = datetime.now(timezone.utc).isoformat()
            job.progress_message = "Executing task"
            self._notify(job)
            try:
                # Allow task_fn to accept a progress callback if it supports it
                res = task_fn(*args, **kwargs)
                job.status = JobStatus.COMPLETE
                job.progress = 1.0
                job.progress_message = "Task completed successfully"
                job.result = res
                job.completed_at = datetime.now(timezone.utc).isoformat()
            except Exception as e:
                job.status = JobStatus.FAILED
                job.progress_message = f"Execution failed: {e}"
                job.error = str(e)
                job.completed_at = datetime.now(timezone.utc).isoformat()
            finally:
                self._notify(job)

        self.executor.submit(_runner)
        return job


global_job_manager = JobManager()
