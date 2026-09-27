import React, { useState, useEffect } from 'react';
import {
  Cpu,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HardDrive,
  Activity,
  Layers,
  FileCode,
  Shield,
  Clock,
  Terminal,
} from 'lucide-react';
import { api } from '../api/client';
import { SystemHealth } from '../types';

export const SystemPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);

  const loadSystemInfo = async () => {
    setLoading(true);
    try {
      const [hRes, aRes] = await Promise.all([
        api.getHealth(),
        api.getAuditLogs(30, 0),
      ]);
      setHealth(hRes);
      setAuditLogs(aRes.entries || []);
    } catch (err) {
      console.error('Failed to load system diagnostics:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSystemInfo();
  }, []);

  const getStatusBadge = (status: string) => {
    if (status === 'READY' || status === 'AVAILABLE' || status === 'CONNECTED') {
      return (
        <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-m-green-light text-m-green border border-m-green/30">
          <CheckCircle2 className="w-3 h-3" /> {status}
        </span>
      );
    }
    if (status === 'DEGRADED' || status === 'LIMITED' || status === 'AUTHENTICATION_FAILED') {
      return (
        <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-m-amber-light text-m-amber border border-m-amber/30">
          <AlertTriangle className="w-3 h-3" /> {status}
        </span>
      );
    }
    return (
      <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-m-red-light text-m-red border border-m-red/30">
        <XCircle className="w-3 h-3" /> {status}
      </span>
    );
  };

  return (
    <div className="h-full flex flex-col overflow-hidden bg-m-bg p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-m-border pb-3 shrink-0">
        <div>
          <h1 className="text-lg font-bold text-m-primary flex items-center gap-2">
            <Cpu className="w-5 h-5 text-m-blue" />
            System Diagnostics, Health Checks & Audit Registry
          </h1>
          <p className="text-xs text-m-muted">
            Real-time infrastructure health, scientific neural network status, provider connectivity, and operator action logs.
          </p>
        </div>

        <button
          onClick={loadSystemInfo}
          disabled={loading}
          className="px-3 py-1.5 rounded bg-m-surface hover:bg-m-border border border-m-divider text-xs font-bold text-m-primary flex items-center gap-1.5 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Run Diagnostics Check
        </button>
      </div>

      {/* Main Health Grids */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3 shrink-0">
        {/* Backend & Storage */}
        <div className="m-card-flat p-4 rounded-lg space-y-2">
          <div className="flex items-center justify-between border-b border-m-border pb-2">
            <span className="text-xs font-bold text-m-primary uppercase flex items-center gap-1.5">
              <HardDrive className="w-4 h-4 text-m-blue" /> Storage & Ledger
            </span>
            {getStatusBadge(health?.storage?.writable ? 'READY' : 'NOT READY')}
          </div>
          <div className="text-xs font-mono space-y-1 text-m-secondary">
            <div className="flex justify-between">
              <span className="text-m-muted">Results Directory:</span>
              <span className="text-m-primary font-bold">{health?.storage?.results_dir}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-m-muted">Storage Writable:</span>
              <span className="text-m-green font-bold">{health?.storage?.writable ? 'YES' : 'NO'}</span>
            </div>
            <div className="text-[10px] text-m-muted truncate pt-1">
              Ledger: {health?.storage?.ledger_path}
            </div>
          </div>
        </div>

        {/* Deep Learning Model */}
        <div className="m-card-flat p-4 rounded-lg space-y-2">
          <div className="flex items-center justify-between border-b border-m-border pb-2">
            <span className="text-xs font-bold text-m-primary uppercase flex items-center gap-1.5">
              <Cpu className="w-4 h-4 text-purple-400" /> Deep Learning U-Net
            </span>
            {getStatusBadge(health?.model?.weights_present ? 'READY' : 'NOT READY')}
          </div>
          <div className="text-xs font-mono space-y-1 text-m-secondary">
            <div className="flex justify-between">
              <span className="text-m-muted">Architecture:</span>
              <span className="text-m-primary font-bold">{health?.model?.name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-m-muted">Model Parameters:</span>
              <span className="text-m-blue font-bold">{health?.model?.parameters}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-m-muted">Inference Device:</span>
              <span className="text-m-green font-bold uppercase">{health?.model?.device}</span>
            </div>
          </div>
        </div>

        {/* Environmental Physics Providers */}
        <div className="m-card-flat p-4 rounded-lg space-y-2">
          <div className="flex items-center justify-between border-b border-m-border pb-2">
            <span className="text-xs font-bold text-m-primary uppercase flex items-center gap-1.5">
              <Activity className="w-4 h-4 text-blue-400" /> Environmental Physics
            </span>
            {getStatusBadge(health?.environment_provider?.status || 'AVAILABLE')}
          </div>
          <div className="text-xs font-mono space-y-1 text-m-secondary">
            <div className="flex justify-between">
              <span className="text-m-muted">ERA5 10m Wind Grid:</span>
              <span className="text-m-green font-bold">{health?.environment_provider?.era5_wind}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-m-muted">OSCAR Currents Grid:</span>
              <span className="text-m-green font-bold">{health?.environment_provider?.oscar_currents}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-m-muted">Lagrangian Formulation:</span>
              <span className="text-m-primary">Runge-Kutta 4th Order</span>
            </div>
          </div>
        </div>
      </div>

      {/* Operator Audit Log Registry */}
      <div className="flex-1 bg-white border border-m-border rounded-lg overflow-hidden flex flex-col">
        <div className="p-3 border-b border-m-border bg-m-bg flex items-center justify-between">
          <span className="text-xs font-bold text-m-primary uppercase tracking-wider flex items-center gap-2">
            <Terminal className="w-4 h-4 text-m-blue" /> Immutable Operator Action Audit Trail
          </span>
          <span className="text-[10px] font-mono text-m-muted">Log File: data/audit/audit_log.jsonl</span>
        </div>

        <div className="overflow-x-auto flex-1">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-m-bg text-m-muted uppercase font-mono text-[10px] tracking-wider sticky top-0">
              <tr>
                <th className="py-2.5 px-4">Timestamp (UTC)</th>
                <th className="py-2.5 px-3">Operator</th>
                <th className="py-2.5 px-3">Action</th>
                <th className="py-2.5 px-3">Target Entity</th>
                <th className="py-2.5 px-3">Execution Status</th>
                <th className="py-2.5 px-4">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-800 font-mono text-xs">
              {auditLogs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-m-muted text-xs">
                    {loading ? 'Reading audit trail...' : 'No actions recorded in audit log yet.'}
                  </td>
                </tr>
              ) : (
                auditLogs.map((log, idx) => (
                  <tr key={idx} className="hover:bg-m-surface/60 transition">
                    <td className="py-2 px-4 text-m-muted text-[11px] whitespace-nowrap">
                      {new Date(log.timestamp).toLocaleString()}
                    </td>
                    <td className="py-2 px-3 text-m-secondary">{log.operator}</td>
                    <td className="py-2 px-3 text-m-blue font-bold">{log.action}</td>
                    <td className="py-2 px-3 text-m-primary truncate max-w-xs">{log.target_id}</td>
                    <td className="py-2 px-3">
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                        log.status === 'SUCCESS' ? 'bg-m-green-light text-m-green' : 'bg-slate-800 text-m-secondary'
                      }`}>
                        {log.status}
                      </span>
                    </td>
                    <td className="py-2 px-4 text-[10px] text-m-muted truncate max-w-sm">
                      {JSON.stringify(log.details)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
