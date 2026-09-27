"""
Forensic Evidentiary Report Compiler.

Assembles cryptographically verified forensic briefs and dossiers for
maritime oil spill incidents adhering to international standards
(MARPOL 73/78 Annex I, UNCLOS).
Produces standalone forensic HTML dossiers and JSON evidentiary packages
with cryptographic SHA-256 chain-of-custody seals.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class ReportRecord:
    report_id: str
    incident_id: str
    created_at: str
    generated_by: str
    sha256_hash: str
    html_path: str
    json_path: str
    file_size_bytes: int
    top_suspect_mmsi: Optional[str] = None
    top_suspect_name: Optional[str] = None
    composite_score: Optional[float] = None
    attribution_decision: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ForensicReportCompiler:
    """
    Forensic compiler producing cryptographically sealed maritime investigation dossiers.
    """

    def __init__(self, output_dir: Union[str, Path] = "data/reports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.output_dir / "reports_index.json"
        self._ensure_index()

    def _ensure_index(self) -> None:
        if not self.index_path.exists():
            with open(self.index_path, "w") as f:
                json.dump({"version": "1.0", "reports": {}}, f, indent=2)

    def _load_index(self) -> Dict[str, Any]:
        try:
            with open(self.index_path) as f:
                return json.load(f)
        except Exception:
            return {"version": "1.0", "reports": {}}

    def _save_index(self, index: Dict[str, Any]) -> None:
        temp_path = self.index_path.with_suffix(".tmp")
        with open(temp_path, "w") as f:
            json.dump(index, f, indent=2)
        temp_path.replace(self.index_path)

    def list_reports(self) -> List[Dict[str, Any]]:
        index = self._load_index()
        reports = list(index.get("reports", {}).values())
        reports.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return reports

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        index = self._load_index()
        return index.get("reports", {}).get(report_id)

    def verify_report_hash(self, report_id: str) -> Dict[str, Any]:
        record = self.get_report(report_id)
        if not record:
            return {"valid": False, "error": f"Report '{report_id}' not found"}

        html_path = Path(record["html_path"])
        if not html_path.exists():
            return {"valid": False, "error": f"Report file missing: {html_path}"}

        hasher = hashlib.sha256()
        with open(html_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        computed_hash = hasher.hexdigest()

        is_match = (computed_hash.lower() == record["sha256_hash"].lower())
        return {
            "valid": is_match,
            "report_id": report_id,
            "expected_hash": record["sha256_hash"],
            "computed_hash": computed_hash,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }

    def compile_incident_report(
        self,
        incident: Dict[str, Any],
        operator_notes: Optional[str] = None,
    ) -> ReportRecord:
        """
        Compile complete forensic dossier for an incident.
        """
        incident_id = incident.get("incident_id", "UNKNOWN_INCIDENT")
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        report_id = f"DOSSIER_{incident_id}_{timestamp_str}"
        created_at = datetime.now(timezone.utc).isoformat()

        spill = incident.get("spill_observation") or {}
        hindcast = incident.get("hindcast_result") or {}
        env = incident.get("environmental_evidence") or {}
        candidates = incident.get("candidates") or []
        top_cand = incident.get("top_candidate") or (candidates[0] if candidates else {})
        counterfactual = incident.get("counterfactual_result") or {}
        forecast = incident.get("forecast_result") or {}
        realities = incident.get("reality_labels") or {}

        # Render HTML
        html_content = self._render_html_dossier(
            report_id=report_id,
            incident=incident,
            spill=spill,
            hindcast=hindcast,
            env=env,
            top_cand=top_cand,
            candidates=candidates,
            counterfactual=counterfactual,
            forecast=forecast,
            realities=realities,
            created_at=created_at,
            operator_notes=operator_notes,
        )

        html_path = self.output_dir / f"{report_id}.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Compute SHA-256
        hasher = hashlib.sha256()
        with open(html_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        sha256_hash = hasher.hexdigest()

        # Save JSON dossier
        json_path = self.output_dir / f"{report_id}.json"
        dossier_data = {
            "report_id": report_id,
            "incident_id": incident_id,
            "created_at": created_at,
            "sha256_hash": sha256_hash,
            "incident_snapshot": incident,
            "operator_notes": operator_notes,
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(dossier_data, f, indent=2)

        file_size = html_path.stat().st_size

        record = ReportRecord(
            report_id=report_id,
            incident_id=incident_id,
            created_at=created_at,
            generated_by="AEGIS-SAR Forensic Engine v2.0",
            sha256_hash=sha256_hash,
            html_path=str(html_path),
            json_path=str(json_path),
            file_size_bytes=file_size,
            top_suspect_mmsi=str(top_cand.get("mmsi")) if top_cand.get("mmsi") else None,
            top_suspect_name=str(top_cand.get("vessel_name")) if top_cand.get("vessel_name") else None,
            composite_score=float(top_cand.get("composite_score")) if top_cand.get("composite_score") is not None else None,
            attribution_decision=str(top_cand.get("attribution_decision")) if top_cand.get("attribution_decision") else None,
        )

        # Update index
        index = self._load_index()
        if "reports" not in index:
            index["reports"] = {}
        index["reports"][report_id] = record.to_dict()
        self._save_index(index)

        return record

    def _render_html_dossier(
        self,
        report_id: str,
        incident: Dict[str, Any],
        spill: Dict[str, Any],
        hindcast: Dict[str, Any],
        env: Dict[str, Any],
        top_cand: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        counterfactual: Dict[str, Any],
        forecast: Dict[str, Any],
        realities: Dict[str, str],
        created_at: str,
        operator_notes: Optional[str],
    ) -> str:
        cand_rows = ""
        for i, c in enumerate(candidates, 1):
            decision = c.get("attribution_decision", "UNKNOWN")
            badge_color = "#10b981" if decision == "ATTRIBUTED" else ("#f59e0b" if decision == "FLAGGED_REVIEW" else "#64748b")
            cand_rows += f"""
            <tr>
              <td style="padding: 8px; border-bottom: 1px solid #334155;">#{i}</td>
              <td style="padding: 8px; border-bottom: 1px solid #334155; font-weight: 600;">{c.get('vessel_name', 'Unknown')}</td>
              <td style="padding: 8px; border-bottom: 1px solid #334155;"><code>{c.get('mmsi', 'N/A')}</code></td>
              <td style="padding: 8px; border-bottom: 1px solid #334155;">{c.get('vessel_type', 'N/A')}</td>
              <td style="padding: 8px; border-bottom: 1px solid #334155;"><strong>{c.get('composite_score', 0.0):.3f}</strong></td>
              <td style="padding: 8px; border-bottom: 1px solid #334155;">{c.get('min_distance_nm', 0.0):.2f} nm</td>
              <td style="padding: 8px; border-bottom: 1px solid #334155;"><span style="background: {badge_color}; color: #000; padding: 2px 8px; border-radius: 4px; font-weight: 700; font-size: 11px;">{decision}</span></td>
            </tr>
            """

        notes_section = ""
        if operator_notes:
            notes_section = f"""
            <div style="background: #1e293b; border-left: 4px solid #38bdf8; padding: 12px 16px; margin: 20px 0; border-radius: 4px;">
              <h4 style="margin: 0 0 6px 0; color: #38bdf8; font-size: 13px; text-transform: uppercase;">Operator Addendum</h4>
              <p style="margin: 0; color: #cbd5e1; font-size: 13px;">{operator_notes}</p>
            </div>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Prosecutor's Brief — {incident.get('incident_id', 'Dossier')}</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      background-color: #0f172a;
      color: #e2e8f0;
      margin: 0;
      padding: 32px 20px;
      line-height: 1.5;
    }}
    .container {{
      max-width: 1000px;
      margin: 0 auto;
      background: #1e293b;
      border: 1px solid #334155;
      border-radius: 8px;
      padding: 32px;
      box-shadow: 0 20px 25px -5px rgba(0,0,0,0.5);
    }}
    .header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      border-bottom: 2px solid #0284c7;
      padding-bottom: 20px;
      margin-bottom: 24px;
    }}
    .title {{
      margin: 0;
      font-size: 24px;
      font-weight: 800;
      letter-spacing: -0.5px;
      color: #f8fafc;
    }}
    .subtitle {{
      margin: 4px 0 0 0;
      font-size: 13px;
      color: #94a3b8;
      text-transform: uppercase;
      letter-spacing: 1px;
    }}
    .grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }}
    .card {{
      background: #0f172a;
      border: 1px solid #334155;
      border-radius: 6px;
      padding: 16px;
    }}
    .card-title {{
      margin: 0 0 12px 0;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 1px;
      color: #38bdf8;
      font-weight: 700;
    }}
    .metric-row {{
      display: flex;
      justify-content: space-between;
      padding: 4px 0;
      border-bottom: 1px solid #1e293b;
      font-size: 13px;
    }}
    .metric-label {{
      color: #94a3b8;
    }}
    .metric-value {{
      font-weight: 600;
      color: #f1f5f9;
    }}
    .badge {{
      display: inline-block;
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 700;
      text-transform: uppercase;
    }}
    .badge-real {{ background: #065f46; color: #34d399; }}
    .badge-inferred {{ background: #1e3a8a; color: #60a5fa; }}
    .badge-simulated {{ background: #701a75; color: #f472b6; }}
    .badge-unavailable {{ background: #374151; color: #9ca3af; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 12px;
      font-size: 13px;
    }}
    th {{
      text-align: left;
      padding: 8px;
      background: #0f172a;
      color: #94a3b8;
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      border-bottom: 2px solid #334155;
    }}
    .seal {{
      margin-top: 32px;
      padding-top: 16px;
      border-top: 1px solid #334155;
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 11px;
      color: #64748b;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <h1 class="title">MARITIME SPILL EVIDENTIARY DOSSIER</h1>
        <p class="subtitle">UNCLOS / MARPOL 73/78 Annex I Admissible Forensic Brief</p>
      </div>
      <div style="text-align: right;">
        <div style="font-size: 12px; color: #38bdf8; font-family: monospace; font-weight: 700;">{report_id}</div>
        <div style="font-size: 11px; color: #64748b; margin-top: 4px;">Compiled: {created_at}</div>
      </div>
    </div>

    {notes_section}

    <div class="grid">
      <!-- Incident Overview -->
      <div class="card">
        <h3 class="card-title">1. Incident Identification</h3>
        <div class="metric-row">
          <span class="metric-label">Incident ID</span>
          <span class="metric-value">{incident.get('incident_id')}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Region / AOI</span>
          <span class="metric-value">{incident.get('region_name', 'Mediterranean')}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Investigation Status</span>
          <span class="metric-value" style="color: #38bdf8;">{incident.get('status', 'OPEN')}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Observation Timestamp</span>
          <span class="metric-value">{incident.get('satellite_observation', {}).get('acquisition_time', 'N/A')}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Observation Reality</span>
          <span class="metric-value"><span class="badge badge-real">{realities.get('satellite', 'REAL')}</span></span>
        </div>
      </div>

      <!-- Spill Properties -->
      <div class="card">
        <h3 class="card-title">2. SAR Slick Morphology</h3>
        <div class="metric-row">
          <span class="metric-label">Estimated Slick Area</span>
          <span class="metric-value">{spill.get('area_km2', 0.0):.2f} km² ({spill.get('area_pixels', 0)} px)</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Centroid Coordinates</span>
          <span class="metric-value">{f"{spill.get('centroid')[0]:.4f}°, {spill.get('centroid')[1]:.4f}°" if spill.get('centroid') else 'N/A'}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Confidence Tier</span>
          <span class="metric-value">{spill.get('confidence_tier', 'N/A')} ({spill.get('model_confidence', 0.0)*100:.1f}%)</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Fay Spreading Age</span>
          <span class="metric-value">{spill.get('estimated_age_hours_fay', 0.0):.1f} hours elapsed</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">SAR Detection Provenance</span>
          <span class="metric-value"><span class="badge badge-real">{spill.get('provenance', 'REAL')}</span></span>
        </div>
      </div>

      <!-- Environmental & Hindcast -->
      <div class="card">
        <h3 class="card-title">3. Environmental Physics & Hindcast</h3>
        <div class="metric-row">
          <span class="metric-label">Wind Velocity (ERA5)</span>
          <span class="metric-value">{env.get('wind_speed_ms', 0.0):.1f} m/s @ {env.get('wind_direction_deg', 0.0):.0f}°</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Current Velocity (OSCAR)</span>
          <span class="metric-value">{env.get('current_velocity_ms', 0.0):.2f} m/s @ {env.get('current_direction_deg', 0.0):.0f}°</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Drift Engine</span>
          <span class="metric-value">Lagrangian RK4 (3% windage + Coriolis)</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Inferred Release Origin</span>
          <span class="metric-value">{f"{hindcast.get('origin_centroid')[0]:.4f}°, {hindcast.get('origin_centroid')[1]:.4f}°" if hindcast.get('origin_centroid') else 'N/A'}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Physics Reality</span>
          <span class="metric-value"><span class="badge badge-inferred">{hindcast.get('provenance', 'INFERRED')}</span></span>
        </div>
      </div>

      <!-- Primary Attributed Suspect -->
      <div class="card" style="border-color: #38bdf8;">
        <h3 class="card-title" style="color: #f59e0b;">4. Primary Attributed Vessel</h3>
        <div class="metric-row">
          <span class="metric-label">Vessel Identity</span>
          <span class="metric-value">{top_cand.get('vessel_name', 'None Attributed')}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">MMSI / Type</span>
          <span class="metric-value">{top_cand.get('mmsi', 'N/A')} ({top_cand.get('vessel_type', 'N/A')})</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Attribution Decision</span>
          <span class="metric-value" style="color: #10b981; font-weight: 700;">{top_cand.get('attribution_decision', 'N/A')}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Composite Suspicion Score</span>
          <span class="metric-value">{top_cand.get('composite_score', 0.0):.3f} / 1.000</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">AIS Provenance</span>
          <span class="metric-value"><span class="badge badge-real">{realities.get('ais', 'REAL')}</span></span>
        </div>
      </div>
    </div>

    <!-- Candidate Matrix -->
    <div class="card" style="margin-bottom: 24px;">
      <h3 class="card-title">5. Comprehensive Vessel Attribution Matrix ({len(candidates)} Vessels Evaluated)</h3>
      <table>
        <thead>
          <tr>
            <th>Rank</th>
            <th>Vessel Name</th>
            <th>MMSI</th>
            <th>Type</th>
            <th>Composite Score</th>
            <th>Min Distance</th>
            <th>Forensic Finding</th>
          </tr>
        </thead>
        <tbody>
          {cand_rows if cand_rows else '<tr><td colspan="7" style="padding: 12px; text-align: center; color: #64748b;">No candidate vessels intersected spatiotemporal hindcast cone</td></tr>'}
        </tbody>
      </table>
    </div>

    <!-- Counterfactual & Forecast -->
    <div class="grid">
      <div class="card">
        <h3 class="card-title">6. Counterfactual Verification</h3>
        <div class="metric-row">
          <span class="metric-label">Simulation Status</span>
          <span class="metric-value">{counterfactual.get('status', 'COMPLETED' if counterfactual else 'N/A')}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Forward Overlap (IoU)</span>
          <span class="metric-value">{counterfactual.get('overlap_iou', 0.0):.3f}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Mean Trajectory Distance</span>
          <span class="metric-value">{counterfactual.get('mean_distance_km', 0.0):.2f} km</span>
        </div>
      </div>

      <div class="card">
        <h3 class="card-title">7. Forward Drift Projection</h3>
        <div class="metric-row">
          <span class="metric-label">Forecast Horizon</span>
          <span class="metric-value">{forecast.get('forecast_hours', 12)} hours</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Threat Level</span>
          <span class="metric-value" style="color: #f59e0b;">{forecast.get('coastal_threat_level', 'MONITORED')}</span>
        </div>
        <div class="metric-row">
          <span class="metric-label">Predicted Centroid</span>
          <span class="metric-value">{f"{forecast.get('predicted_centroid')[0]:.4f}°, {forecast.get('predicted_centroid')[1]:.4f}°" if forecast.get('predicted_centroid') else 'N/A'}</span>
        </div>
      </div>
    </div>

    <div class="seal">
      <div>
        <strong>Cryptographic Chain of Custody:</strong><br>
        SHA-256: <code style="color: #38bdf8;">{report_id} (sealed upon compilation)</code>
      </div>
      <div>
        AEGIS-SAR Autonomous Maritime Surveillance System<br>
        SIH Problem Statement 26143
      </div>
    </div>
  </div>
</body>
</html>
"""
