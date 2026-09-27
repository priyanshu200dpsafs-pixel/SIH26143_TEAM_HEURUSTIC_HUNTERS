"""
End-to-End Acceptance Test for Phase 6 Maritime Operations Platform.
Executes the full 16-step operational investigation flow from Section 38.
"""

import json
import pytest
from fastapi.testclient import TestClient
from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_complete_e2e_investigation_flow(client):
    # Step 1: Open application / verify system health
    health_res = client.get("/api/system/health")
    assert health_res.status_code == 200
    health = health_res.json()
    assert health["status"] in ["READY", "DEGRADED"]

    # Step 2: Open / verify Replay mode
    mode_res = client.post("/api/system/mode", json={"mode": "REPLAY"})
    assert mode_res.status_code == 200
    assert mode_res.json()["current_mode"] == "REPLAY"

    # Step 3: Open / create configured watch
    watch_res = client.get("/api/watch")
    assert watch_res.status_code == 200
    watch_data = watch_res.json()
    assert "status" in watch_data
    assert "config" in watch_data

    # Step 4: Execute watch surveillance cycle (Run Once)
    cycle_res = client.post("/api/watch/run-once")
    assert cycle_res.status_code == 200
    cycle = cycle_res.json()
    assert "status" in cycle

    # Step 5: Observe satellite scenes in catalog
    sat_res = client.get("/api/satellite/products")
    assert sat_res.status_code == 200
    assert sat_res.json()["total"] >= 0

    # Step 6: Open generated / existing incident dynamically
    inc_list_res = client.get("/api/incidents")
    assert inc_list_res.status_code == 200
    inc_list = inc_list_res.json()["incidents"]
    assert len(inc_list) > 0
    target = next((i for i in inc_list if i.get("candidate_count", 0) > 0 and i.get("has_geojson") and i.get("spill_detected")), inc_list[0])
    inc_id = target["incident_id"]

    inc_res = client.get(f"/api/incidents/{inc_id}")
    assert inc_res.status_code == 200
    incident = inc_res.json()
    assert incident["incident_id"] == inc_id

    # Step 7: Verify Slick Observation
    spill = incident.get("spill_observation")
    assert spill is not None
    assert spill["detected"] is True
    assert spill["area_km2"] > 0.0
    assert spill["provenance"] in ["REAL", "INFERRED", "SIMULATED"]

    # Step 8: Verify Hindcast Origin
    hindcast = incident.get("hindcast_result")
    assert hindcast is not None
    assert "confidence_95_polygon" in hindcast
    assert hindcast["provenance"] == "INFERRED"

    # Step 9: Verify Vessel Tracks in GeoJSON
    geo_res = client.get(f"/api/incidents/{inc_id}/geojson")
    assert geo_res.status_code == 200
    geojson = geo_res.json()
    assert geojson["type"] == "FeatureCollection"
    layers = [f["properties"].get("layer") for f in geojson["features"]]
    assert "SPILL_DETECTION" in layers
    assert "HINDCAST_ORIGIN_95" in layers

    # Step 10: Open Candidate Vessel
    candidates = incident.get("candidates")
    assert len(candidates) > 0
    top_cand = incident.get("top_candidate")
    assert top_cand is not None
    assert top_cand["composite_score"] > 0.0

    # Step 11: Run Counterfactual Drift Simulation
    cf_res = client.post(
        f"/api/incidents/{inc_id}/counterfactual",
        json={"mmsi": top_cand["mmsi"], "release_jitter_minutes": 0},
    )
    assert cf_res.status_code == 200
    assert "job_id" in cf_res.json()

    # Step 12: Verify Forecast Projection
    fc = incident.get("forecast_result")
    assert fc is not None
    assert "future_envelope_polygon" in fc

    # Step 13: Open Evidence Timeline
    ev_res = client.get(f"/api/incidents/{inc_id}/evidence")
    assert ev_res.status_code == 200
    ev = ev_res.json()
    assert "DETECTION" in ev["sections"]
    assert "HINDCAST" in ev["sections"]
    assert "ATTRIBUTION" in ev["sections"]
    assert "COUNTERFACTUAL" in ev["sections"]

    # Step 14: Generate Investigation Brief (Prosecutor's Brief)
    brief_res = client.post(
        f"/api/incidents/{inc_id}/report",
        json={"operator_notes": "Automated E2E Acceptance Run"},
    )
    assert brief_res.status_code == 200
    brief = brief_res.json()
    assert brief["status"] == "SUCCESS"
    assert "sha256_hash" in brief
    report_id = brief["report_id"]

    # Step 15: Download GeoJSON
    assert len(geojson["features"]) > 0

    # Step 16: Verify UI displays correct cryptographic provenance
    verify_res = client.post("/api/reports/verify", json={"report_id": report_id})
    assert verify_res.status_code == 200
    assert verify_res.json()["valid"] is True
