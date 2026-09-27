import React, { useState, useEffect } from 'react';
import {
  AlertOctagon,
  Search,
  Filter,
  Download,
  Eye,
  RefreshCw,
  Calendar,
  ChevronRight,
  ShieldAlert,
} from 'lucide-react';
import { api } from '../api/client';
import { ProvenanceBadge } from '../components/ProvenanceBadge';
import { IncidentSummary } from '../types';

interface Props {
  onNavigate: (route: string, id?: string) => void;
}

export const IncidentsPage: React.FC<Props> = ({ onNavigate }) => {
  const [loading, setLoading] = useState(true);
  const [incidents, setIncidents] = useState<IncidentSummary[]>([]);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [confidenceFilter, setConfidenceFilter] = useState('');

  const loadIncidents = async () => {
    setLoading(true);
    try {
      const res = await api.listIncidents({
        search: search || undefined,
        status: statusFilter || undefined,
        confidence_tier: confidenceFilter || undefined,
      });
      setIncidents(res.incidents || []);
    } catch (err) {
      console.error('Failed to load incidents:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadIncidents();
  }, [statusFilter, confidenceFilter]);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    loadIncidents();
  };

  const handleExportGeoJSON = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      const geo = await api.getIncidentGeojson(id);
      const blob = new Blob([JSON.stringify(geo, null, 2)], { type: 'application/geo+json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${id}_layers.geojson`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(`Export failed: ${err.message}`);
    }
  };

  const handleExportJSON = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation();
    try {
      const data = await api.getIncident(id);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${id}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err: any) {
      alert(`Export failed: ${err.message}`);
    }
  };

  return (
    <div className="h-full flex flex-col overflow-hidden bg-m-bg p-4 space-y-4">
      {/* Page Header & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-m-border pb-3 shrink-0">
        <div>
          <h1 className="text-lg font-bold text-m-primary flex items-center gap-2">
            <AlertOctagon className="w-5 h-5 text-m-red" />
            Incident Registry & Forensics Archive
          </h1>
          <p className="text-xs text-m-muted">
            Validated SAR oil slick detections, hindcast drift vectors, and vessel attribution candidate dossiers.
          </p>
        </div>

        <button
          onClick={loadIncidents}
          disabled={loading}
          className="px-3 py-1.5 rounded bg-m-surface hover:bg-m-border border border-m-divider text-xs font-bold text-m-primary flex items-center gap-1.5 transition self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh Registry
        </button>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-white border border-m-border rounded-lg shrink-0">
        <form onSubmit={handleSearchSubmit} className="flex items-center gap-2 flex-1 min-w-[240px]">
          <div className="relative flex-1">
            <Search className="w-4 h-4 text-m-muted absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by Incident ID or Suspect Vessel Name..."
              className="w-full bg-m-bg border border-m-border rounded pl-9 pr-3 py-1.5 text-xs text-m-primary placeholder:text-m-muted focus:outline-none focus:border-cyan-500"
            />
          </div>
          <button type="submit" className="px-3 py-1.5 bg-m-blue hover:bg-m-blue/90 text-m-primary rounded text-xs font-bold transition">
            Search
          </button>
        </form>

        <div className="flex items-center gap-2">
          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="bg-m-bg border border-m-border rounded px-2.5 py-1.5 text-xs text-m-secondary focus:outline-none"
          >
            <option value="">All Statuses</option>
            <option value="OPEN">Open</option>
            <option value="RESOLVED">Resolved</option>
            <option value="ARCHIVED">Archived</option>
          </select>

          {/* Confidence Filter */}
          <select
            value={confidenceFilter}
            onChange={(e) => setConfidenceFilter(e.target.value)}
            className="bg-m-bg border border-m-border rounded px-2.5 py-1.5 text-xs text-m-secondary focus:outline-none"
          >
            <option value="">All Confidence Tiers</option>
            <option value="CONFIRMED_HIGH">High Confidence</option>
            <option value="PROBABLE_MEDIUM">Medium Confidence</option>
            <option value="POSSIBLE_LOW">Low Confidence</option>
          </select>
        </div>
      </div>

      {/* Incidents Table */}
      <div className="flex-1 bg-white border border-m-border rounded-lg overflow-hidden flex flex-col">
        <div className="overflow-x-auto flex-1">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-m-bg border-b border-m-border text-m-muted uppercase font-mono text-[10px] tracking-wider sticky top-0 z-10">
              <tr>
                <th className="py-2.5 px-4">Incident ID</th>
                <th className="py-2.5 px-3">Date / Region</th>
                <th className="py-2.5 px-3">Status</th>
                <th className="py-2.5 px-3">Slick Area</th>
                <th className="py-2.5 px-3">Confidence</th>
                <th className="py-2.5 px-3">Candidates</th>
                <th className="py-2.5 px-3">Primary Suspect</th>
                <th className="py-2.5 px-3">Provenance</th>
                <th className="py-2.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-800">
              {incidents.length === 0 ? (
                <tr>
                  <td colSpan={9} className="py-12 text-center text-m-muted text-xs">
                    {loading ? 'Querying backend incidents...' : 'No incident dossiers match criteria.'}
                  </td>
                </tr>
              ) : (
                incidents.map((inc) => {
                  const statusColor =
                    inc.status === 'OPEN'
                      ? 'bg-m-red-light/80 text-m-red border-m-red/30'
                      : inc.status === 'RESOLVED'
                      ? 'bg-m-green-light/80 text-m-green border-m-green/30'
                      : 'bg-slate-800 text-m-muted border-slate-700';

                  return (
                    <tr
                      key={inc.incident_id}
                      onClick={() => onNavigate('incidents', inc.incident_id)}
                      className="hover:bg-m-surface/60 cursor-pointer transition select-none group"
                    >
                      <td className="py-3 px-4 font-mono font-bold text-m-blue flex items-center gap-1.5">
                        <AlertOctagon className="w-3.5 h-3.5 text-m-red shrink-0" />
                        {inc.incident_id}
                      </td>

                      <td className="py-3 px-3 text-m-secondary">
                        <div>{inc.created_at ? new Date(inc.created_at).toLocaleDateString() : 'N/A'}</div>
                        <div className="text-[10px] text-m-muted">{inc.region_name}</div>
                      </td>

                      <td className="py-3 px-3">
                        <span className={`inline-block font-mono text-[10px] font-bold px-2 py-0.5 rounded border ${statusColor}`}>
                          {inc.status}
                        </span>
                      </td>

                      <td className="py-3 px-3 font-mono font-semibold text-m-amber">
                        {inc.spill_area_km2 > 0 ? `${inc.spill_area_km2.toFixed(2)} km²` : 'Clean / 0.00'}
                      </td>

                      <td className="py-3 px-3">
                        <span className="font-semibold text-m-primary">{inc.confidence_tier}</span>
                        <span className="text-[10px] text-m-muted block font-mono">
                          {Math.round(inc.model_confidence * 100)}%
                        </span>
                      </td>

                      <td className="py-3 px-3 font-mono font-bold text-m-primary">
                        {inc.candidate_count} vessels
                      </td>

                      <td className="py-3 px-3">
                        {inc.top_candidate_name ? (
                          <div>
                            <span className="font-semibold text-m-primary">{inc.top_candidate_name}</span>
                            <span className="text-[10px] text-m-muted block font-mono">
                              MMSI: {inc.top_candidate_mmsi} | Score: {inc.top_composite_score?.toFixed(3)}
                            </span>
                          </div>
                        ) : (
                          <span className="text-m-muted italic">None attributed</span>
                        )}
                      </td>

                      <td className="py-3 px-3">
                        <ProvenanceBadge type={inc.reality_labels?.satellite || 'REAL'} />
                      </td>

                      <td className="py-3 px-4 text-right space-x-1" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={(e) => handleExportGeoJSON(e, inc.incident_id)}
                          className="px-2 py-1 bg-m-bg hover:bg-m-surface border border-m-border text-m-secondary hover:text-m-blue rounded text-[11px] font-mono transition"
                          title="Export Incident GeoJSON"
                        >
                          GeoJSON
                        </button>
                        <button
                          onClick={(e) => handleExportJSON(e, inc.incident_id)}
                          className="px-2 py-1 bg-m-bg hover:bg-m-surface border border-m-border text-m-secondary hover:text-m-blue rounded text-[11px] font-mono transition"
                          title="Export Incident JSON"
                        >
                          JSON
                        </button>
                        <button
                          onClick={() => onNavigate('incidents', inc.incident_id)}
                          className="px-2.5 py-1 bg-m-blue/20 hover:bg-m-blue/30 border border-cyan-500/40 text-m-blue rounded text-[11px] font-bold transition inline-flex items-center gap-1"
                        >
                          Investigate <ChevronRight className="w-3 h-3" />
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
    </div>
  );
};
