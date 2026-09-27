export type GlobalMode = 'LIVE' | 'REPLAY' | 'BENCHMARK';
export type ProvenanceType = 'REAL' | 'INFERRED' | 'SIMULATED' | 'UNAVAILABLE';
export type HealthStatus = 'READY' | 'DEGRADED' | 'NOT READY';

export interface SystemHealth {
  status: HealthStatus;
  mode: GlobalMode;
  timestamp: string;
  storage: {
    writable: boolean;
    results_dir: string;
    ledger_path: string;
  };
  model: {
    name: string;
    weights_present: boolean;
    weights_path: string;
    parameters: string;
    device: string;
  };
  sentinel1_provider: {
    name: string;
    status: string;
    credentials_configured: boolean;
  };
  ais_provider: {
    name: string;
    mode: string;
    status: string;
    buffer_vessel_count: number;
  };
  environment_provider: {
    era5_wind: string;
    oscar_currents: string;
    status: string;
  };
  workers: {
    watch_active: boolean;
    active_async_jobs: number;
  };
}

export interface WatchStatus {
  mode: GlobalMode;
  watch_active: boolean;
  watch_paused: boolean;
  last_watch_run: string | null;
  last_watch_status: string;
  last_summary?: any;
  satellite_status: string;
  ais_status: string;
  environment_status: string;
  pipeline_status: string;
  ledger_products_tracked: number;
  ais_buffer_count: number;
}

export interface WatchConfig {
  name?: string;
  bbox: {
    min_lon: number;
    min_lat: number;
    max_lon: number;
    max_lat: number;
  };
  polling_interval_minutes?: number;
  satellite_enabled?: boolean;
  ais_enabled?: boolean;
  environmental_enabled?: boolean;
  auto_process?: boolean;
  confidence_threshold?: number;
  forecast_horizon_hours?: number;
}

export interface IncidentSummary {
  incident_id: string;
  status: string;
  created_at: string;
  updated_at: string;
  region_name: string;
  spill_detected: boolean;
  spill_area_km2: number;
  confidence_tier: string;
  model_confidence: number;
  estimated_age_hours: number;
  candidate_count: number;
  top_candidate_mmsi?: number;
  top_candidate_name?: string;
  top_composite_score?: number;
  attribution_decision?: string;
  reality_labels: Record<string, string>;
  has_geojson: boolean;
  provenance_category?: string;
}

export interface SatelliteProduct {
  product_id: string;
  product_name: string;
  provenance?: string;
  acquisition_start: string;
  acquisition_end: string;
  first_seen: string;
  processing_status: string;
  incident_id?: string;
  source_provider: string;
  spatial_bbox?: [number, number, number, number];
  product_hash?: string;
  details?: string;
  updated_at?: string;
}

export interface AISObservation {
  mmsi: number;
  timestamp: string;
  latitude: number;
  longitude: number;
  speed_over_ground?: number;
  course_over_ground?: number;
  heading?: number;
  nav_status?: string;
  vessel_name?: string;
  callsign?: string;
  imo?: number;
  vessel_type?: string;
  source_provider?: string;
}

export interface AISVesselSummary {
  mmsi: number;
  vessel_name: string;
  imo?: number;
  vessel_type?: string;
  latitude: number;
  longitude: number;
  speed_over_ground: number;
  course_over_ground: number;
  timestamp: string;
  observations_count: number;
  anomalies_count: number;
  gaps_count: number;
  integrity_state: string;
  source: string;
}

export interface ReportRecord {
  report_id: string;
  incident_id: string;
  created_at: string;
  generated_by: string;
  sha256_hash: string;
  html_path: string;
  json_path: string;
  file_size_bytes: number;
  top_suspect_mmsi?: string;
  top_suspect_name?: string;
  composite_score?: number;
  attribution_decision?: string;
}

export interface AlertNotification {
  id: string;
  timestamp: string;
  severity: 'INFO' | 'WARNING' | 'CRITICAL';
  title: string;
  message: string;
  related_link?: string;
  data?: any;
  read: boolean;
}

export interface AsyncJob {
  job_id: string;
  job_type: string;
  target_id: string;
  status: 'QUEUED' | 'RUNNING' | 'COMPLETE' | 'FAILED';
  progress: number;
  progress_message: string;
  result?: any;
  error?: string;
  created_at: string;
  started_at?: string;
  completed_at?: string;
}
