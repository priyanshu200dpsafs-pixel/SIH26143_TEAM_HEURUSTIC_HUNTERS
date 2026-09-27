"""
Replay AIS Provider Adapter.

Provides deterministic playback of recorded / synthetic benchmark scenario files.
Guarantees strict provenance tracking:
    data_status = 'SIMULATED'
    mode = 'REPLAY'
The hidden benchmark ground truth remains strictly isolated from attribution logic.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import pandas as pd

from src.ingestion.ais.base_provider import AISProvider
from src.ingestion.ais.models import AISObservation, VesselTrack, ProviderStatus
from src.ais_analysis.track_builder import normalize_raw_observation, build_track


class ReplayAISProvider(AISProvider):
    """
    Simulated Replay Provider reading from local benchmark fixtures.
    Implements both the unified AISProvider interface and legacy ReplayAISProvider methods.
    """

    def __init__(
        self,
        benchmark_dir: Union[str, Path] = "data/ais/synthetic/benchmarks",
        default_scenario: int = 1,
    ):
        self.benchmark_dir = Path(benchmark_dir)
        self.default_scenario = default_scenario
        self._data_status = "SIMULATED"
        self._mode = "REPLAY"
        self._manifest: Optional[List[Dict[str, Any]]] = None
        self._load_manifest()

    @property
    def data_status(self) -> str:
        return self._data_status

    @property
    def mode(self) -> str:
        return self._mode

    def get_status(self) -> ProviderStatus:
        if self.benchmark_dir.exists():
            return ProviderStatus.CONNECTED
        return ProviderStatus.PROVIDER_ERROR

    def _load_manifest(self) -> None:
        manifest_path = self.benchmark_dir / "benchmark_manifest.json"
        if manifest_path.exists():
            try:
                with open(manifest_path) as f:
                    self._manifest = json.load(f)
            except Exception:
                self._manifest = []

    # --- Legacy Methods (Strictly Preserved for Backward Compatibility) ---

    def get_available_scenarios(self) -> List[Dict[str, Any]]:
        """Return list of scenarios from manifest without ground truth."""
        if not self._manifest:
            return []
        return [
            {
                "scenario_id": s["scenario_id"],
                "name": s["name"],
                "description": s.get("description", s.get("name", "")),
                "data_status": self.data_status,
                "mode": self.mode,
            }
            for s in self._manifest
        ]

    def load_ais_data(
        self,
        scenario_id: Optional[int] = None,
        csv_path: Optional[Union[str, Path]] = None,
    ) -> pd.DataFrame:
        """
        Load AIS dataframe for specified scenario or filepath.
        Excludes any ground truth information.
        """
        if csv_path is not None:
            target_path = Path(csv_path)
            if not target_path.exists():
                raise FileNotFoundError(f"Specified AIS file not found: {csv_path}")
        else:
            sid = scenario_id if scenario_id is not None else self.default_scenario
            target_path = None
            if self._manifest:
                for item in self._manifest:
                    if int(item["scenario_id"]) == sid:
                        target_path = self.benchmark_dir / item["ais_file"]
                        break
            if target_path is None or not target_path.exists():
                raise FileNotFoundError(f"Replay AIS benchmark scenario {sid} not found in {self.benchmark_dir}")

        df = pd.read_csv(target_path)
        if "BaseDateTime" in df.columns:
            df = df.sort_values("BaseDateTime").reset_index(drop=True)

        return df

    def get_vessels(
        self,
        scenario_id: Optional[int] = None,
        csv_path: Optional[Union[str, Path]] = None,
    ) -> List[int]:
        """Return unique MMSIs present in the scenario."""
        df = self.load_ais_data(scenario_id=scenario_id, csv_path=csv_path)
        return [int(m) for m in df["MMSI"].unique()]

    def get_vessel_track(
        self,
        mmsi: int,
        scenario_id: Optional[int] = None,
        csv_path: Optional[Union[str, Path]] = None,
    ) -> pd.DataFrame:
        """Retrieve slice for a single vessel (legacy DataFrame return)."""
        df = self.load_ais_data(scenario_id=scenario_id, csv_path=csv_path)
        v_df = df[df["MMSI"] == mmsi].sort_values("BaseDateTime").reset_index(drop=True)
        return v_df

    # --- Unified AISProvider Interface ---

    def get_positions(
        self,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
        mmsi: Optional[Union[str, int]] = None,
        scenario_id: Optional[int] = None,
        csv_path: Optional[Union[str, Path]] = None,
    ) -> List[AISObservation]:
        """
        Load and normalize observations from benchmark dataset matching criteria.
        bbox: (min_lon, min_lat, max_lon, max_lat)
        """
        df = self.load_ais_data(scenario_id=scenario_id, csv_path=csv_path)
        if df.empty:
            return []

        # Filter by MMSI
        if mmsi is not None:
            mmsi_target = int(mmsi) if str(mmsi).isdigit() else str(mmsi)
            df = df[df["MMSI"] == mmsi_target]

        # Spatial bounding box filter
        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            df = df[
                (df["LON"] >= min_lon) & (df["LON"] <= max_lon) &
                (df["LAT"] >= min_lat) & (df["LAT"] <= max_lat)
            ]

        # Temporal filter
        if start_time_iso is not None:
            df = df[df["BaseDateTime"] >= start_time_iso]
        if end_time_iso is not None:
            df = df[df["BaseDateTime"] <= end_time_iso]

        observations = []
        for _, row in df.iterrows():
            obs = normalize_raw_observation(
                raw=row.to_dict(),
                source="ReplayFixture",
                data_status=self.data_status,
                mode=self.mode,
            )
            if obs:
                observations.append(obs)

        return observations

    def get_track(
        self,
        mmsi: Union[str, int],
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
        scenario_id: Optional[int] = None,
        csv_path: Optional[Union[str, Path]] = None,
    ) -> Optional[VesselTrack]:
        """Retrieve reconstructed VesselTrack with gap analysis."""
        obs = self.get_positions(
            mmsi=mmsi,
            start_time_iso=start_time_iso,
            end_time_iso=end_time_iso,
            scenario_id=scenario_id,
            csv_path=csv_path,
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
        scenario_id: Optional[int] = None,
        csv_path: Optional[Union[str, Path]] = None,
    ) -> List[VesselTrack]:
        """Retrieve reconstructed tracks for all vessels matching query."""
        obs_list = self.get_positions(
            bbox=bbox,
            start_time_iso=start_time_iso,
            end_time_iso=end_time_iso,
            scenario_id=scenario_id,
            csv_path=csv_path,
        )
        if not obs_list:
            return []

        # Group by MMSI
        by_mmsi: Dict[str, List[AISObservation]] = {}
        for o in obs_list:
            if mmsis is not None:
                if str(o.mmsi) not in [str(m) for m in mmsis]:
                    continue
            by_mmsi.setdefault(o.mmsi, []).append(o)

        tracks = []
        for mmsi_key, v_obs in by_mmsi.items():
            t = build_track(v_obs)
            tracks.append(t)

        return tracks

    def get_vessel_static_data(self, mmsi: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Extract static vessel particulars from replay dataset."""
        track = self.get_track(mmsi=mmsi)
        if not track or not track.observations:
            return None
        obs = track.observations[0]
        return {
            "mmsi": obs.mmsi,
            "ship_name": track.ship_name or obs.ship_name or "UNKNOWN",
            "ship_type": track.ship_type or obs.ship_type or "UNKNOWN",
            "imo": track.imo or obs.imo,
            "length": obs.length,
            "beam": obs.beam,
            "draft": obs.draft,
            "source": obs.source,
            "data_status": self.data_status,
            "mode": self.mode,
        }
