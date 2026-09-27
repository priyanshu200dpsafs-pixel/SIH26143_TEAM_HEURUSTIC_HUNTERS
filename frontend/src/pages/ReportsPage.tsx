import React, { useState, useEffect } from 'react';
import {
  FileText,
  Download,
  Eye,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Hash,
  X,
  FileCode,
} from 'lucide-react';
import { api } from '../api/client';
import { ReportRecord } from '../types';

interface Props {
  initialReportId?: string;
  onNavigate: (route: string, id?: string) => void;
}

export const ReportsPage: React.FC<Props> = ({ initialReportId, onNavigate }) => {
  const [loading, setLoading] = useState(true);
  const [reports, setReports] = useState<ReportRecord[]>([]);
  const [selectedReportId, setSelectedReportId] = useState<string | null>(initialReportId || null);
  const [previewHtml, setPreviewHtml] = useState<string | null>(null);
  const [verifyState, setVerifyState] = useState<Record<string, { valid: boolean; hash: string }>>({});

  const loadReports = async () => {
    setLoading(true);
    try {
      const res = await api.listReports();
      setReports(res.reports || []);
      if (initialReportId && res.reports.some((r) => r.report_id === initialReportId)) {
        handleViewReport(initialReportId);
      }
    } catch (err) {
      console.error('Failed to load reports:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReports();
  }, [initialReportId]);

  const handleViewReport = async (reportId: string) => {
    setSelectedReportId(reportId);
    try {
      const data = await api.getReport(reportId);
      setPreviewHtml(data.html_content);
    } catch (err: any) {
      alert(`Could not load report content: ${err.message}`);
    }
  };

  const handleVerifyHash = async (reportId: string) => {
    try {
      const res = await api.verifyReport(reportId);
      setVerifyState((prev) => ({
        ...prev,
        [reportId]: { valid: res.valid, hash: res.computed_hash },
      }));
      if (res.valid) {
        alert(`Cryptographic Integrity Verified: SHA-256 seal matches disk state.\nHash: ${res.computed_hash}`);
      } else {
        alert(`Hash Verification Failed: ${res.error || 'Tampered or mismatch'}`);
      }
    } catch (err: any) {
      alert(`Hash check failed: ${err.message}`);
    }
  };

  const handleDownload = (reportId: string, format: 'html' | 'json') => {
    const url = api.getReportDownloadUrl(reportId, format);
    window.open(url, '_blank');
  };

  return (
    <div className="h-full flex flex-col overflow-hidden bg-m-bg p-4 space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-m-border pb-3 shrink-0">
        <div>
          <h1 className="text-lg font-bold text-m-primary flex items-center gap-2">
            <FileText className="w-5 h-5 text-m-blue" />
            Evidentiary Dossiers & Prosecutor Briefs
          </h1>
          <p className="text-xs text-m-muted">
            Forensic incident briefs compiled for international maritime law enforcement (MARPOL 73/78 Annex I & UNCLOS).
          </p>
        </div>

        <button
          onClick={loadReports}
          disabled={loading}
          className="px-3 py-1.5 rounded bg-m-surface hover:bg-m-border border border-m-divider text-xs font-bold text-m-primary flex items-center gap-1.5 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh Reports
        </button>
      </div>

      {/* Reports Table */}
      <div className="flex-1 bg-white border border-m-border rounded-lg overflow-hidden flex flex-col">
        <div className="p-3 border-b border-m-border bg-m-bg flex items-center justify-between">
          <span className="text-xs font-bold text-m-primary uppercase tracking-wider">
            Compiled Forensic Archives ({reports.length} Sealed Dossiers)
          </span>
          <span className="text-[10px] font-mono text-m-muted">Directory: data/reports/</span>
        </div>

        <div className="overflow-x-auto flex-1">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-m-bg text-m-muted uppercase font-mono text-[10px] tracking-wider sticky top-0">
              <tr>
                <th className="py-2.5 px-4">Dossier Identifier</th>
                <th className="py-2.5 px-3">Linked Incident</th>
                <th className="py-2.5 px-3">Compilation Date</th>
                <th className="py-2.5 px-3">Primary Suspect</th>
                <th className="py-2.5 px-3">SHA-256 Chain of Custody</th>
                <th className="py-2.5 px-3">File Size</th>
                <th className="py-2.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-navy-800">
              {reports.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-m-muted text-xs">
                    {loading ? 'Reading forensic archives...' : 'No dossiers compiled yet. Navigate to an incident to generate one.'}
                  </td>
                </tr>
              ) : (
                reports.map((rep) => {
                  const verified = verifyState[rep.report_id];

                  return (
                    <tr key={rep.report_id} className="hover:bg-m-surface/60 transition select-none">
                      <td className="py-3 px-4 font-mono font-bold text-m-blue flex items-center gap-1.5">
                        <FileText className="w-4 h-4 text-m-muted shrink-0" />
                        {rep.report_id}
                      </td>

                      <td className="py-3 px-3 font-mono font-bold text-m-primary">
                        <button
                          onClick={() => onNavigate('incidents', rep.incident_id)}
                          className="hover:underline text-m-blue"
                        >
                          {rep.incident_id} →
                        </button>
                      </td>

                      <td className="py-3 px-3 text-m-secondary font-mono text-[11px]">
                        {new Date(rep.created_at).toLocaleString()}
                      </td>

                      <td className="py-3 px-3">
                        {rep.top_suspect_name ? (
                          <div>
                            <span className="font-semibold text-m-primary">{rep.top_suspect_name}</span>
                            <span className="text-[10px] text-m-muted block font-mono">
                              MMSI: {rep.top_suspect_mmsi} | Score: {rep.composite_score?.toFixed(3)}
                            </span>
                          </div>
                        ) : (
                          <span className="text-m-muted italic">None attributed</span>
                        )}
                      </td>

                      <td className="py-3 px-3 font-mono text-[10px] text-m-muted">
                        <div className="flex items-center gap-1.5">
                          <span className="text-m-secondary truncate max-w-[140px]">{rep.sha256_hash}</span>
                          {verified ? (
                            verified.valid ? (
                              <span title="Hash verified"><CheckCircle2 className="w-3.5 h-3.5 text-m-green shrink-0" /></span>
                            ) : (
                              <span title="Hash mismatch"><XCircle className="w-3.5 h-3.5 text-m-red shrink-0" /></span>
                            )
                          ) : null}
                        </div>
                      </td>

                      <td className="py-3 px-3 font-mono text-m-secondary">
                        {(rep.file_size_bytes / 1024).toFixed(1)} KB
                      </td>

                      <td className="py-3 px-4 text-right space-x-1">
                        <button
                          onClick={() => handleVerifyHash(rep.report_id)}
                          className="px-2 py-1 bg-m-bg hover:bg-m-surface border border-m-border text-m-secondary hover:text-m-green rounded text-[11px] font-mono transition"
                          title="Cryptographically verify SHA-256 seal"
                        >
                          Verify Seal
                        </button>
                        <button
                          onClick={() => handleViewReport(rep.report_id)}
                          className="px-2.5 py-1 bg-m-blue/20 hover:bg-m-blue/30 border border-cyan-500/40 text-m-blue rounded text-[11px] font-bold transition inline-flex items-center gap-1"
                        >
                          <Eye className="w-3 h-3" /> View Brief
                        </button>
                        <button
                          onClick={() => handleDownload(rep.report_id, 'html')}
                          className="px-2 py-1 bg-m-bg hover:bg-m-surface border border-m-border text-m-secondary hover:text-m-primary rounded text-[11px] font-mono transition"
                          title="Download HTML Brief"
                        >
                          HTML
                        </button>
                        <button
                          onClick={() => handleDownload(rep.report_id, 'json')}
                          className="px-2 py-1 bg-m-bg hover:bg-m-surface border border-m-border text-m-secondary hover:text-m-primary rounded text-[11px] font-mono transition"
                          title="Download Evidentiary JSON"
                        >
                          JSON
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Forensic Report Viewer Modal */}
      {selectedReportId && previewHtml && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="w-full max-w-5xl bg-white border border-m-border rounded-lg shadow-popup overflow-hidden flex flex-col h-[90vh]">
            <div className="flex items-center justify-between px-4 py-3 border-b border-m-border bg-m-bg">
              <div className="flex items-center gap-2">
                <FileText className="w-4 h-4 text-m-blue" />
                <span className="text-xs font-bold text-m-primary uppercase tracking-wider">
                  Prosecutor's Forensic Dossier: {selectedReportId}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => handleDownload(selectedReportId, 'html')}
                  className="px-2.5 py-1 bg-m-blue hover:bg-m-blue/90 text-m-primary rounded text-xs font-bold flex items-center gap-1"
                >
                  <Download className="w-3.5 h-3.5" /> Download
                </button>
                <button
                  onClick={() => {
                    setSelectedReportId(null);
                    setPreviewHtml(null);
                  }}
                  className="text-m-muted hover:text-m-primary"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Embedded HTML Dossier View */}
            <div className="flex-1 bg-m-bg overflow-hidden">
              <iframe
                title="Forensic Dossier"
                srcDoc={previewHtml}
                className="w-full h-full border-none bg-m-bg"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
