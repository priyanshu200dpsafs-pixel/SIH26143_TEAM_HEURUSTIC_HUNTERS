# AISStream Live Ingestion Provider
# Real-time AIS WebSocket Client implementing the AISProvider interface.

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    import websockets
except ImportError:
    websockets = None

from src.ingestion.ais.base_provider import AISProvider
from src.ingestion.ais.live_buffer import LiveAISBuffer
from src.ingestion.ais.models import AISObservation, VesselTrack, ProviderStatus
from src.ais_analysis.track_builder import build_track

logger = logging.getLogger(__name__)


def convert_bbox_to_aisstream(
    min_lon: float, min_lat: float, max_lon: float, max_lat: float
) -> List[List[List[float]]]:
    """
    Converts standard (min_lon, min_lat, max_lon, max_lat) into AISStream's
    expected format: [[[lat1, lon1], [lat2, lon2]]] (southwest and northeast corners).
    """
    if min_lon > max_lon or min_lat > max_lat:
        raise ValueError("Invalid bounding box: min coordinate exceeds max coordinate")
    return [[[float(min_lat), float(min_lon)], [float(max_lat), float(max_lon)]]]


class AISStreamProvider(AISProvider):
    """
    Live AIS data provider connecting to AISStream (wss://stream.aisstream.io/v0/stream).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        buffer: Optional[LiveAISBuffer] = None,
        wss_url: str = "wss://stream.aisstream.io/v0/stream",
        message_types: Optional[List[str]] = None,
        auto_start: bool = False,
    ):
        if api_key is not None:
            self.api_key = api_key.strip()
        else:
            self.api_key = os.getenv("AISSTREAM_API_KEY", "").strip()
        self.bbox = bbox
        self.buffer = buffer if buffer is not None else LiveAISBuffer()
        self.wss_url = wss_url
        self.message_types = message_types or [
            "PositionReport",
            "StandardClassBPositionReport",
            "ExtendedClassBPositionReport",
            "ShipStaticData",
            "StaticDataReport",
        ]

        # Status and metrics
        self._status = ProviderStatus.DISCONNECTED if self.api_key else ProviderStatus.NOT_CONFIGURED
        self._is_running = False
        self._stop_requested = False
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._supervisor_task: Optional[asyncio.Task] = None
        self._ws = None
        self._lock = threading.Lock()

        # Operational metrics
        self.messages_received: int = 0
        self.position_messages: int = 0
        self.static_messages: int = 0
        self.malformed_messages: int = 0
        self.rejected_messages: int = 0
        self.reconnect_count: int = 0
        self.connected_at: Optional[str] = None
        self.last_message_at: Optional[str] = None
        self.last_position_at: Optional[str] = None
        self.last_error: Optional[str] = None

        # Ship metadata cache: MMSI -> static attributes
        self._static_cache: Dict[str, Dict[str, Any]] = {}

        if auto_start and self.api_key:
            self.start()

    @property
    def data_status(self) -> str:
        return "REAL"

    @property
    def mode(self) -> str:
        return "LIVE"

    def is_configured(self) -> bool:
        return bool(self.api_key)

    def set_bbox(self, bbox: Tuple[float, float, float, float]) -> None:
        self.bbox = bbox

    def get_provider_name(self) -> str:
        return "AISStream"

    def get_status(self) -> ProviderStatus:
        if not self.api_key:
            return ProviderStatus.NOT_CONFIGURED
        return self._status

    def is_connected(self) -> bool:
        return self._status == ProviderStatus.CONNECTED and self._is_running

    def get_subscription_payload(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "APIKey": self.api_key,
            "Format": "json",
        }
        if self.bbox:
            payload["BoundingBoxes"] = convert_bbox_to_aisstream(*self.bbox)
        if self.message_types:
            payload["FilterMessageTypes"] = self.message_types
        return payload

    def start(self):
        """Start background ingestion thread."""
        if not self.api_key:
            self._status = ProviderStatus.NOT_CONFIGURED
            logger.warning("AISStream API key not configured. Cannot start live feed.")
            return

        with self._lock:
            if self._is_running:
                logger.info("AISStream provider already running")
                return
            self._is_running = True
            self._stop_requested = False
            self._status = ProviderStatus.CONNECTING
            self._thread = threading.Thread(target=self._run_event_loop, daemon=True, name="AISStream-Worker")
            self._thread.start()
            logger.info("AISStream ingestion thread started")

    def stop(self):
        """Stop background ingestion thread cleanly."""
        with self._lock:
            if not self._is_running:
                return
            self._stop_requested = True
            self._is_running = False
            self._status = ProviderStatus.DISCONNECTED

        if self._loop and self._loop.is_running():
            def _cancel():
                if self._supervisor_task and not self._supervisor_task.done():
                    self._supervisor_task.cancel()
            self._loop.call_soon_threadsafe(_cancel)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=4.0)
        logger.info("AISStream ingestion stopped")

    def disconnect(self):
        """Alias for stop()."""
        self.stop()

    def _run_event_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._supervisor_task = self._loop.create_task(self._connection_supervisor())
            self._loop.run_until_complete(self._supervisor_task)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Supervisor loop exited: {e}")
        finally:
            try:
                pending = [t for t in asyncio.all_tasks(self._loop) if not t.done()]
                for t in pending:
                    t.cancel()
                if pending:
                    self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            except Exception:
                pass
            finally:
                self._loop.close()

    async def _connection_supervisor(self):
        backoff_delay = 1.0
        while not self._stop_requested:
            try:
                self._status = ProviderStatus.CONNECTING if self.reconnect_count == 0 else ProviderStatus.RECONNECTING
                await self._connect_and_consume()
                backoff_delay = 1.0  # Reset backoff on stable session
            except asyncio.CancelledError:
                break
            except Exception as e:
                err_msg = str(e)
                self.last_error = err_msg
                logger.warning(f"AISStream connection error: {err_msg}")

                if "401" in err_msg or "403" in err_msg or "auth" in err_msg.lower():
                    self._status = ProviderStatus.AUTH_REQUIRED
                    break  # Stop retrying on permanent auth rejection
                elif "429" in err_msg:
                    self._status = ProviderStatus.RATE_LIMITED
                else:
                    self._status = ProviderStatus.PROVIDER_ERROR

                if self._stop_requested:
                    break

                # Exponential backoff with jitter
                self.reconnect_count += 1
                jitter = random.uniform(0.1, 0.5)
                sleep_sec = min(30.0, backoff_delay) + jitter
                logger.info(f"Reconnecting to AISStream in {sleep_sec:.1f}s (attempt {self.reconnect_count})...")
                try:
                    await asyncio.sleep(sleep_sec)
                except asyncio.CancelledError:
                    break
                backoff_delay = min(30.0, backoff_delay * 2.0)

        self._status = ProviderStatus.DISCONNECTED

    async def _connect_and_consume(self):
        if not websockets:
            raise RuntimeError("websockets package is not installed")

        logger.info(f"Connecting to AISStream at {self.wss_url}...")
        try:
            async with websockets.connect(
                self.wss_url,
                ping_interval=20,
                ping_timeout=20,
                close_timeout=5,
            ) as ws:
                self._ws = ws
                sub_payload = self.get_subscription_payload()
                await ws.send(json.dumps(sub_payload))
                logger.info("AISStream subscription payload sent successfully")

                self.connected_at = datetime.now(timezone.utc).isoformat()

                while not self._stop_requested:
                    try:
                        raw_message = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    except asyncio.TimeoutError:
                        continue
                    except asyncio.CancelledError:
                        break

                    self.messages_received += 1
                    self.last_message_at = datetime.now(timezone.utc).isoformat()

                    try:
                        if isinstance(raw_message, bytes):
                            text = raw_message.decode("utf-8", errors="replace")
                        else:
                            text = str(raw_message)

                        parsed = json.loads(text)
                        self._process_message(parsed)
                    except json.JSONDecodeError:
                        self.malformed_messages += 1
                        logger.warning("Received malformed JSON frame from AISStream")
                    except Exception as ex:
                        self.rejected_messages += 1
                        logger.debug(f"Error processing frame: {ex}")
        except asyncio.CancelledError:
            pass
        finally:
            self._ws = None

    def _handle_static_data(self, msg_type: str, meta: Dict[str, Any], message_body: Dict[str, Any]) -> None:
        mmsi = str(meta.get("MMSI") or meta.get("MMSI_String") or "").strip()
        static_info = message_body.get(msg_type, {})
        if not mmsi and "UserID" in static_info:
            mmsi = str(static_info["UserID"]).strip()

        if not mmsi:
            return

        vessel_name = (
            static_info.get("Name")
            or static_info.get("VesselName")
            or meta.get("ShipName")
        )
        vessel_type = static_info.get("Type") or static_info.get("ShipType")
        imo = static_info.get("ImoNumber") or static_info.get("IMO")
        callsign = static_info.get("CallSign")
        draft = static_info.get("MaximumStaticDraught") or static_info.get("Draft")

        dim = static_info.get("Dimension")
        length = None
        beam = None
        if isinstance(dim, dict):
            a = dim.get("A", 0) or 0
            b = dim.get("B", 0) or 0
            c = dim.get("C", 0) or 0
            d = dim.get("D", 0) or 0
            if (a + b) > 0:
                length = float(a + b)
            if (c + d) > 0:
                beam = float(c + d)

        cached = self._static_cache.setdefault(mmsi, {})
        if vessel_name:
            cached["ship_name"] = str(vessel_name).strip()
        if vessel_type is not None:
            cached["ship_type"] = str(vessel_type)
        if imo is not None:
            cached["imo"] = imo
        if callsign:
            cached["callsign"] = str(callsign).strip()
        if draft is not None:
            try:
                cached["draft"] = float(draft)
            except (ValueError, TypeError):
                pass
        if length is not None:
            cached["length"] = length
        if beam is not None:
            cached["beam"] = beam

    def _normalize_position(
        self, msg_type: str, meta: Dict[str, Any], message_body: Dict[str, Any]
    ) -> Optional[AISObservation]:
        mmsi = str(meta.get("MMSI") or meta.get("MMSI_String") or "").strip()
        pos_data = message_body.get(msg_type, {})
        if not mmsi and "UserID" in pos_data:
            mmsi = str(pos_data["UserID"]).strip()

        if not mmsi:
            return None

        lat = meta.get("Latitude") if meta.get("Latitude") is not None else meta.get("latitude")
        lon = meta.get("Longitude") if meta.get("Longitude") is not None else meta.get("longitude")

        if lat is None or lon is None:
            lat = pos_data.get("Latitude")
            lon = pos_data.get("Longitude")

        if lat is None or lon is None:
            return None

        try:
            lat = float(lat)
            lon = float(lon)
        except (ValueError, TypeError):
            return None

        if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
            return None
        if lat == 91.0 or lon == 181.0:
            return None

        sog = pos_data.get("Sog") if pos_data.get("Sog") is not None else pos_data.get("SpeedOverGround")
        try:
            sog = float(sog) if sog is not None else None
            if sog is not None and sog >= 102.2:
                sog = None
        except (ValueError, TypeError):
            sog = None

        cog = pos_data.get("Cog") if pos_data.get("Cog") is not None else pos_data.get("CourseOverGround")
        try:
            cog = float(cog) if cog is not None else None
            if cog is not None and cog >= 360.0:
                cog = None
        except (ValueError, TypeError):
            cog = None

        heading = pos_data.get("TrueHeading")
        try:
            heading = float(heading) if heading is not None else None
            if heading is not None and heading >= 511.0:
                heading = None
        except (ValueError, TypeError):
            heading = None

        # Timestamp parsing
        timestamp_str = meta.get("time_utc")
        iso_ts = None
        if timestamp_str:
            try:
                if "." in timestamp_str and " " in timestamp_str:
                    iso_ts = timestamp_str.split(".")[0].replace(" ", "T") + "Z"
                elif "+" in timestamp_str and " " in timestamp_str:
                    clean = timestamp_str.split("+")[0].strip().replace(" ", "T")
                    iso_ts = clean + "Z" if not clean.endswith("Z") else clean
                else:
                    iso_ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00")).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                iso_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not iso_ts:
            iso_ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Static particulars from cache
        cached_meta = self._static_cache.get(mmsi, {})
        vessel_name = (
            meta.get("ShipName")
            or cached_meta.get("ship_name")
            or f"MMSI-{mmsi}"
        )
        vessel_type = cached_meta.get("ship_type")
        imo = cached_meta.get("imo")
        draft = cached_meta.get("draft")
        length = cached_meta.get("length")
        beam = cached_meta.get("beam")

        return AISObservation(
            mmsi=str(mmsi),
            timestamp=iso_ts,
            latitude=lat,
            longitude=lon,
            sog=sog,
            cog=cog,
            heading=heading,
            ship_name=str(vessel_name).strip() if vessel_name else None,
            ship_type=str(vessel_type) if vessel_type else None,
            imo=str(imo) if imo is not None else None,
            draft=draft,
            length=length,
            beam=beam,
            source="AISStream",
            data_status="REAL",
            mode="LIVE",
        )

    def _process_message(self, data: Dict[str, Any]):
        if "error" in data or "Error" in data:
            err = str(data.get("error") or data.get("Error"))
            self.last_error = err
            if "auth" in err.lower() or "key" in err.lower():
                self._status = ProviderStatus.AUTH_REQUIRED
            logger.error(f"AISStream error received: {err}")
            return

        msg_type = data.get("MessageType", "")
        meta = data.get("MetaData", {})
        message_body = data.get("Message", {})

        # Status update
        if self._status != ProviderStatus.CONNECTED and msg_type in [
            "PositionReport",
            "StandardClassBPositionReport",
            "ExtendedClassBPositionReport",
            "ShipStaticData",
            "StaticDataReport",
            "SubscriptionConfirmation",
        ]:
            self._status = ProviderStatus.CONNECTED

        if msg_type in ["ShipStaticData", "StaticDataReport"]:
            self.static_messages += 1
            self._handle_static_data(msg_type, meta, message_body)
            return

        if msg_type in [
            "PositionReport",
            "StandardClassBPositionReport",
            "ExtendedClassBPositionReport",
        ]:
            obs = self._normalize_position(msg_type, meta, message_body)
            if obs is not None:
                self.buffer.add_observation(obs)
                self.position_messages += 1
                self.last_position_at = obs.timestamp
            else:
                self.rejected_messages += 1

    def get_positions(
        self,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
        mmsi: Optional[Union[str, int]] = None,
    ) -> List[AISObservation]:
        """Query raw normalized AIS observations matching filters from live buffer."""
        return self.buffer.query_observations(
            start_time_iso=start_time_iso,
            end_time_iso=end_time_iso,
            bbox=bbox,
            mmsi=mmsi,
        )

    def get_track(
        self,
        mmsi: Union[str, int],
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
    ) -> Optional[VesselTrack]:
        """Retrieve reconstructed track for a single vessel from live buffer."""
        obs = self.get_positions(
            mmsi=mmsi,
            start_time_iso=start_time_iso,
            end_time_iso=end_time_iso,
        )
        if not obs:
            return None
        return build_track(obs)

    def get_tracks(
        self,
        mmsis: Optional[List[Union[str, int]]] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
    ) -> List[VesselTrack]:
        """Retrieve reconstructed tracks for vessels in the live buffer."""
        tracks = self.buffer.get_vessel_tracks(
            start_time_iso=start_time_iso,
            end_time_iso=end_time_iso,
            bbox=bbox,
        )
        if mmsis is not None:
            mmsi_strs = {str(m) for m in mmsis}
            tracks = [t for t in tracks if str(t.mmsi) in mmsi_strs]
        return tracks

    def get_vessel_static_data(self, mmsi: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Retrieve static vessel particulars from cache or buffered observations."""
        mmsi_str = str(mmsi)
        if mmsi_str in self._static_cache:
            data = dict(self._static_cache[mmsi_str])
            data["mmsi"] = mmsi_str
            data["source"] = self.get_provider_name()
            data["data_status"] = self.data_status
            data["mode"] = self.mode
            return data

        for o in reversed(getattr(self.buffer, "_observations", [])):
            if str(o.mmsi) == mmsi_str:
                return {
                    "mmsi": mmsi_str,
                    "ship_name": o.ship_name,
                    "ship_type": o.ship_type,
                    "imo": o.imo,
                    "draft": o.draft,
                    "length": o.length,
                    "beam": o.beam,
                    "source": self.get_provider_name(),
                    "data_status": self.data_status,
                    "mode": self.mode,
                }
        return None

    def get_metrics(self) -> Dict[str, Any]:
        with self._lock:
            unique_vessels = len(self._static_cache)
            if hasattr(self.buffer, "_observations"):
                unique_vessels = max(unique_vessels, len(set(o.mmsi for o in self.buffer._observations)))

            return {
                "provider": self.get_provider_name(),
                "status": self._status.value,
                "is_running": self._is_running,
                "connected_at": self.connected_at,
                "last_message_at": self.last_message_at,
                "last_position_at": self.last_position_at,
                "messages_received": self.messages_received,
                "position_messages": self.position_messages,
                "static_messages": self.static_messages,
                "malformed_messages": self.malformed_messages,
                "rejected_messages": self.rejected_messages,
                "reconnect_count": self.reconnect_count,
                "unique_vessels": unique_vessels,
                "buffer_observations": len(self.buffer),
                "last_error": self.last_error,
            }
