"""
End-to-End Maritime Incident Pipeline.

Orchestrates the complete intelligence sequence:
1. Ingest satellite scene metadata
2. Load / process SAR scene
3. Execute SARSARSegmentor (U-Net)
4. Extract spill morphology & Fay spreading age
5. Evaluate environmental context (ERA5 Bragg wind & Optical fusion)
6. Compute Lagrangian backward drift hindcast
7. Ingest AIS replay / benchmark trajectories (ReplayAISProvider)
8. Evaluate AIS kinematics & integrity anomalies
9. Evaluate trajectory spatiotemporal intersections
10. Score candidate vessels via SuspicionScorer
11. Execute counterfactual forward simulation on top suspect
12. Project forward drift forecast
13. Assemble canonical Incident model with strict reality labels
14. Persist machine-readable JSON & GeoJSON dossiers
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import json
import time
import numpy as np
import pandas as pd
from shapely.geometry import Polygon, Point, mapping

from src.pipeline.models import (
    Incident,
    SatelliteObservation,
    SpillObservation,
    EnvironmentalEvidence,
    HindcastResult,
    AISCandidate,
    CounterfactualResult,
    ForecastResult,
    ProvenanceType,
)
from src.pipeline.state_machine import WatchState, WatchStateMachine
from src.detection.sar_segmentation import SARSARSegmentor
from src.detection.spill_properties import extract_spill_detections, estimate_spill_age_fay
from src.detection.environmental_context import EnvironmentalContextExtractor
from src.detection.confidence_estimator import ConfidenceEstimator
from src.detection.optical_fusion import OpticalFusionValidator
from src.drift_model.environmental_interpolator import EnvironmentalInterpolator
from src.drift_model.hindcast import BackwardDriftHindcaster
from src.drift_model.lagrangian_tracker import LagrangianDriftTracker
from src.drift_model.uncertainty import UncertaintyConeGenerator
from src.drift_model.counterfactual import CounterfactualTester
from src.ingestion.replay_ais import ReplayAISProvider
from src.ingestion.ais.historical_provider import HistoricalAISProvider
from src.ingestion.ais.gfw_historical_provider import GFWHistoricalAISProvider
from src.ais_analysis.kinematics import AISKinematicEngine
from src.ais_analysis.trajectory_intersection import TrajectoryIntersectionEngine
from src.ais_analysis.suspicion_scorer import SuspicionScorer, rank_suspect_vessels


def _pixel_to_geo_bbox(
    bbox_px: Tuple[int, int, int, int],
    geo_bbox: Tuple[float, float, float, float],
    img_shape: Tuple[int, int] = (256, 256),
) -> Tuple[float, float, float, float]:
    """Map pixel bounding box (min_x, min_y, max_x, max_y) to geographic (min_lon, min_lat, max_lon, max_lat)."""
    min_x, min_y, max_x, max_y = bbox_px
    min_lon, min_lat, max_lon, max_lat = geo_bbox
    h, w = img_shape

    g_min_lon = min_lon + (min_x / w) * (max_lon - min_lon)
    g_max_lon = min_lon + (max_x / w) * (max_lon - min_lon)
    g_max_lat = max_lat - (min_y / h) * (max_lat - min_lat)
    g_min_lat = max_lat - (max_y / h) * (max_lat - min_lat)

    return (float(g_min_lon), float(g_min_lat), float(g_max_lon), float(g_max_lat))


def _pixel_to_geo_coord(
    coord_px: Tuple[float, float],
    geo_bbox: Tuple[float, float, float, float],
    img_shape: Tuple[int, int] = (256, 256),
) -> Tuple[float, float]:
    """Map pixel coordinate (cx, cy) to geographic (lon, lat)."""
    cx, cy = coord_px
    min_lon, min_lat, max_lon, max_lat = geo_bbox
    h, w = img_shape

    lon = min_lon + (cx / w) * (max_lon - min_lon)
    lat = max_lat - (cy / h) * (max_lat - min_lat)
    return (float(lon), float(lat))


def run_incident_pipeline(
    scene_metadata: Dict[str, Any],
    model_path: str = "models/sar_unet_baseline_best.pt",
    era5_path: str = "data/weather/era5_wind_mediterranean_case_study.nc",
    oscar_path: str = "data/ocean_currents/oscar_currents_final_20240823.nc",
    optical_path: Optional[str] = "data/optical_images/sentinel2_l2a_mediterranean_fusion.tif",
    ais_scenario_id: int = 1,
    ais_csv_path: Optional[str] = None,
    ais_provider: Optional[Any] = None,
    output_dir: str = "data/results/incidents",
    device: str = "cpu",
    confidence_threshold: float = 0.5,
    allow_low_confidence: bool = False,
    wind_speed_override: Optional[float] = None,
    optical_eval_override: Optional[Dict[str, Any]] = None,
) -> Incident:
    """
    Execute complete end-to-end maritime incident investigation.
    """
    sm = WatchStateMachine(initial_state=WatchState.NEW_PRODUCT)
    created_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    incident_id = scene_metadata.get("incident_id") or f"INC_{int(time.time())}"
    region_name = scene_metadata.get("region_name", "Mediterranean Testbed")
    product_id = scene_metadata.get("product_id", f"S1_{incident_id}")
    obs_time = scene_metadata.get("acquisition_time", "2024-08-23T09:41:12Z")
    image_path = scene_metadata.get("image_path")
    geo_bbox = tuple(scene_metadata.get("bounding_box", (18.1, 34.3, 18.6, 34.7)))

    # Provider & Reality labels setup
    if ais_provider is not None:
        provider = ais_provider
    else:
        ais_cfg_path = Path("config/ais.yaml")
        cfg_mode = "replay"
        if ais_cfg_path.exists():
            import yaml
            try:
                with open(ais_cfg_path) as f:
                    ais_cfg = yaml.safe_load(f) or {}
                cfg_mode = ais_cfg.get("provider", {}).get("mode", "replay").lower()
            except Exception:
                cfg_mode = "replay"

        if scene_metadata.get("mode") == "HISTORICAL" or cfg_mode == "historical":
            hist_prov_type = ais_cfg.get("provider", {}).get("historical_provider", "").lower() if 'ais_cfg' in locals() else ""
            if hist_prov_type == "gfw" or os.getenv("GFW_API_TOKEN"):
                provider = GFWHistoricalAISProvider()
            else:
                provider = HistoricalAISProvider()
        elif cfg_mode == "live":
            from src.ingestion.ais.aisstream_provider import AISStreamProvider
            from src.ingestion.ais.live_provider import LiveAISProvider
            if os.getenv("AISSTREAM_API_KEY"):
                provider = AISStreamProvider()
            else:
                provider = LiveAISProvider()
        else:
            provider = ReplayAISProvider()

    ais_mode = getattr(provider, "mode", "REPLAY")
    ais_data_status = getattr(provider, "data_status", "SIMULATED")

    if ais_mode == "HISTORICAL":
        ais_reality = "REAL HISTORICAL (NOAA Marine Cadastre / National Archives)"
        ais_provenance_label = ProvenanceType.REAL.value
        ais_source_label = f"{type(provider).__name__} (Authoritative Historical Archives)"
    elif ais_mode == "LIVE":
        ais_reality = "REAL LIVE (Maritime Transponder Stream)"
        ais_provenance_label = ProvenanceType.REAL.value
        ais_source_label = f"{type(provider).__name__} (Live Maritime Feed)"
    else:
        ais_reality = "SIMULATED REPLAY (Controlled Benchmark)"
        ais_provenance_label = ProvenanceType.SIMULATED.value
        ais_source_label = "ReplayAISProvider (Adversarial Benchmark)"

    reality_labels = {
        "Satellite": "REAL ARCHIVED (Sentinel-1 SAR)",
        "Environment": "REAL ARCHIVED (ERA5 hourly / OSCAR daily)",
        "AIS": ais_reality,
        "Hindcast": "INFERRED (RK4 Backward Advection-Diffusion)",
        "Attribution": "MODEL-DERIVED (5-Factor Normalized)",
        "Counterfactual": "INFERRED (Forward Perturbation Resilience)",
        "Forecast": "INFERRED (RK4 Forward Forecast)",
    }

    sat_obs = SatelliteObservation(
        product_id=product_id,
        satellite_name=scene_metadata.get("satellite_name", "Sentinel-1"),
        sensor_type=scene_metadata.get("sensor_type", "SAR C-Band"),
        acquisition_time=obs_time,
        bounding_box=geo_bbox,
        image_path=str(image_path) if image_path else "",
        provenance=scene_metadata.get("provenance", ProvenanceType.REAL.value),
    )

    incident = Incident(
        incident_id=incident_id,
        status=WatchState.NEW_PRODUCT.value,
        created_at=created_at,
        updated_at=created_at,
        region_name=region_name,
        satellite_observation=sat_obs,
        reality_labels=reality_labels,
        execution_log=sm.get_log(),
    )

    # 1. Image Check
    if not image_path or not Path(image_path).exists():
        sm.transition(WatchState.FAILED, reason=f"SAR image file not found: {image_path}")
        incident.status = WatchState.FAILED.value
        incident.failure_reason = f"SAR image file not found: {image_path}"
        incident.execution_log = sm.get_log()
        _persist_incident(incident, output_dir)
        return incident

    # 2. SAR Inference
    sm.transition(WatchState.PROCESSING, reason="Starting SAR U-Net semantic segmentation")
    segmentor = SARSARSegmentor(model_path=model_path, device=device, num_classes=4)

    try:
        seg_res = segmentor.segment(image_path, threshold=confidence_threshold)
    except Exception as e:
        sm.transition(WatchState.FAILED, reason=f"SAR segmentation failed: {e}")
        incident.status = WatchState.FAILED.value
        incident.failure_reason = str(e)
        incident.execution_log = sm.get_log()
        _persist_incident(incident, output_dir)
        return incident

    oil_mask = seg_res["oil_mask"]
    oil_px_count = seg_res["oil_pixel_count"]

    if oil_px_count == 0:
        sm.transition(WatchState.NO_SPILL, reason="Zero oil spill pixels detected by SAR model")
        incident.status = WatchState.NO_SPILL.value
        incident.spill_observation = SpillObservation(
            detected=False,
            provenance=ProvenanceType.INFERRED.value,
        )
        incident.execution_log = sm.get_log()
        _persist_incident(incident, output_dir)
        return incident

    sm.transition(WatchState.POTENTIAL_SPILL, reason=f"Detected {oil_px_count} oil slick candidate pixels")

    # 3. Morphology & Fay Spreading
    probs_np = seg_res.get("probabilities")
    oil_prob = probs_np[1] if probs_np is not None else None
    lookalike_prob = probs_np[2] if probs_np is not None else None

    detections = extract_spill_detections(
        oil_binary_mask=oil_mask,
        pixel_resolution_meters=sat_obs.pixel_resolution_meters,
        min_area_pixels=15,
        probabilities=oil_prob,
        lookalike_probabilities=lookalike_prob,
    )

    if not detections:
        sm.transition(WatchState.NO_SPILL, reason="Candidate pixels rejected as speckle noise (<15 px)")
        incident.status = WatchState.NO_SPILL.value
        incident.spill_observation = SpillObservation(
            detected=False,
            provenance=ProvenanceType.INFERRED.value,
        )
        incident.execution_log = sm.get_log()
        _persist_incident(incident, output_dir)
        return incident

    primary = detections[0]
    spill_geo_bbox = _pixel_to_geo_bbox(primary.bounding_box, geo_bbox)
    spill_geo_centroid = _pixel_to_geo_coord(primary.centroid, geo_bbox)

    # Invert Fay spreading model to bound discharge age
    fay_age_hours = estimate_spill_age_fay(
        area_m2=primary.area_km2 * 1e6,
        initial_volume_m3=10.0,
    )

    # Approximate polygon GeoJSON
    p_min_lon, p_min_lat, p_max_lon, p_max_lat = spill_geo_bbox
    spill_poly = Polygon([
        (p_min_lon, p_min_lat),
        (p_max_lon, p_min_lat),
        (p_max_lon, p_max_lat),
        (p_min_lon, p_max_lat),
        (p_min_lon, p_min_lat),
    ])

    spill_obs = SpillObservation(
        detected=True,
        spill_id=primary.spill_id,
        area_pixels=primary.area_pixels,
        area_km2=primary.area_km2,
        perimeter_km=primary.perimeter_km,
        centroid=spill_geo_centroid,
        bounding_box=spill_geo_bbox,
        major_axis_km=round(primary.major_axis * sat_obs.pixel_resolution_meters / 1000.0, 3),
        minor_axis_km=round(primary.minor_axis * sat_obs.pixel_resolution_meters / 1000.0, 3),
        orientation_deg=primary.orientation_degrees,
        compactness=primary.compactness,
        elongation=primary.elongation,
        model_confidence=primary.model_probability,
        estimated_age_hours_fay=fay_age_hours,
        raw_detections_count=len(detections),
        polygon_geojson=mapping(spill_poly),
        provenance=ProvenanceType.INFERRED.value,
    )
    incident.spill_observation = spill_obs

    # 4. Environmental Validation & Confidence Gate
    sm.transition(WatchState.VALIDATING, reason="Verifying atmospheric wind regime and optical evidence")

    env_evidence = EnvironmentalEvidence(
        observation_time=obs_time,
        era5_source=era5_path,
        oscar_source=oscar_path,
        provenance=ProvenanceType.REAL.value,
    )

    wind_speed = 6.0 if wind_speed_override is None else wind_speed_override
    t_epoch = float(pd.to_datetime(obs_time, utc=True).timestamp())

    if Path(era5_path).exists():
        try:
            env_extractor = EnvironmentalContextExtractor(era5_netcdf_path=era5_path)
            w_info = env_extractor.get_context(
                lat=spill_geo_centroid[1],
                lon=spill_geo_centroid[0],
                timestamp_epoch=t_epoch,
            )
            if w_info.get("status") == "ERA5_CONTEXT_AVAILABLE":
                wind_speed = float(w_info.get("wind_speed_ms", 6.0))
                env_evidence.wind_speed_mps = round(wind_speed, 2)
                env_evidence.wind_direction_deg = round(float(w_info.get("wind_direction_deg", 0.0)), 1)
                env_evidence.wind_u = round(float(w_info.get("wind_u_ms", 0.0)), 3)
                env_evidence.wind_v = round(float(w_info.get("wind_v_ms", 0.0)), 3)
                env_evidence.bragg_regime = w_info.get("dampening_regime", "OPTIMAL_BRAGG_DAMPENING")
            else:
                env_evidence.bragg_regime = "ERA5_CONTEXT_UNAVAILABLE"
        except Exception:
            env_evidence.bragg_regime = "ERA5_READ_ERROR"
    else:
        env_evidence.provenance = ProvenanceType.UNAVAILABLE.value
        env_evidence.bragg_regime = "ERA5_NOT_FOUND"

    # Optical Fusion Check
    optical_eval = optical_eval_override
    if optical_eval is None and optical_path and Path(optical_path).exists():
        try:
            opt_validator = OpticalFusionValidator(geotiff_path=optical_path)
            bounds_dict = {
                "min_lon": p_min_lon,
                "min_lat": p_min_lat,
                "max_lon": p_max_lon,
                "max_lat": p_max_lat,
            }
            optical_eval = opt_validator.validate_detection(
                sar_mask=oil_mask,
                geo_bounds=bounds_dict,
                timestamp=obs_time,
            )
            env_evidence.optical_checked = True
            env_evidence.optical_result = optical_eval
        except Exception as e:
            env_evidence.optical_checked = False

    incident.environmental_evidence = env_evidence

    # Confidence Estimator Gate
    conf_estimator = ConfidenceEstimator()
    evaluated_primary = conf_estimator.evaluate_detection(
        detection=primary,
        wind_speed_ms=wind_speed,
        optical_context=optical_eval,
    )

    spill_obs.confidence_tier = getattr(evaluated_primary, "confidence_level", "MEDIUM")
    spill_obs.model_confidence = getattr(evaluated_primary, "segmentation_confidence", primary.model_probability)

    # Check for CleanSeaNet physical abstention (wind < 2.0 m/s specular water or wind > 14.0 m/s) or low confidence
    is_wind_abstention = (wind_speed < 2.0 or wind_speed > 14.0)
    if (spill_obs.confidence_tier in ("INSUFFICIENT", "LOW") or is_wind_abstention) and not allow_low_confidence:
        reason = "CleanSeaNet Abstention: Calm water specular reflection risk (wind < 2.0 m/s)" if wind_speed < 2.0 else (
            "CleanSeaNet Abstention: High wind wave breaking / dispersion (wind > 14.0 m/s)" if wind_speed > 14.0 else
            f"CleanSeaNet Abstention: Insufficient confidence ({spill_obs.confidence_tier})"
        )
        sm.transition(WatchState.FAILED, reason=reason)
        incident.status = WatchState.FAILED.value
        incident.failure_reason = reason
        incident.execution_log = sm.get_log()
        _persist_incident(incident, output_dir)
        return incident

    sm.transition(WatchState.SPILL_CONFIRMED, reason=f"Spill confirmed with {spill_obs.confidence_tier} confidence")

    # 5. Lagrangian Backward Hindcast
    sm.transition(WatchState.HINDCASTING, reason="Executing backward advection-diffusion trajectory hindcast")

    if not Path(era5_path).exists() or not Path(oscar_path).exists():
        sm.transition(WatchState.FAILED, reason="Environmental forcing datasets missing for drift tracking")
        incident.status = WatchState.FAILED.value
        incident.failure_reason = "Environmental forcing datasets missing"
        incident.execution_log = sm.get_log()
        _persist_incident(incident, output_dir)
        return incident

    try:
        interpolator = EnvironmentalInterpolator(
            era5_path=era5_path,
            oscar_path=oscar_path,
            default_windage=0.03,
            default_deflection_deg=5.0,
        )
        hindcaster = BackwardDriftHindcaster(
            interpolator=interpolator,
            default_windage_range=(0.025, 0.035),
            horizontal_diffusivity_kh=10.0,
        )

        lookback_hr = float(np.clip(fay_age_hours, 3.0, 14.0))

        hindcast_res = hindcaster.run_hindcast(
            spill_geometry=spill_geo_bbox,
            observation_time=obs_time,
            lookback_hours=lookback_hr,
            time_step_seconds=900.0,
            num_particles=100,
            random_seed=42,
        )

        conf_95 = hindcast_res["origin_confidence_regions"]["p95"]
        conf_50 = hindcast_res["origin_confidence_regions"]["p50"]
        source_poly_95 = conf_95["shapely_polygon"]
        origin_pt = (float(source_poly_95.centroid.x), float(source_poly_95.centroid.y))

        t_release = float(hindcast_res["timestamps_epoch"][-1])
        release_window = (t_release - 3600.0, t_release + 3600.0)

        incident.hindcast_result = HindcastResult(
            lookback_hours=lookback_hr,
            time_step_seconds=900.0,
            num_particles=100,
            release_window_start=pd.to_datetime(release_window[0], unit="s", utc=True).isoformat(),
            release_window_end=pd.to_datetime(release_window[1], unit="s", utc=True).isoformat(),
            origin_centroid=origin_pt,
            confidence_95_polygon=mapping(source_poly_95),
            confidence_50_polygon=mapping(conf_50["shapely_polygon"]),
            provenance=ProvenanceType.INFERRED.value,
        )
    except Exception as e:
        sm.transition(WatchState.FAILED, reason=f"Hindcast failed: {e}")
        incident.status = WatchState.FAILED.value
        incident.failure_reason = f"Hindcast failed: {e}"
        incident.execution_log = sm.get_log()
        _persist_incident(incident, output_dir)
        return incident

    # 6. AIS Ingestion & Reconstruction
    sm.transition(WatchState.AIS_RECONSTRUCTION, reason="Retrieving and filtering candidate AIS vessel voyages")

    try:
        if isinstance(provider, (HistoricalAISProvider, GFWHistoricalAISProvider)):
            origin_bounds = source_poly_95.bounds if hasattr(source_poly_95, "bounds") else geo_bbox
            rel_start_iso = pd.to_datetime(release_window[0], unit="s", utc=True).isoformat() if isinstance(release_window[0], (int, float)) else str(release_window[0])
            rel_end_iso = pd.to_datetime(release_window[1], unit="s", utc=True).isoformat() if isinstance(release_window[1], (int, float)) else str(release_window[1])
            hist_tracks = provider.get_tracks(
                bbox=origin_bounds,
                start_time_iso=rel_start_iso,
                end_time_iso=rel_end_iso,
            )
            if hist_tracks:
                dfs = [t.to_dataframe() for t in hist_tracks if not t.to_dataframe().empty]
                df_ais = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading", "VesselName", "VesselType", "Draft"])
                incident.reality_labels["AIS"] = f"REAL HISTORICAL ({len(hist_tracks)} tracks from authoritative archives)"
            else:
                df_ais = pd.DataFrame(columns=["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading", "VesselName", "VesselType", "Draft"])
                incident.reality_labels["HistoricalAIS"] = "HISTORICAL AIS COVERAGE INSUFFICIENT"
                incident.reality_labels["AIS"] = "HISTORICAL AIS UNAVAILABLE (Live AIS cannot reconstruct traffic at the historical SAR acquisition time)"
                incident.failure_reason = "Live AIS cannot reconstruct traffic at the historical SAR acquisition time."
        elif isinstance(provider, ReplayAISProvider):
            df_ais = provider.load_ais_data(scenario_id=ais_scenario_id, csv_path=ais_csv_path)
        else:
            from src.ingestion.ais.live_buffer import LiveAISBuffer
            live_buffer = LiveAISBuffer(buffer_hours=48.0, minimum_track_points=1)
            rel_start_iso = (
                pd.to_datetime(release_window[0], unit="s", utc=True).strftime("%Y-%m-%dT%H:%M:%SZ")
                if isinstance(release_window[0], (int, float))
                else str(release_window[0])
            )
            obs_list = provider.get_positions(
                bbox=geo_bbox,
                start_time_iso=rel_start_iso,
                end_time_iso=obs_time,
            )
            if not obs_list:
                direct_tracks = provider.get_tracks(
                    bbox=geo_bbox,
                    start_time_iso=rel_start_iso,
                    end_time_iso=obs_time,
                )
                for tr in direct_tracks:
                    live_buffer.add_observations(tr.observations)
            else:
                live_buffer.add_observations(obs_list)

            candidate_tracks = live_buffer.get_candidate_tracks_for_incident(
                spill_time_iso=obs_time,
                release_window_start_iso=rel_start_iso,
                origin_polygon=source_poly_95,
            )
            if not candidate_tracks and len(live_buffer) > 0:
                candidate_tracks = live_buffer.get_vessel_tracks(
                    start_time_iso=rel_start_iso,
                    end_time_iso=obs_time,
                    bbox=geo_bbox,
                )
            if candidate_tracks:
                dfs = [t.to_dataframe() for t in candidate_tracks if not t.to_dataframe().empty]
                df_ais = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame(columns=["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading", "VesselName", "VesselType", "Draft"])
            else:
                df_ais = pd.DataFrame(columns=["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading", "VesselName", "VesselType", "Draft"])
    except Exception as e:
        sm.transition(WatchState.FAILED, reason=f"Failed to load AIS data: {e}")
        incident.status = WatchState.FAILED.value
        incident.failure_reason = f"AIS data unavailable: {e}"
        incident.execution_log = sm.get_log()
        _persist_incident(incident, output_dir)
        return incident

    kinematic_engine = AISKinematicEngine()
    intersection_engine = TrajectoryIntersectionEngine(temporal_tolerance_seconds=5400.0)
    scorer = SuspicionScorer()

    # 7. Attribution Scoring
    sm.transition(WatchState.ATTRIBUTION, reason="Evaluating multi-factor suspicion scores across candidate vessels")

    vessel_mmsis = df_ais["MMSI"].unique()
    candidate_scores = []

    for mmsi in vessel_mmsis:
        v_df = df_ais[df_ais["MMSI"] == mmsi].sort_values("BaseDateTime").reset_index(drop=True)
        v_name = str(v_df.at[0, "VesselName"])
        v_type = float(v_df.at[0, "VesselType"])

        kin_res = kinematic_engine.analyze_trajectory(v_df)
        inter_res = intersection_engine.evaluate_intersection(
            vessel_df=v_df,
            source_polygon=source_poly_95,
            source_time_window=release_window,
        )

        first_draft = float(v_df["Draft"].iloc[0]) if "Draft" in v_df else 0.0
        last_draft = float(v_df["Draft"].iloc[-1]) if "Draft" in v_df else 0.0
        draft_change = last_draft - first_draft

        v_profile = {
            "mmsi": int(mmsi),
            "vessel_name": v_name,
            "vessel_type": v_type,
            "draft_change": draft_change,
            "intersection": inter_res,
            "kinematics": kin_res,
        }

        v_score = scorer.score_vessel(v_profile, hindcast_res)
        candidate_scores.append(v_score)

        line_coords = [[float(r["LON"]), float(r["LAT"])] for _, r in v_df.iterrows()]
        track_geojson = {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": line_coords},
            "properties": {"mmsi": int(mmsi), "vessel_name": v_name},
        }

        eb = v_score["evidence_breakdown"]
        dec = str(v_score["attribution_decision"])
        if dec == "PRIMARY_SUSPECT":
            tier = "HIGH-CONSISTENCY CANDIDATE"
        elif dec == "PLAUSIBLE_CANDIDATE":
            tier = "MODERATE-CONSISTENCY CANDIDATE"
        else:
            tier = "LOW-CONSISTENCY CANDIDATE"

        c_obj = AISCandidate(
            mmsi=int(mmsi),
            vessel_name=v_name,
            vessel_type=v_type,
            composite_score=float(v_score["composite_suspicion_score"]),
            attribution_decision=dec,
            consistency_tier=tier,
            spatial_score=float(eb.get("spatial_compatibility", 0.0)),
            temporal_score=float(eb.get("temporal_compatibility", 0.0)),
            trajectory_score=float(eb.get("trajectory_compatibility", 0.0)),
            gap_score=float(eb.get("ais_integrity", 0.0)),
            type_score=float(eb.get("vessel_prior", 0.0)),
            draft_score=float(eb.get("draft_prior", 0.0)),
            min_distance_nm=float(eb.get("min_distance_nm", 999.0)),
            residence_time_minutes=float(eb.get("residence_time_minutes", 0.0)),
            anomalies=kin_res.get("anomalies", []),
            track_geojson=track_geojson,
            provenance=ais_provenance_label,
            source_identifier=ais_source_label,
        )
        incident.candidates.append(c_obj)

    ranked = rank_suspect_vessels(candidate_scores, top_n=len(candidate_scores))
    top_score_dict = ranked[0] if ranked else None

    if top_score_dict:
        top_mmsi = int(top_score_dict["mmsi"])
        for c_item in incident.candidates:
            if c_item.mmsi == top_mmsi:
                incident.top_candidate = c_item
                break

    if not candidate_scores:
        if ais_mode == "LIVE":
            incident.attribution_status = "INSUFFICIENT AIS COVERAGE"
        else:
            incident.attribution_status = "NO CANDIDATES"
    else:
        incident.attribution_status = "ATTRIBUTION_RESOLVED"

    # 8. Counterfactual Analysis
    sm.transition(WatchState.COUNTERFACTUAL, reason="Executing environmental perturbation resilience tests")

    cf_res_obj = CounterfactualResult(provenance=ProvenanceType.INFERRED.value)
    if incident.top_candidate and incident.top_candidate.attribution_decision in ("PRIMARY_SUSPECT", "PLAUSIBLE_CANDIDATE"):
        try:
            cf_tester = CounterfactualTester(interpolator=interpolator, windage_factor=0.03)
            cf_run = cf_tester.test_candidate_release(
                candidate_release_coord=origin_pt,
                candidate_release_time=t_release,
                observed_spill_geometry=spill_geo_bbox,
                observation_time=obs_time,
                num_particles=100,
            )
            cf_res_obj.candidate_mmsi = incident.top_candidate.mmsi
            cf_res_obj.candidate_name = incident.top_candidate.vessel_name
            cf_res_obj.tested = True
            cf_res_obj.verdict = str(cf_run["counterfactual_verdict"])
            cf_res_obj.plausibility_score = float(cf_run["physical_plausibility_score"])
            cf_res_obj.centroid_offset_km = float(cf_run["centroid_offset_km"])
            cf_res_obj.footprint_iou = float(cf_run["footprint_iou"])
        except Exception as e:
            cf_res_obj.verdict = f"ERROR: {e}"

    incident.counterfactual_result = cf_res_obj

    # 9. Forward Forecast
    sm.transition(WatchState.FORECASTING, reason="Simulating forward drift projection across next 12 hours")

    try:
        tracker = LagrangianDriftTracker(
            interpolator=interpolator,
            windage_factor=0.03,
            deflection_angle_deg=5.0,
            horizontal_diffusivity_kh=10.0,
        )
        # Seed ensemble around slick centroid for realistic 12h dispersion envelope
        rng = np.random.default_rng(42)
        spread_deg = 0.005
        forecast_seeds = [
            (spill_geo_centroid[0] + rng.normal(0, spread_deg), spill_geo_centroid[1] + rng.normal(0, spread_deg))
            for _ in range(50)
        ]
        forecast_sim = tracker.simulate(
            seed_positions=forecast_seeds,
            start_time=obs_time,
            duration_seconds=12.0 * 3600.0,
            time_step_seconds=900.0,
            direction=1,
            random_seed=42,
        )

        future_pts = forecast_sim["trajectories"][:, -1, :]
        future_centroid = (float(future_pts[:, 0].mean()), float(future_pts[:, 1].mean()))

        u_gen = UncertaintyConeGenerator(horizontal_diffusivity_kh=10.0)
        future_poly_dict = u_gen.build_confidence_polygon(future_pts, confidence_level=0.95)
        future_geom = future_poly_dict.get("geometry") or mapping(future_poly_dict["shapely_polygon"])

        incident.forecast_result = ForecastResult(
            forecast_hours=12.0,
            time_step_seconds=900.0,
            num_particles=len(forecast_seeds),
            future_window_end=forecast_sim["end_time_iso"],
            future_centroid=future_centroid,
            future_envelope_polygon=future_geom,
            provenance=ProvenanceType.INFERRED.value,
        )
    except Exception as e:
        incident.forecast_result = ForecastResult(
            forecast_hours=0.0,
            time_step_seconds=0.0,
            num_particles=0,
            future_window_end=obs_time,
            future_centroid=spill_geo_centroid,
            provenance=ProvenanceType.UNAVAILABLE.value,
        )

    # 10. Finalize Incident
    if incident.attribution_status == "INSUFFICIENT AIS COVERAGE":
        sm.transition(WatchState.AIS_COVERAGE_INSUFFICIENT, reason="No candidate vessel transponder broadcasts found intersecting hindcast origin region")
        incident.status = WatchState.AIS_COVERAGE_INSUFFICIENT.value
    else:
        sm.transition(WatchState.INCIDENT_READY, reason="All pipeline stages executed successfully")
        incident.status = WatchState.INCIDENT_READY.value
    incident.updated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    incident.execution_log = sm.get_log()

    # 11. Persist Result & Derived GeoJSON
    _persist_incident(incident, output_dir)

    return incident


def _persist_incident(incident: Incident, output_dir: Union[str, Path]) -> None:
    """Save machine-readable JSON and derived GeoJSON layers."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    incident_file = out_path / f"{incident.incident_id}.json"
    incident.save(str(incident_file))

    features = []

    if incident.spill_observation and incident.spill_observation.polygon_geojson:
        features.append({
            "type": "Feature",
            "geometry": incident.spill_observation.polygon_geojson,
            "properties": {
                "layer": "SPILL_DETECTION",
                "area_km2": incident.spill_observation.area_km2,
                "confidence_tier": incident.spill_observation.confidence_tier,
            },
        })

    if incident.hindcast_result and incident.hindcast_result.confidence_95_polygon:
        features.append({
            "type": "Feature",
            "geometry": incident.hindcast_result.confidence_95_polygon,
            "properties": {
                "layer": "HINDCAST_ORIGIN_95",
                "lookback_hours": incident.hindcast_result.lookback_hours,
            },
        })

    if incident.forecast_result and incident.forecast_result.future_envelope_polygon:
        features.append({
            "type": "Feature",
            "geometry": incident.forecast_result.future_envelope_polygon,
            "properties": {
                "layer": "FORECAST_PROJECTION_12H",
                "forecast_hours": incident.forecast_result.forecast_hours,
            },
        })

    for cand in incident.candidates:
        if cand.track_geojson:
            feat = dict(cand.track_geojson)
            feat["properties"].update({
                "layer": "CANDIDATE_VESSEL_TRACK",
                "composite_score": cand.composite_score,
                "decision": cand.attribution_decision,
            })
            features.append(feat)

    if features:
        geojson_doc = {"type": "FeatureCollection", "features": features}
        geojson_file = out_path / f"{incident.incident_id}_layers.geojson"
        with open(geojson_file, "w") as f:
            json.dump(geojson_doc, f, indent=2)
