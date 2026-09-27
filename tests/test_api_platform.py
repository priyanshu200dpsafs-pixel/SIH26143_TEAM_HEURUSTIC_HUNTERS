"""
Automated Integration Tests for Phase 6 Operational Platform API.
"""

import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.api.state import global_app_state, GlobalMode


@pytest.fixture
def client():
    return TestClient(app)


def test_system_health(client):
    res = client.get("/api/system/health")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert data["storage"]["writable"] is True
    assert data["model"]["weights_present"] is True


def test_system_mode_switch(client):
    # Switch to BENCHMARK
    res = client.post("/api/system/mode", json={"mode": "BENCHMARK"})
    assert res.status_code == 200
    assert res.json()["current_mode"] == "BENCHMARK"

    # Switch back to REPLAY
    res = client.post("/api/system/mode", json={"mode": "REPLAY"})
    assert res.status_code == 200
    assert res.json()["current_mode"] == "REPLAY"


def test_watch_endpoints(client):
    res = client.get("/api/watch")
    assert res.status_code == 200
    data = res.json()
    assert "status" in data
    assert "config" in data

    # Test run-once
    res_once = client.post("/api/watch/run-once")
    assert res_once.status_code == 200
    assert "status" in res_once.json()


def test_satellite_endpoints(client):
    res = client.get("/api/satellite/products")
    assert res.status_code == 200
    data = res.json()
    assert "products" in data
    assert "total" in data


def test_incidents_endpoints(client):
    res = client.get("/api/incidents")
    assert res.status_code == 200
    data = res.json()
    assert "incidents" in data
    assert len(data["incidents"]) > 0

    # Test detail for INC_S1_SPILL_TRI
    inc_id = "INC_S1_SPILL_TRI"
    res_detail = client.get(f"/api/incidents/{inc_id}")
    assert res_detail.status_code == 200
    detail = res_detail.json()
    assert detail["incident_id"] == inc_id
    assert "spill_observation" in detail

    # Test GeoJSON
    res_geo = client.get(f"/api/incidents/{inc_id}/geojson")
    assert res_geo.status_code == 200
    geo = res_geo.json()
    assert geo["type"] == "FeatureCollection"
    assert len(geo["features"]) > 0

    # Test Evidence
    res_ev = client.get(f"/api/incidents/{inc_id}/evidence")
    assert res_ev.status_code == 200
    ev = res_ev.json()
    assert "sections" in ev
    assert "DETECTION" in ev["sections"]
    assert "HINDCAST" in ev["sections"]


def test_ais_endpoints(client):
    res = client.get("/api/ais/status")
    assert res.status_code == 200
    data = res.json()
    assert "connection_status" in data
    assert "buffer_size_observations" in data

    res_vessels = client.get("/api/ais/vessels")
    assert res_vessels.status_code == 200
    assert "vessels" in res_vessels.json()


def test_attribution_analysis(client):
    res = client.get("/api/analysis/incident/INC_S1_SPILL_TRI")
    assert res.status_code == 200
    data = res.json()
    assert data["incident_id"] == "INC_S1_SPILL_TRI"
    assert "candidates" in data


def test_reports_workflow(client):
    # Compile report
    compile_res = client.post("/api/reports/compile", json={"incident_id": "INC_S1_SPILL_TRI", "operator_notes": "API test brief"})
    assert compile_res.status_code == 200
    rep = compile_res.json()["report"]
    report_id = rep["report_id"]

    # Verify report hash
    verify_res = client.post("/api/reports/verify", json={"report_id": report_id})
    assert verify_res.status_code == 200
    assert verify_res.json()["valid"] is True

    # List reports
    list_res = client.get("/api/reports")
    assert list_res.status_code == 200
    assert list_res.json()["total"] > 0


def test_global_search(client):
    res = client.get("/api/search?q=INC_S1")
    assert res.status_code == 200
    data = res.json()
    assert data["total_matches"] > 0
    assert len(data["results"]["INCIDENTS"]) > 0


def test_settings_endpoints(client):
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert "surveillance" in data
    assert "satellite" in data
    assert "ais" in data
    assert data["satellite"]["credentials_state"] in ["CONFIGURED", "NOT_CONFIGURED"]
