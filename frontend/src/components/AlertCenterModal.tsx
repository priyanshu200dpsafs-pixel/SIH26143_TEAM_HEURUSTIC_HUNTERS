import React from 'react';
import { Bell, X, Check, Trash2, AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { AlertNotification } from '../types';
import { api } from '../api/client';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  alerts: AlertNotification[];
  onRefreshAlerts: () => void;
  onNavigate: (route: string) => void;
}

export const AlertCenterModal: React.FC<Props> = ({
  isOpen,
  onClose,
  alerts,
  onRefreshAlerts,
  onNavigate,
}) => {
  if (!isOpen) return null;

  const handleMarkRead = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await api.markAlertRead(id);
      onRefreshAlerts();
    } catch {
      // ignore
    }
  };

  const handleClearAll = async () => {
    try {
      await api.clearAlerts();
      onRefreshAlerts();
    } catch {
      // ignore
    }
  };

  const getSeverityBadge = (sev: string) => {
    if (sev === 'CRITICAL') {
      return (
        <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-m-red-light text-m-red border border-m-red/30">
          <AlertCircle className="w-3 h-3" /> CRITICAL
        </span>
      );
    }
    if (sev === 'WARNING') {
      return (
        <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-m-amber-light text-m-amber border border-m-amber/30">
          <AlertTriangle className="w-3 h-3" /> WARNING
        </span>
      );
    }
    return (
      <span className="flex items-center gap-1 text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-m-blue-light text-m-blue border border-sky-800">
        <Info className="w-3 h-3" /> INFO
      </span>
    );
  };

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-end p-4 pt-16 bg-black/25 backdrop-blur-xs">
      <div className="w-full max-w-md bg-white border border-m-border rounded-lg shadow-popup overflow-hidden flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-m-border bg-m-bg">
          <div className="flex items-center gap-2">
            <Bell className="w-4 h-4 text-m-blue" />
            <span className="text-xs font-bold text-m-primary uppercase tracking-wider">Operational Alert Feed</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={handleClearAll}
              title="Clear read alerts"
              className="p-1 rounded text-m-muted hover:text-m-red transition"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
            <button onClick={onClose} className="p-1 rounded text-m-muted hover:text-m-primary transition">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* List */}
        <div className="overflow-y-auto p-3 space-y-2">
          {alerts.length === 0 ? (
            <div className="text-center py-8 text-m-muted text-xs">
              No alerts or active warning notices.
            </div>
          ) : (
            alerts.map((alert) => (
              <div
                key={alert.id}
                onClick={() => {
                  if (alert.related_link) {
                    const cleanRoute = alert.related_link.replace(/^\//, '');
                    onNavigate(cleanRoute);
                    onClose();
                  }
                }}
                className={`p-3 rounded border text-left transition cursor-pointer ${
                  alert.read
                    ? 'bg-m-bg/60 border-m-border text-m-muted'
                    : 'bg-m-bg border-m-border text-m-primary shadow-sm'
                }`}
              >
                <div className="flex items-center justify-between mb-1.5">
                  <div className="flex items-center gap-2">
                    {getSeverityBadge(alert.severity)}
                    <span className="text-xs font-bold">{alert.title}</span>
                  </div>
                  {!alert.read && (
                    <button
                      onClick={(e) => handleMarkRead(alert.id, e)}
                      className="text-m-muted hover:text-m-green text-xs p-1"
                      title="Mark as read"
                    >
                      <Check className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
                <p className="text-xs text-m-secondary mb-2 leading-relaxed">{alert.message}</p>
                <div className="flex items-center justify-between text-[10px] font-mono text-m-muted">
                  <span>{new Date(alert.timestamp).toLocaleTimeString()} UTC</span>
                  {alert.related_link && (
                    <span className="text-m-blue hover:underline">View Object →</span>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};
