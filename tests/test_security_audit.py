"""
Security & Data Isolation Audit Tests for AEGIS-SAR Platform.
"""

from pathlib import Path
import os
import pytest
from fastapi.testclient import TestClient
from src.api.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_path_traversal_protection_incidents(client):
    # Attempt path traversal on incident detail
    res = client.get("/api/incidents/..%2F..%2Fetc%2Fpasswd")
    assert res.status_code in [400, 404]

    res2 = client.get("/api/incidents/invalid..id")
    assert res2.status_code in [400, 404]


def test_path_traversal_protection_reports(client):
    # Attempt path traversal on report download
    res = client.get("/api/reports/..%2F..%2Fetc%2Fpasswd/download")
    assert res.status_code in [400, 404]

    res2 = client.get("/api/reports/invalid..id/download")
    assert res2.status_code in [400, 404]


def test_settings_secrets_masked(client):
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()

    # Verify no raw secrets exposed
    raw_str = str(data)
    assert "password" not in raw_str.lower()
    assert "secret" not in raw_str.lower() or "credentials_state" in raw_str
    assert data["satellite"]["credentials_state"] in ["CONFIGURED", "NOT_CONFIGURED"]
    assert data["ais"]["credentials_state"] in ["CONFIGURED", "NOT_CONFIGURED"]


def test_frontend_bundle_secret_leak_audit():
    assets_dir = Path("frontend/dist/assets")
    assert assets_dir.exists(), "Frontend bundle must be built before security audit"

    js_files = list(assets_dir.glob("*.js"))
    assert len(js_files) > 0

    forbidden_patterns = [
        "CDSE_CLIENT_SECRET",
        "COPERNICUS_API_KEY",
        "AWS_SECRET_ACCESS_KEY",
        "PRIVATE KEY",
        "BEGIN RSA PRIVATE KEY",
        "GFW_API_TOKEN",
    ]

    for js_file in js_files:
        with open(js_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
        for pat in forbidden_patterns:
            assert pat not in content, f"Secret pattern '{pat}' detected in compiled frontend bundle: {js_file.name}"


def test_cors_headers(client):
    res = client.options(
        "/api/system/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.status_code == 200
    assert "access-control-allow-origin" in res.headers
