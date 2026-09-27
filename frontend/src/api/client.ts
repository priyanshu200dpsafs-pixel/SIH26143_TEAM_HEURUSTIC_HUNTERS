import {
  SystemHealth,
  WatchStatus,
  WatchConfig,
  IncidentSummary,
  SatelliteProduct,
  AISVesselSummary,
  ReportRecord,
  AlertNotification,
  AsyncJob,
  GlobalMode,
} from '../types';

const API_BASE = '/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: {
      'Content-Type': 'application/json',
      ...(options?.headers || {}),
    },
    ...options,
  });
  if (!res.ok) {
    let errorMsg = `HTTP ${res.status} ${res.statusText}`;
    try {
      const errData = await res.json();
      if (errData.detail) errorMsg = errData.detail;
      else if (errData.message) errorMsg = errData.message;
    } catch {
      // ignore
    }
    throw new Error(errorMsg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  // System
  getHealth: () => fetchJson<SystemHealth>(`${API_BASE}/system/health`),
  getStatus: () => fetchJson<WatchStatus>(`${API_BASE}/system/status`),
  setMode: (mode: GlobalMode) =>
    fetchJson<{ status: string; current_mode: GlobalMode }>(`${API_BASE}/system/mode`, {
      method: 'POST',
      body: JSON.stringify({ mode }),
    }),
  getAuditLogs: (limit = 50, offset = 0) =>
    fetchJson<{ total: number; entries: any[] }>(`${API_BASE}/system/audit?limit=${limit}&offset=${offset}`),
  getAlerts: () => fetchJson<{ alerts: AlertNotification[]; unread_count: number }>(`${API_BASE}/alerts`),
  markAlertRead: (id: string) => fetchJson(`${API_BASE}/alerts/${id}/read`, { method: 'POST' }),
  clearAlerts: () => fetchJson(`${API_BASE}/alerts/clear`, { method: 'POST' }),

  // Watch
  getWatch: () => fetchJson<{ status: WatchStatus; config: any; ledger: any }>(`${API_BASE}/watch`),
  updateWatch: (config: WatchConfig) =>
    fetchJson<{ status: string; config: any }>(`${API_BASE}/watch`, {
      method: 'POST',
      body: JSON.stringify(config),
    }),
  startWatch: () => fetchJson<{ status: string; message: string }>(`${API_BASE}/watch/start`, { method: 'POST' }),
  stopWatch: () => fetchJson<{ status: string; message: string }>(`${API_BASE}/watch/stop`, { method: 'POST' }),
  pauseWatch: () => fetchJson<{ status: string; message: string }>(`${API_BASE}/watch/pause`, { method: 'POST' }),
  resumeWatch: () => fetchJson<{ status: string; message: string }>(`${API_BASE}/watch/resume`, { method: 'POST' }),
  runWatchOnce: () => fetchJson<any>(`${API_BASE}/watch/run-once`, { method: 'POST' }),
  deleteWatch: () => fetchJson(`${API_BASE}/watch`, { method: 'DELETE' }),

  // Satellite
  listSatelliteProducts: (status?: string, limit = 50) => {
    const q = status ? `?status=${status}&limit=${limit}` : `?limit=${limit}`;
    return fetchJson<{ total: number; products: SatelliteProduct[]; ledger_summary: any }>(`${API_BASE}/satellite/products${q}`);
  },
  getSatelliteProduct: (id: string) =>
    fetchJson<{ product: SatelliteProduct; local_file_exists: boolean; local_path: string | null; validation_report: any }>(
      `${API_BASE}/satellite/products/${id}`
    ),
  searchSatellite: (params: { min_lon: number; min_lat: number; max_lon: number; max_lat: number; start_time?: string; end_time?: string }) =>
    fetchJson<{ status: string; provider: string; count: number; products: any[]; message?: string }>(`${API_BASE}/satellite/search`, {
      method: 'POST',
      body: JSON.stringify(params),
    }),
  downloadProduct: (id: string) =>
    fetchJson<{ status: string; product_id: string; destination_path?: string; reason?: string }>(
      `${API_BASE}/satellite/products/${id}/download`,
      { method: 'POST' }
    ),
  validateProduct: (id: string) =>
    fetchJson<any>(`${API_BASE}/satellite/products/${id}/validate`, { method: 'POST' }),
  processProduct: (id: string) =>
    fetchJson<{ status: string; job_id: string; message: string }>(`${API_BASE}/satellite/products/${id}/process`, {
      method: 'POST',
    }),
  getProductResult: (id: string) =>
    fetchJson<{
      product_id: string;
      incident_id: string | null;
      acquisition_time: string;
      processing_status: string;
      geometry: any | null;
      geometry_hash: string | null;
      scene_footprint: any | null;
      footprint_validation: string;
      geometry_centroid: [number, number] | null;
      geometry_bbox: [number, number, number, number] | null;
    }>(`${API_BASE}/satellite/products/${id}/result`),

  // Incidents
  listIncidents: (params?: { status?: string; confidence_tier?: string; search?: string; provenance_category?: string; limit?: number; offset?: number }) => {
    const sp = new URLSearchParams();
    if (params?.status) sp.set('status', params.status);
    if (params?.confidence_tier) sp.set('confidence_tier', params.confidence_tier);
    if (params?.search) sp.set('search', params.search);
    if (params?.provenance_category) sp.set('provenance_category', params.provenance_category);
    if (params?.limit) sp.set('limit', String(params.limit));
    if (params?.offset) sp.set('offset', String(params.offset));
    return fetchJson<{ total: number; limit: number; offset: number; incidents: IncidentSummary[] }>(
      `${API_BASE}/incidents?${sp.toString()}`
    );
  },
  getIncident: (id: string) => fetchJson<any>(`${API_BASE}/incidents/${id}`),
  getIncidentGeojson: (id: string) => fetchJson<any>(`${API_BASE}/incidents/${id}/geojson`),
  getIncidentEvidence: (id: string) => fetchJson<{ incident_id: string; sections: Record<string, any> }>(`${API_BASE}/incidents/${id}/evidence`),
  rerunIncident: (id: string) => fetchJson<{ status: string; job_id: string }>(`${API_BASE}/incidents/${id}/rerun`, { method: 'POST' }),
  rerunHindcast: (id: string, req?: any) => fetchJson<{ status: string; job_id: string }>(`${API_BASE}/incidents/${id}/hindcast`, { method: 'POST', body: JSON.stringify(req || {}) }),
  rerunAIS: (id: string) => fetchJson<{ status: string; job_id: string }>(`${API_BASE}/incidents/${id}/ais`, { method: 'POST' }),
  runCounterfactual: (id: string, req: { mmsi: number; release_jitter_minutes?: number; spatial_jitter_km?: number }) =>
    fetchJson<{ status: string; job_id: string }>(`${API_BASE}/incidents/${id}/counterfactual`, { method: 'POST', body: JSON.stringify(req) }),
  runForecast: (id: string) => fetchJson<{ status: string; job_id: string }>(`${API_BASE}/incidents/${id}/forecast`, { method: 'POST' }),
  compileReport: (id: string, notes?: string) =>
    fetchJson<{ status: string; report_id: string; sha256_hash: string; size_bytes: number }>(`${API_BASE}/incidents/${id}/report`, {
      method: 'POST',
      body: JSON.stringify({ operator_notes: notes }),
    }),
  archiveIncident: (id: string) => fetchJson<{ status: string; incident_id: string }>(`${API_BASE}/incidents/${id}/archive`, { method: 'POST' }),

  // AIS
  getAISStatus: () => fetchJson<any>(`${API_BASE}/ais/status`),
  testAIS: () => fetchJson<{ success: boolean; status: string; message: string }>(`${API_BASE}/ais/test`, { method: 'POST' }),
  listAISVessels: (search?: string, limit = 100) => {
    const q = search ? `?search=${encodeURIComponent(search)}&limit=${limit}` : `?limit=${limit}`;
    return fetchJson<{ total: number; vessels: AISVesselSummary[] }>(`${API_BASE}/ais/vessels${q}`);
  },
  getAISVessel: (mmsi: number) => fetchJson<any>(`${API_BASE}/ais/vessels/${mmsi}`),
  getAISVesselTrack: (mmsi: number) => fetchJson<any>(`${API_BASE}/ais/vessels/${mmsi}/track`),
  refreshAISBuffer: () => fetchJson<{ status: string; buffer_size: number }>(`${API_BASE}/ais/refresh`, { method: 'POST' }),
  updateAISConfig: (cfg: any) => fetchJson(`${API_BASE}/ais/config`, { method: 'POST', body: JSON.stringify(cfg) }),

  // Analysis / Attribution
  getAttributionWorkspace: (incident_id: string) => fetchJson<any>(`${API_BASE}/analysis/incident/${incident_id}`),
  runCounterfactualSimulation: (req: { incident_id: string; mmsi: number; wind_jitter_pct?: number; current_jitter_pct?: number }) =>
    fetchJson<{ status: string; job_id: string }>(`${API_BASE}/analysis/counterfactual`, { method: 'POST', body: JSON.stringify(req) }),

  // Reports
  listReports: () => fetchJson<{ total: number; reports: ReportRecord[] }>(`${API_BASE}/reports`),
  getReport: (id: string) => fetchJson<{ report: ReportRecord; html_content: string }>(`${API_BASE}/reports/${id}`),
  verifyReport: (report_id: string) =>
    fetchJson<{ valid: boolean; report_id: string; expected_hash: string; computed_hash: string; error?: string }>(
      `${API_BASE}/reports/verify`,
      { method: 'POST', body: JSON.stringify({ report_id }) }
    ),
  getReportDownloadUrl: (id: string, format = 'html') => `${API_BASE}/reports/${id}/download?format=${format}`,

  // Settings
  getSettings: () => fetchJson<any>(`${API_BASE}/settings`),
  updateSettings: (cfg: any) => fetchJson<{ status: string; message: string }>(`${API_BASE}/settings`, { method: 'PUT', body: JSON.stringify(cfg) }),

  // Search
  globalSearch: (q: string) => fetchJson<{ query: string; coordinate_match: any; results: { INCIDENTS: any[]; VESSELS: any[]; SATELLITE_PRODUCTS: any[] }; total_matches: number }>(
    `${API_BASE}/search?q=${encodeURIComponent(q)}`
  ),

  // Jobs
  getJob: (id: string) => fetchJson<AsyncJob>(`${API_BASE}/jobs/${id}`),
  listJobs: (limit = 50) => fetchJson<{ total: number; jobs: AsyncJob[] }>(`${API_BASE}/jobs?limit=${limit}`),
};
