import logging
logger = logging.getLogger("aegis_sar.state")
"""
Central Application State Manager for AEGIS-SAR.

Maintains platform modes (LIVE, REPLAY, BENCHMARK), orchestrates the continuous
watch background thread, manages the live AIS buffer, and tracks system notifications.
"""

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional
import yaml

from src.ingestion.ledger import IngestionLedger
from src.ingestion.sentinel1_provider import CopernicusSentinel1Provider
from src.detection.sentinel1_preprocessing import Sentinel1Preprocessor
from src.ingestion.watch_service import WatchService
from src.ingestion.ais.live_buffer import LiveAISBuffer
from src.ingestion.ais.live_provider import LiveAISProvider
from src.ingestion.ais.aisstream_provider import AISStreamProvider
from src.ingestion.replay_ais import ReplayAISProvider
from src.reporting.report_compiler import ForensicReportCompiler
from src.api.audit import log_action
from src.api.ws import global_ws_hub


class GlobalMode(str, Enum):
    LIVE = "LIVE"
    REPLAY = "REPLAY"
    BENCHMARK = "BENCHMARK"


class AlertSeverity(str, Enum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AppState:
    def __init__(self):
        self.mode: GlobalMode = GlobalMode.REPLAY
        self.watch_config_path = Path("config/watch.yaml")
        self.ais_config_path = Path("config/ais.yaml")
        self.ledger_path = Path("data/ledger/ingestion_ledger.json")

        # Ingestion components
        self.ledger = IngestionLedger(str(self.ledger_path))
        self.preprocessor = Sentinel1Preprocessor()
        self.s1_provider = CopernicusSentinel1Provider()
        self.report_compiler = ForensicReportCompiler()

        # AIS Components
        self.ais_buffer = LiveAISBuffer(buffer_hours=72.0)
        self.live_ais_provider = AISStreamProvider(buffer=self.ais_buffer)
        self.replay_ais_provider = ReplayAISProvider()

        # Watch service thread management
        self.watch_service: Optional[WatchService] = None
        self._watch_thread: Optional[threading.Thread] = None
        self._watch_running = False
        self._watch_paused = False
        self.last_watch_run: Optional[str] = None
        self.last_watch_status: str = "IDLE"
        self.last_watch_summary: Optional[Dict[str, Any]] = None

        # Notifications queue
        self.alerts: List[Dict[str, Any]] = []
        self._alerts_lock = threading.Lock()

        # Seed initial system status alert
        self.add_alert(
            severity=AlertSeverity.INFO,
            title="System Initialized",
            message="AEGIS-SAR Maritime Surveillance Backend initialized in REPLAY mode.",
            related_link="/operations",
        )

        # Populate AIS buffer with default replay tracks if in REPLAY mode
        self._init_ais_data()

    def _init_ais_data(self):
        """Pre-populate buffer with scenario 1 candidates and Mediterranean traffic."""
        try:
            # 1. Load Mediterranean incident candidate tracks
            positions = self.replay_ais_provider.get_positions(
                bbox=(18.0, 34.0, 19.0, 35.0),
                start_time_iso="2024-08-20T00:00:00Z",
                end_time_iso="2024-08-24T00:00:00Z",
            )
            if positions:
                self.ais_buffer.add_observations(positions)
                logger.info(f"Loaded {len(positions)} candidate observations into AIS buffer.")

            # 2. Also load wider Mediterranean background shipping traffic
            traffic_path = Path("data/ais/synthetic/synthetic_ais_spill_scenario.csv")
            if traffic_path.exists():
                traffic_positions = self.replay_ais_provider.get_positions(csv_path=traffic_path)
                if traffic_positions:
                    self.ais_buffer.add_observations(traffic_positions)
                    logger.info(f"Loaded {len(traffic_positions)} background traffic observations into AIS buffer.")
        except Exception as e:
            logger.error(f"Failed to populate AIS buffer: {e}")

    def set_mode(self, mode: GlobalMode) -> None:
        prev = self.mode
        self.mode = mode
        log_action("SWITCH_MODE", "SYSTEM", mode.value, "SUCCESS", {"from": prev.value, "to": mode.value})
        if mode == GlobalMode.LIVE:
            if self.live_ais_provider.is_configured():
                self.live_ais_provider.start()
        else:
            self.live_ais_provider.stop()
            if mode == GlobalMode.REPLAY and len(self.ais_buffer) == 0:
                self._init_ais_data()
        self.add_alert(
            severity=AlertSeverity.WARNING if mode == GlobalMode.LIVE else AlertSeverity.INFO,
            title=f"Mode Switched to {mode.value}",
            message=f"Platform data stream updated to {mode.value} source.",
            related_link="/system",
        )
        global_ws_hub.broadcast({
            "type": "MODE_CHANGED",
            "mode": mode.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

    def add_alert(
        self,
        severity: AlertSeverity,
        title: str,
        message: str,
        related_link: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        entry = {
            "id": f"alt_{int(time.time() * 1000)}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "severity": severity.value,
            "title": title,
            "message": message,
            "related_link": related_link,
            "data": data or {},
            "read": False,
        }
        with self._alerts_lock:
            self.alerts.insert(0, entry)
            if len(self.alerts) > 100:
                self.alerts = self.alerts[:100]

        global_ws_hub.broadcast({
            "type": "ALERT",
            "alert": entry,
            "timestamp": entry["timestamp"],
        })
        return entry

    def get_alerts(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._alerts_lock:
            return list(self.alerts[:limit])

    def start_live_ais(self) -> Dict[str, Any]:
        if not self.live_ais_provider.is_configured():
            return {
                "status": "NOT_CONFIGURED",
                "message": "AISSTREAM_API_KEY environment variable is not configured.",
            }
        self.live_ais_provider.start()
        return {
            "status": self.live_ais_provider.get_status().value,
            "message": "AISStream live connection started.",
        }

    def stop_live_ais(self) -> Dict[str, Any]:
        self.live_ais_provider.stop()
        return {
            "status": "DISCONNECTED",
            "message": "AISStream live connection stopped.",
        }

    def get_active_ais_provider(self):
        if self.mode == GlobalMode.LIVE:
            return self.live_ais_provider
        return self.replay_ais_provider

    # Watch Service Controls

    def get_ledger_summary(self) -> Dict[str, Any]:
        entries = self.ledger.get_all_entries()
        total = len(entries)
        processed = sum(1 for e in entries if getattr(e.processing_status, "value", str(e.processing_status)) == "PROCESSED")
        return {"total_products": total, "processed": processed}

    def get_watch_status(self) -> Dict[str, Any]:
        s1_status, _ = self.s1_provider.get_auth_token()
        ais_status = self.get_active_ais_provider().get_status()

        # Environmental check
        era5_exists = Path("data/weather/era5_wind_mediterranean_case_study.nc").exists()
        oscar_exists = Path("data/ocean_currents/oscar_currents_final_20240823.nc").exists()
        env_state = "AVAILABLE" if (era5_exists and oscar_exists) else "UNAVAILABLE"

        ledger_stats = self.get_ledger_summary()

        return {
            "mode": self.mode.value,
            "watch_active": self._watch_running,
            "watch_paused": self._watch_paused,
            "last_watch_run": self.last_watch_run,
            "last_watch_status": self.last_watch_status,
            "last_summary": self.last_watch_summary,
            "satellite_status": s1_status.value,
            "ais_status": ais_status.value,
            "environment_status": env_state,
            "pipeline_status": "READY",
            "ledger_products_tracked": ledger_stats.get("total_products", 0),
            "ais_buffer_count": len(self.ais_buffer),
        }

    def start_watch(self) -> Dict[str, Any]:
        if self._watch_running:
            return {"status": "ALREADY_RUNNING", "message": "Watch service is already running."}

        self.watch_service = WatchService(
            config_path=self.watch_config_path,
            ledger=self.ledger,
            preprocessor=self.preprocessor,
        )
        self._watch_running = True
        self._watch_paused = False

        def _loop():
            log_action("START_WATCH", "WATCH_SERVICE", "continuous_loop", "RUNNING")
            self.add_alert(AlertSeverity.INFO, "Watch Started", "Continuous maritime watch worker thread activated.", "/watch")
            while self._watch_running:
                if not self._watch_paused:
                    try:
                        self.last_watch_run = datetime.now(timezone.utc).isoformat()
                        res = self.watch_service.run_once()
                        self.last_watch_summary = res
                        self.last_watch_status = res.get("status", "SUCCESS")

                        # If new scenes or incidents were generated, broadcast
                        if res.get("new_products_found", 0) > 0:
                            self.add_alert(
                                AlertSeverity.WARNING,
                                "New Satellite Scene Discovered",
                                f"Discovered {res['new_products_found']} new Sentinel-1 products in AOI.",
                                "/satellite",
                                res,
                            )
                        global_ws_hub.broadcast({
                            "type": "WATCH_EVENT",
                            "summary": res,
                            "timestamp": self.last_watch_run,
                        })
                    except Exception as e:
                        self.last_watch_status = f"ERROR: {e}"

                # Sleep polling interval (default 30s in test/dev, configurable)
                interval = self.watch_service.config.get("watch", {}).get("polling_interval_minutes", 10) * 60
                interval = min(interval, 30)  # capped for responsive UI testing
                for _ in range(int(interval)):
                    if not self._watch_running:
                        break
                    time.sleep(1)

        self._watch_thread = threading.Thread(target=_loop, daemon=True, name="AegisWatchThread")
        self._watch_thread.start()
        return {"status": "STARTED", "message": "Continuous surveillance watch service started."}

    def stop_watch(self) -> Dict[str, Any]:
        if not self._watch_running:
            return {"status": "NOT_RUNNING", "message": "Watch service is not running."}
        self._watch_running = False
        if self.watch_service:
            self.watch_service.stop()
        log_action("STOP_WATCH", "WATCH_SERVICE", "continuous_loop", "STOPPED")
        self.add_alert(AlertSeverity.INFO, "Watch Stopped", "Continuous maritime watch service stopped by operator.", "/watch")
        return {"status": "STOPPED", "message": "Watch service terminated."}

    def pause_watch(self) -> Dict[str, Any]:
        self._watch_paused = True
        log_action("PAUSE_WATCH", "WATCH_SERVICE", "continuous_loop", "PAUSED")
        return {"status": "PAUSED", "message": "Watch polling paused."}

    def resume_watch(self) -> Dict[str, Any]:
        self._watch_paused = False
        log_action("RESUME_WATCH", "WATCH_SERVICE", "continuous_loop", "RESUMED")
        return {"status": "RESUMED", "message": "Watch polling resumed."}

    def run_watch_once(self) -> Dict[str, Any]:
        ws = WatchService(
            config_path=self.watch_config_path,
            ledger=self.ledger,
            preprocessor=self.preprocessor,
        )
        self.last_watch_run = datetime.now(timezone.utc).isoformat()
        res = ws.run_once()
        self.last_watch_summary = res
        self.last_watch_status = res.get("status", "SUCCESS")
        log_action("RUN_WATCH_ONCE", "WATCH_SERVICE", "single_cycle", self.last_watch_status, res)

        global_ws_hub.broadcast({
            "type": "WATCH_EVENT",
            "summary": res,
            "timestamp": self.last_watch_run,
        })
        return res


global_app_state = AppState()
