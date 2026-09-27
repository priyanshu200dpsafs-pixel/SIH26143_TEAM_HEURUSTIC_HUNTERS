import React, { useState, useEffect } from 'react';
import {
  Radar,
  Play,
  Square,
  Pause,
  RotateCw,
  RefreshCw,
  Save,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Satellite,
  Ship,
  Wind,
  Layers,
  Activity,
  Trash2,
} from 'lucide-react';
import { api } from '../api/client';
import { MapLibreView } from '../components/MapLibreView';
import { ProvenanceBadge } from '../components/ProvenanceBadge';
import { WatchStatus, WatchConfig } from '../types';

export const WatchPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [actionLoading, setActionLoading] = useState(false);
  const [watchData, setWatchData] = useState<{ status: WatchStatus; config: any; ledger: any } | null>(null);

  // Form State
  const [regionName, setRegionName] = useState('Central Mediterranean Approaches');
  const [minLon, setMinLon] = useState(18.1);
  const [minLat, setMinLat] = useState(34.3);
  const [maxLon, setMaxLon] = useState(18.6);
  const [maxLat, setMaxLat] = useState(34.7);
  const [pollingMinutes, setPollingMinutes] = useState(60);
  const [satEnabled, setSatEnabled] = useState(true);
  const [aisEnabled, setAisEnabled] = useState(true);
  const [envEnabled, setEnvEnabled] = useState(true);
  const [autoProcess, setAutoProcess] = useState(true);
  const [confidenceThreshold, setConfidenceThreshold] = useState(0.5);
  const [forecastHorizon, setForecastHorizon] = useState(24);

  const [notification, setNotification] = useState<string | null>(null);

  const loadWatchData = async () => {
    try {
      const res = await api.getWatch();
      setWatchData(res);
      if (res.config?.region) {
        setRegionName(res.config.region.name || 'Central Mediterranean Approaches');
        if (res.config.region.bbox) {
          setMinLon(res.config.region.bbox.min_lon ?? 18.1);
          setMinLat(res.config.region.bbox.min_lat ?? 34.3);
          setMaxLon(res.config.region.bbox.max_lon ?? 18.6);
          setMaxLat(res.config.region.bbox.max_lat ?? 34.7);
        }
      }
      if (res.config?.watch?.polling_interval_minutes) {
        setPollingMinutes(res.config.watch.polling_interval_minutes);
      }
      if (res.config?.satellite?.sentinel1) {
        setSatEnabled(res.config.satellite.sentinel1.enabled ?? true);
      }
    } catch (err: any) {
      console.error('Failed to load watch data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadWatchData();
    const interval = setInterval(loadWatchData, 8000);
    return () => clearInterval(interval);
  }, []);

  const handleStart = async () => {
    setActionLoading(true);
    try {
      const res = await api.startWatch();
      setNotification(`Watch Started: ${res.message}`);
      await loadWatchData();
    } catch (err: any) {
      alert(`Start failed: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleStop = async () => {
    setActionLoading(true);
    try {
      const res = await api.stopWatch();
      setNotification(`Watch Stopped: ${res.message}`);
      await loadWatchData();
    } catch (err: any) {
      alert(`Stop failed: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handlePause = async () => {
    setActionLoading(true);
    try {
      await api.pauseWatch();
      setNotification('Watch Polling Paused');
      await loadWatchData();
    } catch (err: any) {
      alert(`Pause failed: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleResume = async () => {
    setActionLoading(true);
    try {
      await api.resumeWatch();
      setNotification('Watch Polling Resumed');
      await loadWatchData();
    } catch (err: any) {
      alert(`Resume failed: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRunOnce = async () => {
    setActionLoading(true);
    try {
      const res = await api.runWatchOnce();
      setNotification(`Cycle Executed: ${res.status || 'SUCCESS'}`);
      await loadWatchData();
    } catch (err: any) {
      alert(`Cycle execution failed: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const handleSaveConfig = async () => {
    setActionLoading(true);
    try {
      const cfg: WatchConfig = {
        name: regionName,
        bbox: {
          min_lon: Number(minLon),
          min_lat: Number(minLat),
          max_lon: Number(maxLon),
          max_lat: Number(maxLat),
        },
        polling_interval_minutes: Number(pollingMinutes),
        satellite_enabled: satEnabled,
        ais_enabled: aisEnabled,
        environmental_enabled: envEnabled,
        auto_process: autoProcess,
        confidence_threshold: Number(confidenceThreshold),
        forecast_horizon_hours: Number(forecastHorizon),
      };
      await api.updateWatch(cfg);
      setNotification('Watch configuration updated and persisted.');
      await loadWatchData();
    } catch (err: any) {
      alert(`Save failed: ${err.message}`);
    } finally {
      setActionLoading(false);
    }
  };

  const currentBbox: [number, number, number, number] = [minLon, minLat, maxLon, maxLat];
  const st = watchData?.status;

  return (
    <div className="h-full flex flex-col overflow-hidden bg-m-bg p-4 space-y-4">
      {/* Page Header */}
      <div className="flex items-center justify-between border-b border-m-border pb-3 shrink-0">
        <div>
          <h1 className="text-lg font-bold text-m-primary flex items-center gap-2">
            <Radar className="w-5 h-5 text-m-blue" />
            Continuous Maritime Surveillance Watch Service
          </h1>
          <p className="text-xs text-m-muted">
            Autonomous surveillance loop discovering Sentinel-1 acquisitions and correlating live AIS.
          </p>
        </div>

        {/* Global Watch Controls */}
        <div className="flex items-center gap-2">
          {st?.watch_active ? (
            <>
              {st.watch_paused ? (
                <button
                  onClick={handleResume}
                  disabled={actionLoading}
                  className="px-3 py-1.5 rounded bg-emerald-600 hover:bg-emerald-500 text-m-primary text-xs font-bold flex items-center gap-1.5 transition"
                >
                  <Play className="w-3.5 h-3.5" /> Resume Watch
                </button>
              ) : (
                <button
                  onClick={handlePause}
                  disabled={actionLoading}
                  className="px-3 py-1.5 rounded bg-amber-600 hover:bg-amber-500 text-m-primary text-xs font-bold flex items-center gap-1.5 transition"
                >
                  <Pause className="w-3.5 h-3.5" /> Pause Watch
                </button>
              )}
              <button
                onClick={handleStop}
                disabled={actionLoading}
                className="px-3 py-1.5 rounded bg-rose-600 hover:bg-m-red text-m-primary text-xs font-bold flex items-center gap-1.5 transition"
              >
                <Square className="w-3.5 h-3.5" /> Stop Watch
              </button>
            </>
          ) : (
            <button
              onClick={handleStart}
              disabled={actionLoading}
              className="px-4 py-1.5 rounded bg-m-blue hover:bg-m-blue/90 text-m-primary text-xs font-bold flex items-center gap-1.5 transition shadow-lg shadow-cyan-600/20"
            >
              <Play className="w-3.5 h-3.5" /> Start Watch Service
            </button>
          )}

          <button
            onClick={handleRunOnce}
            disabled={actionLoading}
            className="px-3 py-1.5 rounded bg-m-surface hover:bg-m-border text-m-blue border border-m-divider text-xs font-bold flex items-center gap-1.5 transition"
            title="Execute immediate single surveillance cycle"
          >
            <RotateCw className="w-3.5 h-3.5" /> Run Once
          </button>

          <button
            onClick={loadWatchData}
            disabled={actionLoading}
            className="p-1.5 rounded bg-m-surface hover:bg-m-border text-m-secondary transition"
            title="Refresh Status"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {notification && (
        <div className="px-3 py-2 bg-m-blue-light/80 border border-m-blue/30 text-m-blue rounded text-xs flex items-center justify-between">
          <span>{notification}</span>
          <button onClick={() => setNotification(null)} className="text-m-muted hover:text-m-primary text-xs">
            ✕
          </button>
        </div>
      )}

      {/* 4 Multi-Domain Status Indicators */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 shrink-0">
        {/* Satellite Status */}
        <div className="m-card-flat p-3 rounded-md">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-mono text-m-muted uppercase flex items-center gap-1.5">
              <Satellite className="w-3.5 h-3.5 text-m-blue" /> Satellite Catalog
            </span>
            <ProvenanceBadge type="REAL" />
          </div>
          <div className="text-sm font-bold text-m-primary">
            {st?.satellite_status || 'UNKNOWN'}
          </div>
          <div className="text-[11px] text-m-muted mt-1">
            Tracked in Ledger: <span className="text-m-blue font-mono">{st?.ledger_products_tracked ?? 0} scenes</span>
          </div>
        </div>

        {/* AIS Status */}
        <div className="m-card-flat p-3 rounded-md">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-mono text-m-muted uppercase flex items-center gap-1.5">
              <Ship className="w-3.5 h-3.5 text-m-blue" /> AIS Provider
            </span>
            <ProvenanceBadge type={st?.mode === 'LIVE' ? 'REAL' : 'SIMULATED'} />
          </div>
          <div className="text-sm font-bold text-m-primary">
            {st?.ais_status || 'NOT CONNECTED'}
          </div>
          <div className="text-[11px] text-m-muted mt-1">
            Buffer: <span className="text-m-blue font-mono">{st?.ais_buffer_count ?? 0} observations</span>
          </div>
        </div>

        {/* Environment Status */}
        <div className="m-card-flat p-3 rounded-md">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-mono text-m-muted uppercase flex items-center gap-1.5">
              <Wind className="w-3.5 h-3.5 text-m-green" /> Environment Physics
            </span>
            <ProvenanceBadge type="REAL" />
          </div>
          <div className="text-sm font-bold text-m-primary">
            {st?.environment_status || 'AVAILABLE'}
          </div>
          <div className="text-[11px] text-m-muted mt-1">ERA5 10m Wind + OSCAR Currents</div>
        </div>

        {/* Pipeline Status */}
        <div className="m-card-flat p-3 rounded-md">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[11px] font-mono text-m-muted uppercase flex items-center gap-1.5">
              <Activity className="w-3.5 h-3.5 text-purple-400" /> Pipeline Engine
            </span>
            <ProvenanceBadge type="REAL" />
          </div>
          <div className="text-sm font-bold text-m-primary">
            {st?.watch_active ? (st.watch_paused ? 'PAUSED' : 'PROCESSING LOOP') : 'READY (STANDBY)'}
          </div>
          <div className="text-[11px] text-m-muted mt-1">
            Last run: {st?.last_watch_run ? new Date(st.last_watch_run).toLocaleTimeString() : 'N/A'}
          </div>
        </div>
      </div>

      {/* Main Watch Console: Left Config & Right Interactive Map */}
      <div className="flex-1 flex gap-4 overflow-hidden">
        {/* Left AOI & Polling Form */}
        <div className="w-96 bg-white border border-m-border rounded-lg p-4 flex flex-col justify-between overflow-y-auto shrink-0">
          <div className="space-y-4">
            <div className="border-b border-m-border pb-2">
              <span className="text-xs font-bold text-m-primary uppercase tracking-wider">Surveillance Area (AOI)</span>
            </div>

            <div>
              <label className="text-xs text-m-secondary block mb-1">Surveillance Region Name</label>
              <input
                type="text"
                value={regionName}
                onChange={(e) => setRegionName(e.target.value)}
                className="w-full bg-m-bg border border-m-border rounded px-2.5 py-1.5 text-xs text-m-primary"
              />
            </div>

            {/* Bounding Box Coordinates */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs text-m-secondary">Bounding Box (WGS84)</label>
                <span className="text-[10px] font-mono text-m-blue">minLon, minLat, maxLon, maxLat</span>
              </div>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <span className="text-[10px] text-m-muted">Min Lon</span>
                  <input
                    type="number"
                    step="0.01"
                    value={minLon}
                    onChange={(e) => setMinLon(parseFloat(e.target.value))}
                    className="w-full bg-m-bg border border-m-border rounded px-2 py-1 text-m-primary font-mono text-xs"
                  />
                </div>
                <div>
                  <span className="text-[10px] text-m-muted">Min Lat</span>
                  <input
                    type="number"
                    step="0.01"
                    value={minLat}
                    onChange={(e) => setMinLat(parseFloat(e.target.value))}
                    className="w-full bg-m-bg border border-m-border rounded px-2 py-1 text-m-primary font-mono text-xs"
                  />
                </div>
                <div>
                  <span className="text-[10px] text-m-muted">Max Lon</span>
                  <input
                    type="number"
                    step="0.01"
                    value={maxLon}
                    onChange={(e) => setMaxLon(parseFloat(e.target.value))}
                    className="w-full bg-m-bg border border-m-border rounded px-2 py-1 text-m-primary font-mono text-xs"
                  />
                </div>
                <div>
                  <span className="text-[10px] text-m-muted">Max Lat</span>
                  <input
                    type="number"
                    step="0.01"
                    value={maxLat}
                    onChange={(e) => setMaxLat(parseFloat(e.target.value))}
                    className="w-full bg-m-bg border border-m-border rounded px-2 py-1 text-m-primary font-mono text-xs"
                  />
                </div>
              </div>
            </div>

            {/* Polling & Thresholds */}
            <div className="space-y-3 pt-2 border-t border-m-border">
              <div>
                <label className="text-xs text-m-secondary flex justify-between">
                  <span>Polling Interval</span>
                  <span className="text-m-blue font-mono font-bold">{pollingMinutes} minutes</span>
                </label>
                <input
                  type="range"
                  min="5"
                  max="180"
                  step="5"
                  value={pollingMinutes}
                  onChange={(e) => setPollingMinutes(parseInt(e.target.value))}
                  className="w-full accent-cyan-400 h-1 bg-m-bg rounded mt-1"
                />
              </div>

              <div>
                <label className="text-xs text-m-secondary flex justify-between">
                  <span>Detection Confidence Threshold</span>
                  <span className="text-m-blue font-mono font-bold">{Math.round(confidenceThreshold * 100)}%</span>
                </label>
                <input
                  type="range"
                  min="0.1"
                  max="0.9"
                  step="0.05"
                  value={confidenceThreshold}
                  onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
                  className="w-full accent-cyan-400 h-1 bg-m-bg rounded mt-1"
                />
              </div>

              <div>
                <label className="text-xs text-m-secondary flex justify-between">
                  <span>Forecast Horizon</span>
                  <span className="text-m-blue font-mono font-bold">{forecastHorizon} hours</span>
                </label>
                <input
                  type="range"
                  min="6"
                  max="72"
                  step="6"
                  value={forecastHorizon}
                  onChange={(e) => setForecastHorizon(parseInt(e.target.value))}
                  className="w-full accent-cyan-400 h-1 bg-m-bg rounded mt-1"
                />
              </div>
            </div>

            {/* Checkbox Toggles */}
            <div className="space-y-2 pt-2 border-t border-m-border text-xs">
              <label className="flex items-center gap-2 cursor-pointer text-m-secondary">
                <input
                  type="checkbox"
                  checked={satEnabled}
                  onChange={(e) => setSatEnabled(e.target.checked)}
                  className="rounded bg-m-bg border-m-border text-cyan-500"
                />
                Sentinel-1 SAR Ingestion Active
              </label>

              <label className="flex items-center gap-2 cursor-pointer text-m-secondary">
                <input
                  type="checkbox"
                  checked={aisEnabled}
                  onChange={(e) => setAisEnabled(e.target.checked)}
                  className="rounded bg-m-bg border-m-border text-cyan-500"
                />
                AIS Vessel Correlation Active
              </label>

              <label className="flex items-center gap-2 cursor-pointer text-m-secondary">
                <input
                  type="checkbox"
                  checked={autoProcess}
                  onChange={(e) => setAutoProcess(e.target.checked)}
                  className="rounded bg-m-bg border-m-border text-cyan-500"
                />
                Automated Incident Pipeline Trigger on New Scene
              </label>
            </div>
          </div>

          <div className="pt-4 border-t border-m-border">
            <button
              onClick={handleSaveConfig}
              disabled={actionLoading}
              className="w-full py-2 bg-m-surface hover:bg-m-border text-m-blue border border-m-blue/30/80 rounded text-xs font-bold flex items-center justify-center gap-2 transition"
            >
              <Save className="w-3.5 h-3.5" /> Save Watch Configuration
            </button>
          </div>
        </div>

        {/* Right AOI Interactive Map Preview */}
        <div className="flex-1 bg-white border border-m-border rounded-lg overflow-hidden flex flex-col relative">
          <div className="px-3 py-2 border-b border-m-border bg-m-bg/80 flex items-center justify-between text-xs">
            <span className="font-bold text-m-primary uppercase tracking-wider">AOI Geographic Bounds</span>
            <div className="flex items-center gap-2">
              <span className="font-mono text-m-blue text-[10px]">
                {minLat}°N, {minLon}°E to {maxLat}°N, {maxLon}°E
              </span>
            </div>
          </div>

          <div className="flex-1 relative">
            <MapLibreView
              aoiBbox={currentBbox}
              initialCenter={[(minLon + maxLon) / 2, (minLat + maxLat) / 2]}
              initialZoom={8}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
