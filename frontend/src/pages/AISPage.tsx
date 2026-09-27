import React, { useState, useEffect } from 'react';
import {
  Ship,
  RefreshCw,
  Activity,
  AlertTriangle,
  Play,
  Square,
  Search,
  CheckCircle2,
  XCircle,
  FileDown,
  X,
  Compass,
} from 'lucide-react';
import { api } from '../api/client';
import { MapLibreView } from '../components/MapLibreView';
import { ProvenanceBadge } from '../components/ProvenanceBadge';
import { AISVesselSummary } from '../types';

interface Props {
  onNavigate: (route: string, id?: string) => void;
  initialMmsi?: string;
}

export const AISPage: React.FC<Props> = ({ onNavigate, initialMmsi }) => {
  const [loading, setLoading] = useState(true);
  const [vessels, setVessels] = useState<AISVesselSummary[]>([]);
  const [aisStatus, setAisStatus] = useState<any>(null);
  const [search, setSearch] = useState('');
  const [bufferHours, setBufferHours] = useState(48);
  const [testResult, setTestResult] = useState<any>(null);

  // Vessel Detail Modal State
  const [selectedVessel, setSelectedVessel] = useState<any>(null);
  const [vesselTrackGeojson, setVesselTrackGeojson] = useState<any>(null);
  const [modalLoading, setModalLoading] = useState(false);

  const loadAIS = async () => {
    setLoading(true);
    try {
      const [stRes, vesRes] = await Promise.all([
        api.getAISStatus(),
        api.listAISVessels(search || undefined, 100),
      ]);
      setAisStatus(stRes);
      setVessels(vesRes.vessels || []);
      if (stRes.buffer_history_hours) {
        setBufferHours(stRes.buffer_history_hours);
      }
    } catch (err) {
      console.error('Failed to load AIS data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAIS();
  }, [search]);

  useEffect(() => {
    if (initialMmsi && vessels.length > 0) {
      handleOpenVessel(parseInt(initialMmsi, 10));
    }
  }, [initialMmsi, vessels]);

  const handleTestConnection = async () => {
    try {
      const res = await api.testAIS();
      setTestResult(res);
    } catch (err: any) {
      setTestResult({ success: false, status: 'ERROR', message: err.message });
    }
  };

  const handleRefreshBuffer = async () => {
    try {
      const res = await api.refreshAISBuffer();
      alert(`Buffer Refreshed: ${res.buffer_size} total observations staged.`);
      await loadAIS();
    } catch (err: any) {
      alert(`Buffer refresh failed: ${err.message}`);
    }
  };

  const handleOpenVessel = async (mmsi: number) => {
    setModalLoading(true);
    setSelectedVessel(null);
    setVesselTrackGeojson(null);
    try {
      const detail = await api.getAISVessel(mmsi);
      setSelectedVessel(detail);
      if (detail.track_geojson) {
        setVesselTrackGeojson({
          type: 'FeatureCollection',
          features: [detail.track_geojson],
        });
      }
    } catch (err: any) {
      alert(`Could not load vessel detail: ${err.message}`);
    } finally {
      setModalLoading(false);
    }
  };

  const handleExportTrack = (mmsi: number) => {
    if (!selectedVessel?.track_geojson) return;
    const blob = new Blob([JSON.stringify(selectedVessel.track_geojson, null, 2)], { type: 'application/geo+json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `vessel_${mmsi}_track.geojson`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="h-full flex flex-col overflow-hidden bg-m-bg p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-m-border pb-3 shrink-0">
        <div>
          <h1 className="text-lg font-bold text-m-primary flex items-center gap-2">
            <Ship className="w-5 h-5 text-m-blue" />
            AIS Vessel Traffic & Trajectory Operations
          </h1>
          <p className="text-xs text-m-muted">
            Real-time buffer, sliding observation windows, kinematics evaluation, and AIS transponder integrity verification.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={handleTestConnection}
            className="px-3 py-1.5 rounded bg-m-surface hover:bg-m-border border border-m-divider text-xs font-bold text-m-primary flex items-center gap-1.5 transition"
          >
            <Activity className="w-3.5 h-3.5 text-m-blue" /> Test Connection
          </button>
          <button
            onClick={handleRefreshBuffer}
            className="px-3 py-1.5 rounded bg-sky-600 hover:bg-sky-500 text-m-primary text-xs font-bold flex items-center gap-1.5 transition"
          >
            <RefreshCw className="w-3.5 h-3.5" /> Refresh Buffer
          </button>
        </div>
      </div>

      {testResult && (
        <div className={`p-2.5 rounded border text-xs flex items-center justify-between ${
          testResult.success ? 'bg-m-green-light/80 border-m-green/30 text-m-green' : 'bg-m-red-light/80 border-m-red/30 text-rose-300'
        }`}>
          <div className="flex items-center gap-2">
            {testResult.success ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
            <span><strong>Connection Test ({testResult.status}):</strong> {testResult.message}</span>
          </div>
          <button onClick={() => setTestResult(null)} className="text-m-muted hover:text-m-primary">✕</button>
        </div>
      )}

      {/* Provider Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 shrink-0">
        <div className="m-card-flat p-3 rounded">
          <div className="flex justify-between items-center mb-1">
            <span className="text-[10px] font-mono text-m-muted uppercase">Provider Mode</span>
            <ProvenanceBadge type={aisStatus?.provenance || 'REAL'} />
          </div>
          <div className="text-sm font-bold text-m-primary">{aisStatus?.provider_mode || 'REPLAY'}</div>
          <div className="text-[10px] text-m-muted mt-1">Class: {aisStatus?.provider_class}</div>
        </div>

        <div className="m-card-flat p-3 rounded">
          <div className="flex justify-between items-center mb-1">
            <span className="text-[10px] font-mono text-m-muted uppercase">Connection Status</span>
            <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
              aisStatus?.connection_status === 'CONNECTED' ? 'bg-m-green-light text-m-green' : 'bg-m-amber-light text-m-amber'
            }`}>
              {aisStatus?.connection_status || 'UNKNOWN'}
            </span>
          </div>
          <div className="text-sm font-bold text-m-primary">{aisStatus?.connection_status}</div>
          <div className="text-[10px] text-m-muted mt-1">
            Configured: {aisStatus?.is_configured ? 'Yes' : 'No'}
          </div>
        </div>

        <div className="m-card-flat p-3 rounded">
          <div className="flex justify-between items-center mb-1">
            <span className="text-[10px] font-mono text-m-muted uppercase">Sliding Buffer</span>
            <span className="text-[10px] font-mono text-m-blue font-bold">{bufferHours}h window</span>
          </div>
          <div className="text-sm font-bold text-m-blue">{aisStatus?.buffer_size_observations || 0} obs</div>
          <div className="text-[10px] text-m-muted mt-1">{vessels.length} distinct vessels tracked</div>
        </div>

        <div className="m-card-flat p-3 rounded">
          <div className="flex justify-between items-center mb-1">
            <span className="text-[10px] font-mono text-m-muted uppercase">Integrity Diagnostics</span>
            <span className="text-[10px] font-mono text-m-muted">Transponder</span>
          </div>
          <div className="text-sm font-bold text-m-primary">
            {vessels.filter((v) => v.integrity_state !== 'NORMAL').length} Anomalies Flagged
          </div>
          <div className="text-[10px] text-m-muted mt-1">Speed/acceleration/gap limits enforced</div>
        </div>
      </div>

      {/* Vessel Filter & Table */}
      <div className="flex-1 bg-white border border-m-border rounded-lg overflow-hidden flex flex-col">
        <div className="p-3 border-b border-m-border bg-m-bg flex items-center justify-between">
          <div className="relative w-72">
            <Search className="w-3.5 h-3.5 text-m-muted absolute left-2.5 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by MMSI or Vessel Name..."
              className="w-full bg-white border border-m-border rounded pl-8 pr-3 py-1 text-xs text-m-primary placeholder:text-m-muted focus:outline-none focus:border-sky-500"
            />
          </div>
          <span className="text-[10px] font-mono text-m-muted">Total Vessels: {vessels.length}</span>
        </div>

        <div className="overflow-x-auto flex-1">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-m-bg text-m-muted uppercase font-mono text-[10px] tracking-wider sticky top-0">
              <tr>
                <th className="py-2.5 px-4">MMSI</th>
                <th className="py-2.5 px-3">Vessel Name</th>
                <th className="py-2.5 px-3">Type / IMO</th>
                <th className="py-2.5 px-3">Coordinates</th>
                <th className="py-2.5 px-3">SOG / COG</th>
                <th className="py-2.5 px-3">Latest Time (UTC)</th>
                <th className="py-2.5 px-3">Integrity State</th>
                <th className="py-2.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-800">
              {vessels.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-m-muted text-xs">
                    {loading ? 'Reading vessel positions from AIS buffer...' : 'No vessels currently active in buffer.'}
                  </td>
                </tr>
              ) : (
                vessels.map((v) => {
                  let integrityBadge = 'bg-slate-800 text-m-muted';
                  if (v.integrity_state === 'ANOMALOUS') integrityBadge = 'bg-m-red-light text-m-red border border-m-red/30';
                  else if (v.integrity_state === 'GAPS_DETECTED') integrityBadge = 'bg-m-amber-light text-m-amber border border-m-amber/30';
                  else integrityBadge = 'bg-m-green-light text-m-green border border-m-green/30';

                  return (
                    <tr
                      key={v.mmsi}
                      onClick={() => handleOpenVessel(v.mmsi)}
                      className="hover:bg-m-surface/60 cursor-pointer transition select-none"
                    >
                      <td className="py-3 px-4 font-mono font-bold text-m-blue">{v.mmsi}</td>
                      <td className="py-3 px-3 font-semibold text-m-primary">{v.vessel_name}</td>
                      <td className="py-3 px-3 text-m-secondary">
                        <div>{v.vessel_type || 'Vessel'}</div>
                        <div className="text-[10px] text-m-muted font-mono">IMO: {v.imo || 'N/A'}</div>
                      </td>
                      <td className="py-3 px-3 font-mono text-[11px] text-m-secondary">
                        {v.latitude.toFixed(4)}°, {v.longitude.toFixed(4)}°
                      </td>
                      <td className="py-3 px-3 font-mono text-m-blue">
                        {v.speed_over_ground?.toFixed(1) || '0.0'} kn @ {v.course_over_ground?.toFixed(0) || '0'}°
                      </td>
                      <td className="py-3 px-3 font-mono text-[10px] text-m-muted">
                        {v.timestamp ? new Date(v.timestamp).toLocaleString() : 'N/A'}
                      </td>
                      <td className="py-3 px-3">
                        <span className={`inline-block font-mono text-[10px] font-bold px-1.5 py-0.5 rounded ${integrityBadge}`}>
                          {v.integrity_state}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleOpenVessel(v.mmsi);
                          }}
                          className="px-2.5 py-1 bg-sky-600/20 hover:bg-sky-600/30 border border-sky-500/40 text-sky-300 rounded text-[11px] font-bold"
                        >
                          View Track
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Vessel Detail Modal with Trajectory Map */}
      {selectedVessel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
          <div className="w-full max-w-4xl bg-white border border-m-border rounded-lg shadow-popup overflow-hidden flex flex-col h-[80vh]">
            <div className="flex items-center justify-between px-4 py-3 border-b border-m-border bg-m-bg">
              <div className="flex items-center gap-2">
                <Ship className="w-4 h-4 text-m-blue" />
                <span className="text-xs font-bold text-m-primary uppercase tracking-wider">
                  Vessel Trajectory Profile: {selectedVessel.vessel_name} (MMSI: {selectedVessel.mmsi})
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleExportTrack(selectedVessel.mmsi)}
                  className="px-2.5 py-1 bg-m-surface hover:bg-m-border border border-m-divider text-xs font-mono text-m-primary rounded flex items-center gap-1"
                >
                  <FileDown className="w-3.5 h-3.5" /> Export Track
                </button>
                <button onClick={() => setSelectedVessel(null)} className="text-m-muted hover:text-m-primary">
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            <div className="flex-1 flex overflow-hidden">
              {/* Left Vessel Stats */}
              <div className="w-72 bg-m-bg border-r border-m-border p-3 overflow-y-auto text-xs font-mono space-y-3">
                <div>
                  <span className="text-m-muted text-[10px] uppercase block mb-1">Identity & Dimensions</span>
                  <div className="space-y-1 text-m-secondary">
                    <div>MMSI: <span className="text-m-blue font-bold">{selectedVessel.mmsi}</span></div>
                    <div>IMO: <span className="text-m-primary">{selectedVessel.imo || 'N/A'}</span></div>
                    <div>Type: <span className="text-m-primary">{selectedVessel.vessel_type || 'N/A'}</span></div>
                    <div>Length: <span className="text-m-primary">{selectedVessel.length_m || 'N/A'} m</span></div>
                    <div>Draft: <span className="text-m-primary">{selectedVessel.draft_m || 'N/A'} m</span></div>
                  </div>
                </div>

                <div className="pt-2 border-t border-m-border">
                  <span className="text-m-muted text-[10px] uppercase block mb-1">Kinematic Anomalies ({selectedVessel.anomalies?.length || 0})</span>
                  {selectedVessel.anomalies?.length === 0 ? (
                    <div className="text-[11px] text-m-green">Zero kinematic anomalies detected.</div>
                  ) : (
                    <div className="space-y-1 text-[10px]">
                      {selectedVessel.anomalies.map((a: any, idx: number) => (
                        <div key={idx} className="p-1.5 bg-m-red-light border border-transparent rounded text-rose-300">
                          {a.anomaly_type}: {a.description}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <div className="pt-2 border-t border-m-border">
                  <span className="text-m-muted text-[10px] uppercase block mb-1">Relevant Spill Incidents</span>
                  {selectedVessel.relevant_incidents?.length === 0 ? (
                    <div className="text-[11px] text-m-muted italic">No correlated incidents.</div>
                  ) : (
                    <div className="space-y-1">
                      {selectedVessel.relevant_incidents.map((ri: any) => (
                        <button
                          key={ri.incident_id}
                          onClick={() => {
                            setSelectedVessel(null);
                            onNavigate('incidents', ri.incident_id);
                          }}
                          className="w-full p-2 bg-white hover:bg-m-surface border border-m-border rounded text-left"
                        >
                          <div className="text-m-blue font-bold">{ri.incident_id}</div>
                          <div className="text-[10px] text-m-muted">Decision: {ri.attribution_decision}</div>
                          <div className="text-[10px] text-m-amber">Score: {ri.composite_score?.toFixed(3)}</div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {/* Right Trajectory Map */}
              <div className="flex-1 relative">
                <MapLibreView
                  geojson={vesselTrackGeojson}
                  initialCenter={[
                    selectedVessel.latest_observation?.longitude || 18.35,
                    selectedVessel.latest_observation?.latitude || 34.5,
                  ]}
                  initialZoom={10}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
