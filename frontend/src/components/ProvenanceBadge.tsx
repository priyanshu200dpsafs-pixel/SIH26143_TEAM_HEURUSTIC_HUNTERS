import React from 'react';
import { ProvenanceType } from '../types';

interface Props {
  type?: ProvenanceType | string;
  size?: 'sm' | 'md';
}

export const ProvenanceBadge: React.FC<Props> = ({ type = 'UNAVAILABLE', size = 'sm' }) => {
  const raw = String(type).toUpperCase();
  let label = raw;
  let color = 'bg-slate-100 text-slate-600 border-slate-300';

  if (raw.includes('SIMULATED') || raw.includes('REPLAY')) {
    label = 'SIMULATED / REPLAY';
    color = 'bg-purple-50 text-purple-700 border-purple-200';
  } else if (raw.includes('LIVE') || (raw.includes('REAL') && !raw.includes('REPLAY') && !raw.includes('ARCHIVED'))) {
    label = 'REAL / LIVE';
    color = 'bg-emerald-50 text-emerald-700 border-emerald-300';
  } else if (raw.includes('ARCHIVED')) {
    label = 'REAL ARCHIVED';
    color = 'bg-teal-50 text-teal-700 border-teal-300';
  } else if (raw.includes('INFERRED') || raw.includes('MODEL')) {
    label = 'INFERRED';
    color = 'bg-blue-50 text-blue-700 border-blue-200';
  }

  const px = size === 'sm' ? 'px-1.5 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs';

  return (
    <span className={`inline-flex items-center gap-1 font-mono font-semibold uppercase tracking-wider border rounded ${px} ${color}`}>
      <span className="w-1.5 h-1.5 rounded-full bg-current"></span>
      {label}
    </span>
  );
};
