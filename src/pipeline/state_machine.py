"""
Continuous Maritime Watch State Machine.

Tracks the lifecycle of satellite observations and incident progression through
the defined formal states:
- MONITORING
- NEW_PRODUCT
- PROCESSING
- NO_SPILL
- POTENTIAL_SPILL
- VALIDATING
- SPILL_CONFIRMED
- HINDCASTING
- AIS_RECONSTRUCTION
- ATTRIBUTION
- COUNTERFACTUAL
- FORECASTING
- INCIDENT_READY
- FAILED
"""

from enum import Enum
from typing import Any, Dict, List, Optional
import time


class WatchState(str, Enum):
    MONITORING = "MONITORING"
    NEW_PRODUCT = "NEW_PRODUCT"
    PROCESSING = "PROCESSING"
    NO_SPILL = "NO_SPILL"
    POTENTIAL_SPILL = "POTENTIAL_SPILL"
    VALIDATING = "VALIDATING"
    SPILL_CONFIRMED = "SPILL_CONFIRMED"
    HINDCASTING = "HINDCASTING"
    AIS_RECONSTRUCTION = "AIS_RECONSTRUCTION"
    ATTRIBUTION = "ATTRIBUTION"
    COUNTERFACTUAL = "COUNTERFACTUAL"
    FORECASTING = "FORECASTING"
    INCIDENT_READY = "INCIDENT_READY"
    AIS_COVERAGE_INSUFFICIENT = "AIS_COVERAGE_INSUFFICIENT"
    FAILED = "FAILED"


class WatchStateMachine:
    """
    Finite State Machine with transition audit logging.
    """

    def __init__(self, initial_state: WatchState = WatchState.MONITORING):
        self._current_state = initial_state
        self._history: List[Dict[str, Any]] = [
            {
                "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "from_state": None,
                "to_state": initial_state.value,
                "reason": "Initialization",
            }
        ]

    @property
    def current_state(self) -> WatchState:
        return self._current_state

    def transition(self, new_state: WatchState, reason: Optional[str] = None) -> None:
        """Execute and log a state transition."""
        entry = {
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "from_state": self._current_state.value,
            "to_state": new_state.value,
            "reason": reason or "",
        }
        self._history.append(entry)
        self._current_state = new_state

    def get_log(self) -> List[Dict[str, Any]]:
        """Return full chronological transition ledger."""
        return list(self._history)
