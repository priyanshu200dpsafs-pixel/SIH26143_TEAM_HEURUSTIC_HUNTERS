"""
Operator Action Audit Logging System.

Maintains an immutable append-only JSONL log of operator and system actions
for regulatory and chain-of-custody compliance.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
import threading
from typing import Any, Dict, List, Optional


class AuditLogger:
    def __init__(self, log_path: str = "data/audit/audit_log.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(
        self,
        action: str,
        target_type: str,
        target_id: str,
        status: str,
        details: Optional[Dict[str, Any]] = None,
        operator: str = "OPERATOR_CONSOLE",
    ) -> Dict[str, Any]:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operator": operator,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "status": status,
            "details": details or {},
        }
        line = json.dumps(entry) + "\n"
        with self._lock:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(line)
        return entry

    def get_logs(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        if not self.log_path.exists():
            return []
        with self._lock:
            with open(self.log_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        entries = []
        for line in reversed(lines):
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
        return entries[offset : offset + limit]


_global_audit = AuditLogger()


def log_action(
    action: str,
    target_type: str,
    target_id: str,
    status: str,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return _global_audit.log(action, target_type, target_id, status, details)


def get_recent_audit_logs(limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
    return _global_audit.get_logs(limit, offset)
