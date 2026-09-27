import React, { useState, useEffect } from 'react';
import {
  Anchor,
  Search,
  Bell,
  Clock,
  Radio,
  CheckCircle2,
  AlertTriangle,
  XCircle,
} from 'lucide-react';
import { GlobalMode, HealthStatus } from '../types';
import { api } from '../api/client';

interface Props {
  currentMode: GlobalMode;
  onModeChange: (mode: GlobalMode) => void;
  healthStatus: HealthStatus;
  wsConnected: boolean;
  unreadAlertCount: number;
  onOpenSearch: () => void;
  onOpenAlerts: () => void;
}

export const Navbar: React.FC<Props> = ({
  currentMode,
  onModeChange,
  healthStatus,
  wsConnected,
  unreadAlertCount,
  onOpenSearch,
  onOpenAlerts,
}) => {
  const [utcTime, setUtcTime] = useState<string>('');

  useEffect(() => {
    const tick = () => {
      const now = new Date();
      setUtcTime(now.toISOString().replace('T', ' ').substring(0, 19) + ' UTC');
    };
    tick();
    const timer = setInterval(tick, 1000);
    return () => clearInterval(timer);
  }, []);

  const handleModeSwitch = async (mode: GlobalMode) => {
    try {
      await api.setMode(mode);
      onModeChange(mode);
    } catch (err: any) {
      alert(`Mode switch failed: ${err.message}`);
    }
  };

  const getHealthBadge = () => {
    if (healthStatus === 'READY') {
      return (
        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-m-green-light text-m-green text-xs font-semibold">
          <CheckCircle2 className="w-3.5 h-3.5" />
          <span className="hidden xl:inline">SYSTEM READY</span>
        </span>
      );
    }
    if (healthStatus === 'DEGRADED') {
      return (
        <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-m-amber-light text-m-amber text-xs font-semibold">
          <AlertTriangle className="w-3.5 h-3.5" />
          <span className="hidden xl:inline">DEGRADED</span>
        </span>
      );
    }
    return (
      <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-m-red-light text-m-red text-xs font-semibold">
        <XCircle className="w-3.5 h-3.5" />
        <span className="hidden xl:inline">NOT READY</span>
      </span>
    );
  };

  return (
    <header className="h-12 border-b border-m-border bg-white px-4 flex items-center justify-between z-30 select-none shadow-panel">
      {/* Brand Identity */}
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-m-blue flex items-center justify-center text-white">
          <Anchor className="w-4.5 h-4.5" />
        </div>
        <div>
          <div className="flex items-center gap-2">
            <span className="font-extrabold tracking-wide text-sm text-m-primary">AEGIS-SAR</span>
            <span className="text-[10px] uppercase font-semibold px-1.5 py-0.5 rounded bg-m-blue-light text-m-blue">
              OPS v2.0
            </span>
          </div>
          <p className="text-[10px] text-m-muted tracking-tight hidden md:block">
            Maritime Spill Intelligence & Vessel Attribution
          </p>
        </div>
      </div>

      {/* Global Mode Switcher */}
      <div className="flex items-center bg-m-surface p-0.5 rounded-lg border border-m-border">
        {(['LIVE', 'REPLAY', 'BENCHMARK'] as GlobalMode[]).map((mode) => {
          const isActive = currentMode === mode;
          let activeClass = '';
          if (isActive) {
            if (mode === 'LIVE') activeClass = 'bg-m-red text-white shadow-sm';
            else if (mode === 'REPLAY') activeClass = 'bg-m-blue text-white shadow-sm';
            else activeClass = 'bg-m-amber text-white shadow-sm';
          }
          return (
            <button
              key={mode}
              onClick={() => handleModeSwitch(mode)}
              className={`px-3 py-1 rounded-md text-xs font-bold transition-all ${
                isActive ? activeClass : 'text-m-secondary hover:text-m-primary hover:bg-m-border/50'
              }`}
            >
              {mode}
            </button>
          );
        })}
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-2.5">
        {/* UTC Clock */}
        <div className="hidden lg:flex items-center gap-1.5 text-[11px] font-mono text-m-secondary bg-m-surface px-2.5 py-1 rounded-md border border-m-border">
          <Clock className="w-3.5 h-3.5 text-m-blue" />
          <span>{utcTime || 'UTC CLOCK'}</span>
        </div>

        {/* WebSocket Indicator */}
        <div
          title={wsConnected ? 'Real-time stream active' : 'Stream disconnected'}
          className={`flex items-center gap-1.5 px-2 py-1 rounded-md text-xs font-semibold border ${
            wsConnected
              ? 'bg-m-green-light text-m-green border-transparent'
              : 'bg-m-red-light text-m-red border-transparent'
          }`}
        >
          <Radio className={`w-3 h-3 ${wsConnected ? 'animate-pulse-subtle' : ''}`} />
          <span className="hidden xl:inline">{wsConnected ? 'LIVE' : 'OFFLINE'}</span>
        </div>

        {/* Health */}
        {getHealthBadge()}

        {/* Search */}
        <button
          onClick={onOpenSearch}
          className="flex items-center gap-2 px-3 py-1.5 bg-m-surface hover:bg-m-border/40 border border-m-border rounded-lg text-xs text-m-secondary transition"
          title="Command Search (Ctrl+K)"
        >
          <Search className="w-3.5 h-3.5 text-m-muted" />
          <span className="hidden sm:inline">Search…</span>
          <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-[10px] bg-white border border-m-border rounded text-m-muted font-mono">
            ⌘K
          </kbd>
        </button>

        {/* Alert Bell */}
        <button
          onClick={onOpenAlerts}
          className="relative p-1.5 rounded-lg bg-m-surface hover:bg-m-border/40 border border-m-border text-m-secondary transition"
          title="Alert Center"
        >
          <Bell className="w-4 h-4" />
          {unreadAlertCount > 0 && (
            <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-m-red text-white text-[10px] font-bold flex items-center justify-center">
              {unreadAlertCount}
            </span>
          )}
        </button>
      </div>
    </header>
  );
};
