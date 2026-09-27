import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { Sidebar, RouteId } from './components/Sidebar';
import { GlobalSearchModal } from './components/GlobalSearchModal';
import { AlertCenterModal } from './components/AlertCenterModal';
import { OperationsPage } from './pages/OperationsPage';
import { WatchPage } from './pages/WatchPage';
import { IncidentsPage } from './pages/IncidentsPage';
import { IncidentDetailPage } from './pages/IncidentDetailPage';
import { SatellitePage } from './pages/SatellitePage';
import { AISPage } from './pages/AISPage';
import { AttributionPage } from './pages/AttributionPage';
import { ReportsPage } from './pages/ReportsPage';
import { SettingsPage } from './pages/SettingsPage';
import { SystemPage } from './pages/SystemPage';
import { GlobalMode, HealthStatus, AlertNotification } from './types';
import { api } from './api/client';

export const App: React.FC = () => {
  const [currentRoute, setCurrentRoute] = useState<RouteId>('operations');
  const [targetIncidentId, setTargetIncidentId] = useState<string | null>(null);
  const [targetProductId, setTargetProductId] = useState<string | null>(null);
  const [targetMmsi, setTargetMmsi] = useState<string | null>(null);
  const [targetReportId, setTargetReportId] = useState<string | null>(null);

  const [currentMode, setCurrentMode] = useState<GlobalMode>('REPLAY');
  const [healthStatus, setHealthStatus] = useState<HealthStatus>('READY');
  const [wsConnected, setWsConnected] = useState(false);
  const [alerts, setAlerts] = useState<AlertNotification[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);

  // Sync health & alerts
  const syncHealthAndAlerts = async () => {
    try {
      const [hRes, aRes] = await Promise.all([api.getHealth(), api.getAlerts()]);
      setHealthStatus(hRes.status);
      setCurrentMode(hRes.mode);
      setAlerts(aRes.alerts || []);
    } catch {
      setHealthStatus('DEGRADED');
    }
  };

  useEffect(() => {
    syncHealthAndAlerts();
    const interval = setInterval(syncHealthAndAlerts, 10000);
    return () => clearInterval(interval);
  }, []);

  // Parse direct URL path on initial load
  useEffect(() => {
    const path = window.location.pathname.replace(/^\//, '');
    const parts = path.split('/');
    if (parts[0] === 'incidents' && parts[1]) {
      const cleanId = parts[1].replace(/[^a-zA-Z0-9_-]/g, '');
      setTargetIncidentId(cleanId);
      setCurrentRoute('incidents');
    } else if (parts[0]) {
      const cleanRoute = parts[0] as RouteId;
      if (['operations', 'watch', 'incidents', 'satellite', 'ais', 'attribution', 'reports', 'settings', 'system'].includes(cleanRoute)) {
        setCurrentRoute(cleanRoute);
      }
    }
  }, []);

  // WebSocket Live Connection
  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    let ws: WebSocket | null = null;

    try {
      ws = new WebSocket(wsUrl);
      ws.onopen = () => setWsConnected(true);
      ws.onclose = () => setWsConnected(false);
      ws.onerror = () => setWsConnected(false);
      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'ALERT') {
            setAlerts((prev) => [msg.alert, ...prev]);
          } else if (msg.type === 'MODE_CHANGED') {
            setCurrentMode(msg.mode);
          }
        } catch {
          // ignore
        }
      };
    } catch {
      setWsConnected(false);
    }

    return () => {
      ws?.close();
    };
  }, []);

  // Global Keyboard Shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setSearchOpen((prev) => !prev);
      }
      if (e.key === 'Escape') {
        setSearchOpen(false);
        setAlertsOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Generic navigation handler
  const handleNavigate = (route: string, id?: string) => {
    const clean = route.replace(/^\//, '') as RouteId;
    if (clean === 'incidents' && id) {
      setTargetIncidentId(id);
      setCurrentRoute('incidents');
    } else if (clean === 'satellite' && id) {
      setTargetProductId(id);
      setCurrentRoute('satellite');
    } else if (clean === 'ais' && id) {
      setTargetMmsi(id);
      setCurrentRoute('ais');
    } else if (clean === 'reports' && id) {
      setTargetReportId(id);
      setCurrentRoute('reports');
    } else {
      setTargetIncidentId(null);
      setTargetProductId(null);
      setTargetMmsi(null);
      setTargetReportId(null);
      setCurrentRoute(clean);
    }
  };

  const unreadAlerts = alerts.filter((a) => !a.read).length;

  return (
    <div className="h-screen w-screen flex flex-col bg-m-bg text-m-primary overflow-hidden font-sans">
      {/* Top Application Bar */}
      <Navbar
        currentMode={currentMode}
        onModeChange={setCurrentMode}
        healthStatus={healthStatus}
        wsConnected={wsConnected}
        unreadAlertCount={unreadAlerts}
        onOpenSearch={() => setSearchOpen(true)}
        onOpenAlerts={() => setAlertsOpen(true)}
      />

      {/* Main Workspace Body */}
      <div className="flex-1 flex overflow-hidden">
        {/* Persistent Left Navigation Sidebar */}
        <Sidebar
          currentRoute={currentRoute}
          onNavigate={(r) => handleNavigate(r)}
        />

        {/* Center Main Stage Content */}
        <main className="flex-1 overflow-hidden relative">
          {currentRoute === 'operations' && <OperationsPage onNavigate={handleNavigate} />}
          {currentRoute === 'watch' && <WatchPage />}
          {currentRoute === 'incidents' && (
            targetIncidentId ? (
              <IncidentDetailPage
                incidentId={targetIncidentId}
                onBack={() => setTargetIncidentId(null)}
                onNavigate={handleNavigate}
              />
            ) : (
              <IncidentsPage onNavigate={handleNavigate} />
            )
          )}
          {currentRoute === 'satellite' && (
            <SatellitePage onNavigate={handleNavigate} initialProductId={targetProductId || undefined} />
          )}
          {currentRoute === 'ais' && <AISPage onNavigate={handleNavigate} initialMmsi={targetMmsi || undefined} />}
          {currentRoute === 'analysis' && <AttributionPage onNavigate={handleNavigate} />}
          {currentRoute === 'reports' && (
            <ReportsPage onNavigate={handleNavigate} initialReportId={targetReportId || undefined} />
          )}
          {currentRoute === 'settings' && <SettingsPage />}
          {currentRoute === 'system' && <SystemPage />}
        </main>
      </div>

      {/* Global Command Center Search Modal */}
      <GlobalSearchModal
        isOpen={searchOpen}
        onClose={() => setSearchOpen(false)}
        onNavigate={handleNavigate}
      />

      {/* Alert Center Flyout Modal */}
      <AlertCenterModal
        isOpen={alertsOpen}
        onClose={() => setAlertsOpen(false)}
        alerts={alerts}
        onRefreshAlerts={syncHealthAndAlerts}
        onNavigate={handleNavigate}
      />
    </div>
  );
};
