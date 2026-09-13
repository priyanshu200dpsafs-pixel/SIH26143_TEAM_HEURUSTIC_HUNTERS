"""
End-to-End Evaluation of Attribution & Counterfactual Engines across all 7 Benchmark Scenarios.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import json
import pandas as pd
import numpy as np

from src.drift_model.environmental_interpolator import EnvironmentalInterpolator
from src.drift_model.hindcast import BackwardDriftHindcaster
from src.drift_model.counterfactual import CounterfactualTester
from src.ais_analysis.kinematics import AISKinematicEngine
from src.ais_analysis.trajectory_intersection import TrajectoryIntersectionEngine
from src.ais_analysis.suspicion_scorer import SuspicionScorer, rank_suspect_vessels

BENCHMARK_DIR = PROJECT_ROOT / "data" / "ais" / "synthetic" / "benchmarks"
TRUTH_DIR = BENCHMARK_DIR / "ground_truth"

ERA5_PATH = PROJECT_ROOT / "data" / "weather" / "era5_wind_mediterranean_case_study.nc"
OSCAR_PATH = PROJECT_ROOT / "data" / "ocean_currents" / "oscar_currents_final_20240823.nc"


def run_benchmark_suite():
    print("=" * 80)
    print("EXECUTING BENCHMARK SUITE ACROSS ALL 7 ADVERSARIAL SCENARIOS")
    print("=" * 80)

    # 1. Initialize engines
    interpolator = EnvironmentalInterpolator(
        era5_path=str(ERA5_PATH),
        oscar_path=str(OSCAR_PATH),
        default_windage=0.03,
        default_deflection_deg=5.0,
    )
    hindcaster = BackwardDriftHindcaster(
        interpolator=interpolator,
        default_windage_range=(0.025, 0.035),
        horizontal_diffusivity_kh=10.0,
    )
    kinematic_engine = AISKinematicEngine()
    intersection_engine = TrajectoryIntersectionEngine(temporal_tolerance_seconds=5400.0)  # 1.5h buffer
    scorer = SuspicionScorer()
    counterfactual_tester = CounterfactualTester(interpolator=interpolator, windage_factor=0.03)

    # 2. Run backward hindcast once for the target slick
    observed_slick_poly = (18.30, 34.45, 18.40, 34.55)  # bounding box around (18.35, 34.50)
    obs_time_iso = "2024-08-23T09:41:12Z"
    lookback_hr = 8.5

    print(f"[*] Running backward Lagrangian hindcast (lookback: {lookback_hr} hours)...")
    hindcast_res = hindcaster.run_hindcast(
        spill_geometry=observed_slick_poly,
        observation_time=obs_time_iso,
        lookback_hours=lookback_hr,
        time_step_seconds=900.0,  # 15 min
        num_particles=100,
        random_seed=42,
    )

    source_poly_95 = hindcast_res["origin_confidence_regions"]["p95"]["shapely_polygon"]
    release_t_epoch = float(hindcast_res["timestamps_epoch"][-1])
    release_t_window = (release_t_epoch - 3600.0, release_t_epoch + 3600.0)

    print(f"[✓] Hindcast complete. 95% origin confidence region centroid: {source_poly_95.centroid.x:.3f}°E, {source_poly_95.centroid.y:.3f}°N")

    manifest_file = BENCHMARK_DIR / "benchmark_manifest.json"
    with open(manifest_file) as f:
        manifest = json.load(f)

    results_summary = []

    for item in manifest:
        scn_id = int(item["scenario_id"])
        scn_name = item["name"]
        print(f"\n" + "-" * 75)
        print(f"EVALUATING SCENARIO {scn_id}: {scn_name.upper()}")
        print("-" * 75)

        ais_csv = BENCHMARK_DIR / item["ais_file"]
        meta_json = BENCHMARK_DIR / item["meta_file"]
        truth_json = TRUTH_DIR / item["truth_file"]

        df_ais = pd.read_csv(ais_csv)
        with open(truth_json) as f:
            truth = json.load(f)

        vessels = df_ais["MMSI"].unique()
        vessel_scores = []

        for mmsi in vessels:
            v_df = df_ais[df_ais["MMSI"] == mmsi].sort_values("BaseDateTime").reset_index(drop=True)
            v_name = v_df.at[0, "VesselName"]
            v_type = v_df.at[0, "VesselType"]

            # Kinematics analysis
            kin_res = kinematic_engine.analyze_trajectory(v_df)

            # Trajectory intersection
            inter_res = intersection_engine.evaluate_intersection(
                vessel_df=v_df,
                source_polygon=source_poly_95,
                source_time_window=release_t_window,
            )

            # Draft change
            first_draft = float(v_df["Draft"].iloc[0])
            last_draft = float(v_df["Draft"].iloc[-1])
            draft_change = last_draft - first_draft

            # Build profile & score
            v_profile = {
                "mmsi": int(mmsi),
                "vessel_name": str(v_name),
                "vessel_type": float(v_type),
                "draft_change": float(draft_change),
                "intersection": inter_res,
                "kinematics": kin_res,
            }

            v_score = scorer.score_vessel(v_profile, hindcast_res)
            vessel_scores.append(v_score)

        ranked = rank_suspect_vessels(vessel_scores, top_n=len(vessel_scores))

        top_candidate = ranked[0]
        top_decision = top_candidate["attribution_decision"]
        top_mmsi = int(top_candidate["mmsi"])
        top_score = float(top_candidate["composite_suspicion_score"])

        # Run counterfactual on top candidate if candidate intersects
        cf_metric = None
        if top_decision in ("PRIMARY_SUSPECT", "PLAUSIBLE_CANDIDATE"):
            # Use release point estimate
            cand_rel_coord = (source_poly_95.centroid.x, source_poly_95.centroid.y)
            cf_res = counterfactual_tester.test_candidate_release(
                candidate_release_coord=cand_rel_coord,
                candidate_release_time=release_t_epoch,
                observed_spill_geometry=observed_slick_poly,
                observation_time=obs_time_iso,
                num_particles=100,
            )
            cf_metric = {
                "offset_km": float(cf_res["centroid_offset_km"]),
                "iou": float(cf_res["footprint_iou"]),
                "score": float(cf_res["physical_plausibility_score"]),
                "verdict": str(cf_res["counterfactual_verdict"]),
            }

        # Compare with hidden ground truth
        expected_culprit = truth["ground_truth_culprit_mmsi"]
        if expected_culprit is not None:
            expected_culprit = int(expected_culprit)
            correct_identification = (top_mmsi == expected_culprit) and (top_decision == "PRIMARY_SUSPECT")
        else:
            # Expected no culprit attributed (exoneration, abstention, or ghost ship)
            correct_identification = (top_decision not in ("PRIMARY_SUSPECT",))

        print(f"Top Ranked Vessel: {top_candidate['vessel_name']} (MMSI: {top_mmsi})")
        print(f"Decision:          {top_decision} (Score: {top_score:.3f})")
        print(f"Ground Truth:      {truth['ground_truth_culprit_name']} (MMSI: {expected_culprit})")
        print(f"Benchmark Verdict: {'PASSED [CORRECT]' if correct_identification else 'FAILED [MISMATCH]'}")
        if cf_metric:
            print(f"Counterfactual:    Offset {cf_metric['offset_km']} km, Plausibility: {cf_metric['score']} ({cf_metric['verdict']})")

        results_summary.append({
            "scenario_id": scn_id,
            "scenario_name": scn_name,
            "top_candidate_name": str(top_candidate["vessel_name"]),
            "top_candidate_mmsi": int(top_mmsi),
            "composite_score": float(top_score),
            "attribution_decision": str(top_decision),
            "ground_truth_name": str(truth["ground_truth_culprit_name"]),
            "ground_truth_mmsi": expected_culprit,
            "passed": bool(correct_identification),
            "counterfactual": cf_metric,
        })

    print("\n" + "=" * 80)
    print("BENCHMARK EXECUTION SUMMARY REPORT")
    print("=" * 80)
    total_scenarios = len(results_summary)
    passed_scenarios = sum(1 for r in results_summary if r["passed"])
    print(f"Scenarios Passed: {passed_scenarios} / {total_scenarios} ({passed_scenarios/total_scenarios*100:.1f}%)")
    for r in results_summary:
        status_icon = "✓" if r["passed"] else "✗"
        print(f"[{status_icon}] Scenario {r['scenario_id']} ({r['scenario_name']}): {r['attribution_decision']} -> Match: {r['passed']}")

    summary_file = BENCHMARK_DIR / "benchmark_evaluation_results.json"
    with open(summary_file, "w") as f:
        json.dump(results_summary, f, indent=2)
    print(f"\n[+] Saved detailed benchmark evaluation results to: {summary_file}")
    return results_summary


if __name__ == "__main__":
    run_benchmark_suite()
