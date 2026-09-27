import React, { useState, useEffect } from 'react';
import {
  Settings,
  Save,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Lock,
  Key,
  Shield,
  Layers,
  Clock,
  Radar,
} from 'lucide-react';
import { api } from '../api/client';

export const SettingsPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState<any>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Editable Form Fields
  const [regionName, setRegionName] = useState('');
  const [minLon, setMinLon] = useState(18.1);
  const [minLat, setMinLat] = useState(34.3);
  const [maxLon, setMaxLon] = useState(18.6);
  const [maxLat, setMaxLat] = useState(34.7);
  const [watchInterval, setWatchInterval] = useState(60);
  const [aisMode, setAisMode] = useState('replay');
  const [bufferHours, setBufferHours] = useState(48);
  const [forecastHorizon, setForecastHorizon] = useState(24);
  const [autoProcess, setAutoProcess] = useState(true);

  const loadSettings = async () => {
    setLoading(true);
    try {
      const data = await api.getSettings();
      setSettings(data);
      if (data.surveillance) {
        setRegionName(data.surveillance.region_name || '');
        if (data.surveillance.bbox) {
          setMinLon(data.surveillance.bbox.min_lon ?? 18.1);
          setMinLat(data.surveillance.bbox.min_lat ?? 34.3);
          setMaxLon(data.surveillance.bbox.max_lon ?? 18.6);
          setMaxLat(data.surveillance.bbox.max_lat ?? 34.7);
        }
        setWatchInterval(data.surveillance.polling_interval_minutes ?? 60);
        setAutoProcess(data.surveillance.auto_process_new_scene ?? true);
        setForecastHorizon(data.surveillance.forecast_horizon_hours ?? 24);
      }
      if (data.ais) {
        setAisMode(data.ais.mode || 'replay');
        setBufferHours(data.ais.buffer_hours || 48);
      }
    } catch (err) {
      console.error('Failed to load settings:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSettings();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setNotice(null);
    try {
      const res = await api.updateSettings({
        region_name: regionName,
        min_lon: Number(minLon),
        min_lat: Number(minLat),
        max_lon: Number(maxLon),
        max_lat: Number(maxLat),
        watch_interval_minutes: Number(watchInterval),
        auto_process_new_scene: autoProcess,
        forecast_horizon_hours: Number(forecastHorizon),
        ais_mode: aisMode,
        ais_buffer_hours: Number(bufferHours),
      });
      setNotice(res.message || 'Settings saved successfully.');
      await loadSettings();
    } catch (err: any) {
      alert(`Save failed: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="h-full flex flex-col overflow-hidden bg-m-bg p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-m-border pb-3 shrink-0">
        <div>
          <h1 className="text-lg font-bold text-m-primary flex items-center gap-2">
            <Settings className="w-5 h-5 text-m-blue" />
            Platform Configuration & Security Settings
          </h1>
          <p className="text-xs text-m-muted">
            Surveillance thresholds, provider API configurations, and cryptographic parameter administration.
          </p>
        </div>

        <button
          onClick={loadSettings}
          disabled={loading}
          className="px-3 py-1.5 rounded bg-m-surface hover:bg-m-border border border-m-divider text-xs font-bold text-m-primary flex items-center gap-1.5 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Reload
        </button>
      </div>

      {notice && (
        <div className="px-3 py-2 bg-m-green-light/80 border border-m-green/30 text-m-green rounded text-xs flex items-center justify-between shrink-0">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4" />
            <span>{notice}</span>
          </div>
          <button onClick={() => setNotice(null)} className="text-m-muted hover:text-m-primary">✕</button>
        </div>
      )}

      {/* Main Form */}
      <form onSubmit={handleSave} className="flex-1 overflow-y-auto space-y-4 pr-2">
        {/* Surveillance Parameters Card */}
        <div className="m-card-flat p-4 rounded-lg space-y-3">
          <span className="text-xs font-bold text-m-primary uppercase tracking-wider block border-b border-m-border pb-2">
            Continuous AOI Surveillance Parameters
          </span>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-m-secondary block mb-1">Region Identifier</label>
              <input
                type="text"
                value={regionName}
                onChange={(e) => setRegionName(e.target.value)}
                className="w-full bg-m-bg border border-m-border rounded px-3 py-1.5 text-xs text-m-primary"
              />
            </div>

            <div>
              <label className="text-xs text-m-secondary block mb-1">Polling Interval (Minutes)</label>
              <input
                type="number"
                value={watchInterval}
                onChange={(e) => setWatchInterval(parseInt(e.target.value))}
                className="w-full bg-m-bg border border-m-border rounded px-3 py-1.5 text-xs text-m-primary font-mono"
              />
            </div>

            <div className="col-span-2">
              <label className="text-xs text-m-secondary block mb-1">Surveillance Bounding Box (minLon, minLat, maxLon, maxLat)</label>
              <div className="grid grid-cols-4 gap-2">
                <input
                  type="number"
                  step="0.01"
                  value={minLon}
                  onChange={(e) => setMinLon(parseFloat(e.target.value))}
                  placeholder="Min Lon"
                  className="bg-m-bg border border-m-border rounded px-2 py-1 text-xs text-m-primary font-mono"
                />
                <input
                  type="number"
                  step="0.01"
                  value={minLat}
                  onChange={(e) => setMinLat(parseFloat(e.target.value))}
                  placeholder="Min Lat"
                  className="bg-m-bg border border-m-border rounded px-2 py-1 text-xs text-m-primary font-mono"
                />
                <input
                  type="number"
                  step="0.01"
                  value={maxLon}
                  onChange={(e) => setMaxLon(parseFloat(e.target.value))}
                  placeholder="Max Lon"
                  className="bg-m-bg border border-m-border rounded px-2 py-1 text-xs text-m-primary font-mono"
                />
                <input
                  type="number"
                  step="0.01"
                  value={maxLat}
                  onChange={(e) => setMaxLat(parseFloat(e.target.value))}
                  placeholder="Max Lat"
                  className="bg-m-bg border border-m-border rounded px-2 py-1 text-xs text-m-primary font-mono"
                />
              </div>
            </div>

            <div>
              <label className="text-xs text-m-secondary block mb-1">Forward Drift Forecast Horizon (Hours)</label>
              <input
                type="number"
                value={forecastHorizon}
                onChange={(e) => setForecastHorizon(parseInt(e.target.value))}
                className="w-full bg-m-bg border border-m-border rounded px-3 py-1.5 text-xs text-m-primary font-mono"
              />
            </div>

            <div className="flex items-center pt-5">
              <label className="flex items-center gap-2 cursor-pointer text-xs text-m-secondary">
                <input
                  type="checkbox"
                  checked={autoProcess}
                  onChange={(e) => setAutoProcess(e.target.checked)}
                  className="rounded bg-m-bg border-m-border text-cyan-500"
                />
                Automatically Trigger Investigation Pipeline on Discovered Sentinel-1 Scene
              </label>
            </div>
          </div>
        </div>

        {/* Provider Credential States (Masked Secrets) */}
        <div className="m-card-flat p-4 rounded-lg space-y-3">
          <span className="text-xs font-bold text-m-primary uppercase tracking-wider block border-b border-m-border pb-2 flex items-center justify-between">
            <span>External Provider Authentication State (Strictly Masked)</span>
            <Lock className="w-3.5 h-3.5 text-m-blue" />
          </span>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-3 bg-m-bg border border-m-border rounded space-y-1 text-xs font-mono">
              <div className="flex justify-between items-center">
                <span className="text-m-muted">Copernicus CDSE Sentinel-1 OData:</span>
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                  settings?.satellite?.credentials_state === 'CONFIGURED'
                    ? 'bg-m-green-light text-m-green border border-m-green/30'
                    : 'bg-slate-800 text-m-muted'
                }`}>
                  {settings?.satellite?.credentials_state || 'NOT_CONFIGURED'}
                </span>
              </div>
              <div className="text-[10px] text-m-muted pt-1">
                API Key Env: <code className="text-m-blue">Copernicus OAuth2 Client Credentials</code>
              </div>
              <div className="text-[10px] text-m-muted">
                Secrets are evaluated in secure backend memory and never leaked to frontend bundles.
              </div>
            </div>

            <div className="p-3 bg-m-bg border border-m-border rounded space-y-1 text-xs font-mono">
              <div className="flex justify-between items-center">
                <span className="text-m-muted">AIS Feed Provider:</span>
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                  settings?.ais?.credentials_state === 'CONFIGURED'
                    ? 'bg-m-green-light text-m-green border border-m-green/30'
                    : 'bg-slate-800 text-m-muted'
                }`}>
                  {settings?.ais?.credentials_state || 'NOT_CONFIGURED'}
                </span>
              </div>
              <div className="text-[10px] text-m-muted pt-1">
                Active Ingestion Mode: <strong className="text-m-blue uppercase">{settings?.ais?.mode || 'REPLAY'}</strong>
              </div>
              <div className="text-[10px] text-m-muted">
                Buffer Lookback: {settings?.ais?.buffer_hours || 48} hours sliding window.
              </div>
            </div>
          </div>
        </div>

        {/* AI & Inference Configuration */}
        <div className="m-card-flat p-4 rounded-lg space-y-2 text-xs font-mono">
          <span className="text-xs font-bold text-m-primary uppercase tracking-wider block border-b border-m-border pb-2">
            Scientific Deep Learning & Numerical Drift Engines
          </span>
          <div className="text-m-secondary">
            SAR Segmentation Checkpoint: <code className="text-m-blue">models/sar_unet_baseline_best.pt</code> (7.76M parameters)
          </div>
          <div className="text-m-secondary">
            Lagrangian Drift Tracker: Runge-Kutta 4th Order with Fay radial spreading & Coriolis deflection.
          </div>
        </div>

        <div className="pt-2 flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2 bg-m-blue hover:bg-m-blue/90 text-m-primary rounded text-xs font-bold flex items-center gap-2 transition"
          >
            <Save className="w-4 h-4" /> Save Configuration
          </button>
        </div>
      </form>
    </div>
  );
};
