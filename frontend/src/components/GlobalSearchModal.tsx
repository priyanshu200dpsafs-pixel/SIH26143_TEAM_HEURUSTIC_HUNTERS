import React, { useState, useEffect, useRef } from 'react';
import { Search, X, AlertOctagon, Ship, Satellite, MapPin, Loader2 } from 'lucide-react';
import { api } from '../api/client';

interface Props {
  isOpen: boolean;
  onClose: () => void;
  onNavigate: (route: string, id?: string) => void;
}

export const GlobalSearchModal: React.FC<Props> = ({ isOpen, onClose, onNavigate }) => {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<any>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery('');
      setResults(null);
    }
  }, [isOpen]);

  useEffect(() => {
    if (!query.trim()) {
      setResults(null);
      return;
    }
    const timer = setTimeout(async () => {
      setLoading(true);
      try {
        const data = await api.globalSearch(query.trim());
        setResults(data);
      } catch (err) {
        // ignore
      } finally {
        setLoading(false);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-20 bg-black/30 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl bg-white border border-m-border rounded-lg shadow-popup overflow-hidden flex flex-col max-h-[80vh]">
        {/* Search Input Bar */}
        <div className="flex items-center px-4 py-3 border-b border-m-border bg-m-bg">
          <Search className="w-5 h-5 text-m-blue shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search Incident ID, MMSI, IMO, Vessel name, Scene ID, or coordinates (lat, lon)..."
            className="w-full bg-transparent border-none outline-none px-3 text-sm text-m-primary placeholder:text-m-muted font-sans"
          />
          {loading && <Loader2 className="w-4 h-4 text-m-blue animate-spin shrink-0 mr-2" />}
          <button onClick={onClose} className="text-m-muted hover:text-m-primary transition">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Results Container */}
        <div className="overflow-y-auto p-4 space-y-4">
          {!query && (
            <div className="text-center py-8 text-m-muted text-xs">
              Type to search incidents, vessels, Sentinel-1 scenes, or input coordinates like <code className="text-m-blue font-mono">34.5, 18.3</code>.
            </div>
          )}

          {results?.coordinate_match && (
            <div>
              <div className="text-[10px] font-mono font-bold text-m-muted uppercase tracking-wider mb-2">Coordinate Target</div>
              <button
                onClick={() => {
                  onClose();
                  onNavigate('operations');
                }}
                className="w-full flex items-center gap-3 p-2.5 rounded bg-m-bg hover:bg-m-surface border border-m-border text-left transition"
              >
                <MapPin className="w-4 h-4 text-m-blue shrink-0" />
                <div>
                  <div className="text-xs font-bold text-m-primary">{results.coordinate_match.label}</div>
                  <div className="text-[10px] text-m-muted">Navigate map viewport to coordinates</div>
                </div>
              </button>
            </div>
          )}

          {results?.results?.INCIDENTS?.length > 0 && (
            <div>
              <div className="text-[10px] font-mono font-bold text-m-muted uppercase tracking-wider mb-2">
                Incidents ({results.results.INCIDENTS.length})
              </div>
              <div className="space-y-1.5">
                {results.results.INCIDENTS.map((inc: any) => (
                  <button
                    key={inc.id}
                    onClick={() => {
                      onClose();
                      onNavigate('incidents', inc.id);
                    }}
                    className="w-full flex items-center justify-between p-2.5 rounded bg-m-bg hover:bg-m-surface border border-m-border text-left transition"
                  >
                    <div className="flex items-center gap-2.5">
                      <AlertOctagon className="w-4 h-4 text-m-red shrink-0" />
                      <div>
                        <div className="text-xs font-bold text-m-primary">{inc.title}</div>
                        <div className="text-[10px] text-m-muted">{inc.subtitle}</div>
                      </div>
                    </div>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-white border border-m-border text-m-blue">
                      Top Suspect: {inc.top_suspect}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {results?.results?.VESSELS?.length > 0 && (
            <div>
              <div className="text-[10px] font-mono font-bold text-m-muted uppercase tracking-wider mb-2">
                Vessels in Buffer ({results.results.VESSELS.length})
              </div>
              <div className="space-y-1.5">
                {results.results.VESSELS.map((v: any) => (
                  <button
                    key={v.mmsi}
                    onClick={() => {
                      onClose();
                      onNavigate('ais', String(v.mmsi));
                    }}
                    className="w-full flex items-center justify-between p-2.5 rounded bg-m-bg hover:bg-m-surface border border-m-border text-left transition"
                  >
                    <div className="flex items-center gap-2.5">
                      <Ship className="w-4 h-4 text-m-blue shrink-0" />
                      <div>
                        <div className="text-xs font-bold text-m-primary">{v.title}</div>
                        <div className="text-[10px] text-m-muted">{v.subtitle}</div>
                      </div>
                    </div>
                    <span className="text-[10px] font-mono text-m-muted">MMSI {v.mmsi}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {results?.results?.SATELLITE_PRODUCTS?.length > 0 && (
            <div>
              <div className="text-[10px] font-mono font-bold text-m-muted uppercase tracking-wider mb-2">
                Sentinel-1 Scenes ({results.results.SATELLITE_PRODUCTS.length})
              </div>
              <div className="space-y-1.5">
                {results.results.SATELLITE_PRODUCTS.map((p: any) => (
                  <button
                    key={p.id}
                    onClick={() => {
                      onClose();
                      onNavigate('satellite', p.id);
                    }}
                    className="w-full flex items-center justify-between p-2.5 rounded bg-m-bg hover:bg-m-surface border border-m-border text-left transition"
                  >
                    <div className="flex items-center gap-2.5">
                      <Satellite className="w-4 h-4 text-m-green shrink-0" />
                      <div>
                        <div className="text-xs font-bold text-m-primary truncate max-w-md">{p.title}</div>
                        <div className="text-[10px] text-m-muted">{p.subtitle}</div>
                      </div>
                    </div>
                    <span className="text-[10px] font-mono text-m-muted">{p.status}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {results && results.total_matches === 0 && (
            <div className="text-center py-6 text-m-muted text-xs">
              No matching records found across incidents, vessels, or satellite scenes.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
