import React from 'react';
import {
  Compass,
  Radar,
  AlertOctagon,
  Satellite,
  Ship,
  Scale,
  FileText,
  Settings,
  Cpu,
} from 'lucide-react';

export type RouteId =
  | 'operations'
  | 'watch'
  | 'incidents'
  | 'satellite'
  | 'ais'
  | 'analysis'
  | 'reports'
  | 'settings'
  | 'system';

interface Props {
  currentRoute: RouteId;
  onNavigate: (route: RouteId) => void;
  incidentCount?: number;
}

export const Sidebar: React.FC<Props> = ({ currentRoute, onNavigate, incidentCount }) => {
  const navItems = [
    { id: 'operations' as RouteId, label: 'Operations', icon: Compass },
    { id: 'watch' as RouteId, label: 'Watch Service', icon: Radar },
    { id: 'incidents' as RouteId, label: 'Incidents', icon: AlertOctagon, badge: incidentCount },
    { id: 'satellite' as RouteId, label: 'SAR Catalog', icon: Satellite },
    { id: 'ais' as RouteId, label: 'AIS Traffic', icon: Ship },
    { id: 'analysis' as RouteId, label: 'Attribution', icon: Scale },
    { id: 'reports' as RouteId, label: 'Reports', icon: FileText },
    { id: 'settings' as RouteId, label: 'Settings', icon: Settings },
    { id: 'system' as RouteId, label: 'System', icon: Cpu },
  ];

  return (
    <aside className="w-52 bg-white border-r border-m-border flex flex-col justify-between py-3 select-none shrink-0">
      <nav className="space-y-0.5 px-2">
        <div className="px-3 pb-2 text-[10px] font-semibold text-m-muted tracking-wider uppercase">
          Navigation
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentRoute === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onNavigate(item.id)}
              className={`w-full flex items-center justify-between px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                isActive
                  ? 'bg-m-blue-light text-m-blue font-semibold'
                  : 'text-m-secondary hover:text-m-primary hover:bg-m-surface'
              }`}
            >
              <div className="flex items-center gap-2.5">
                <Icon className={`w-4 h-4 ${isActive ? 'text-m-blue' : 'text-m-muted'}`} />
                <span>{item.label}</span>
              </div>
              {item.badge !== undefined && item.badge > 0 && (
                <span className="px-1.5 py-0.5 rounded-full text-[10px] font-bold bg-m-red-light text-m-red">
                  {item.badge}
                </span>
              )}
            </button>
          );
        })}
      </nav>

      {/* Footer Info */}
      <div className="px-3 text-[10px] text-m-muted space-y-0.5 border-t border-m-border pt-3 mt-2">
        <div className="font-semibold text-m-secondary">COPERNICUS OData: ACTIVE</div>
        <div>LAGRANGIAN RK4: LOADED</div>
        <div>SIH 26143 / v2.0-PROD</div>
      </div>
    </aside>
  );
};
