'use client';

import React, { useState } from 'react';
import { Search, Eye, CheckCircle, AlertCircle, ArrowRight, Globe, Layers, Sparkles } from 'lucide-react';

export default function EntityInspector() {
  const [qidInput, setQidInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [inspection, setInspection] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleInspect = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!qidInput.trim()) return;

    setLoading(true);
    setError(null);
    setInspection(null);

    try {
      const res = await fetch('/api/inspect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qid: qidInput })
      });
      const data = await res.json();
      if (data.success) {
        setInspection(data.inspection);
      } else {
        setError(data.error || 'Inspection failed.');
      }
    } catch (err: any) {
      setError(err.message || 'Network error');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-2xl bg-slate-900/70 border border-slate-800/80 backdrop-blur-xl shadow-2xl p-6 mb-8">
      
      {/* Header */}
      <div className="flex items-center space-x-2 mb-4 border-b border-slate-800 pb-3">
        <Eye className="w-5 h-5 text-indigo-400" />
        <h2 className="text-lg font-bold text-white">Single Entity Inspector (Dry-Run Simulator)</h2>
      </div>
      <p className="text-xs text-slate-400 mb-4">
        Input any Wikidata QID to preview extracted sitelinks, matched Indian state, and intended edit payload WITHOUT modifying Wikidata.
      </p>

      {/* Input Form */}
      <form onSubmit={handleInspect} className="flex gap-3 mb-6">
        <div className="relative flex-1">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
          <input
            type="text"
            placeholder="Enter Wikidata QID (e.g. Q12498001, Q130977614)..."
            value={qidInput}
            onChange={(e) => setQidInput(e.target.value)}
            className="w-full pl-10 pr-4 py-2 bg-slate-950/90 border border-slate-800 rounded-xl text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors font-mono"
          />
        </div>
        <button
          type="submit"
          disabled={loading || !qidInput.trim()}
          className="px-5 py-2 rounded-xl text-xs font-bold bg-indigo-500 hover:bg-indigo-600 text-white transition-all shadow-lg shadow-indigo-500/25 flex items-center space-x-2 disabled:opacity-50"
        >
          {loading ? (
            <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              <span>Simulate Dry-Run</span>
            </>
          )}
        </button>
      </form>

      {/* Error Message */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950/30 border border-rose-500/30 text-rose-300 text-xs flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Inspection Output */}
      {inspection && (
        <div className="space-y-4 font-mono text-xs">
          
          {/* Item Meta Bar */}
          <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 flex flex-wrap items-center justify-between gap-4 font-sans">
            <div>
              <span className="text-xs text-slate-400">Target Entity:</span>
              <div className="text-base font-bold text-white font-mono">{inspection.qid}</div>
              <p className="text-xs text-slate-300 font-medium">"{inspection.enLabel}"</p>
            </div>
            <div>
              <span className="text-xs text-slate-400">English Description:</span>
              <p className="text-xs text-slate-300 italic font-mono">"{inspection.enDesc || 'None'}"</p>
            </div>
            <div>
              <span className="text-xs text-slate-400">Targetable:</span>
              <div className="mt-1">
                {inspection.isTargetable ? (
                  <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    YES (Eligible for Edit)
                  </span>
                ) : (
                  <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-amber-500/10 text-amber-400 border border-amber-500/20">
                    NO (All Fields Present or Missing Match)
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Sitelinks & State Match */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            
            {/* Sitelinks Extracted */}
            <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800">
              <div className="flex items-center space-x-2 mb-3 text-slate-300 font-sans font-bold">
                <Globe className="w-4 h-4 text-indigo-400" />
                <span>Extracted Wikipedia Sitelinks</span>
              </div>
              <div className="space-y-2">
                <div className="flex justify-between items-center bg-slate-900 p-2 rounded border border-slate-800">
                  <span className="text-slate-400">bnwiki (Bengali):</span>
                  <span className="font-bold text-emerald-400">
                    {inspection.sitelinks.bnwiki ? `"${inspection.sitelinks.bnwiki}"` : 'Not Found'}
                  </span>
                </div>
                <div className="flex justify-between items-center bg-slate-900 p-2 rounded border border-slate-800">
                  <span className="text-slate-400">hiwiki (Hindi):</span>
                  <span className="font-bold text-emerald-400">
                    {inspection.sitelinks.hiwiki ? `"${inspection.sitelinks.hiwiki}"` : 'Not Found'}
                  </span>
                </div>
              </div>
            </div>

            {/* Parsed State Match */}
            <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800">
              <div className="flex items-center space-x-2 mb-3 text-slate-300 font-sans font-bold">
                <Layers className="w-4 h-4 text-indigo-400" />
                <span>State & Entity Type Match</span>
              </div>
              {inspection.stateMapping ? (
                <div className="space-y-2">
                  <div className="flex justify-between items-center bg-slate-900 p-2 rounded border border-slate-800">
                    <span className="text-slate-400">Indian State:</span>
                    <span className="font-bold text-white">{inspection.stateMapping.stateName}</span>
                  </div>
                  <div className="flex justify-between items-center bg-slate-900 p-2 rounded border border-slate-800">
                    <span className="text-slate-400">Entity Category:</span>
                    <span className="font-bold text-indigo-400 uppercase">{inspection.stateMapping.entityType}</span>
                  </div>
                </div>
              ) : (
                <p className="text-slate-500 italic p-2">No Indian state pattern matched in description.</p>
              )}
            </div>

          </div>

          {/* Intended Payload Preview */}
          <div className="p-4 rounded-xl bg-slate-950/90 border border-indigo-500/30">
            <div className="flex items-center justify-between mb-3 font-sans font-bold text-slate-200">
              <span className="flex items-center space-x-2">
                <CheckCircle className="w-4 h-4 text-emerald-400" />
                <span>Intended `wbeditentity` Payload (Dry-Run Preview)</span>
              </span>
              <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                100% Script Guardrail Verified
              </span>
            </div>
            <pre className="p-3 rounded-lg bg-slate-900 text-indigo-300 overflow-x-auto border border-slate-800 text-[11px] leading-relaxed">
              {JSON.stringify(inspection.intendedPayload, null, 2)}
            </pre>
          </div>

        </div>
      )}

    </div>
  );
}
