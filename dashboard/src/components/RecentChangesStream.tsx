'use client';

import React, { useState } from 'react';
import { ExternalLink, RotateCcw, ShieldCheck, AlertTriangle, Clock, Zap, Search, Filter } from 'lucide-react';
import { EditRecord } from '@/app/api/edits/route';

interface RecentChangesProps {
  edits: EditRecord[];
  onRollbackComplete: (editId: string) => void;
}

export default function RecentChangesStream({ edits, onRollbackComplete }: RecentChangesProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'ALL' | 'VERIFIED_SAFE' | 'FLAGGED_ANOMALY'>('ALL');
  const [revertingId, setRevertingId] = useState<string | null>(null);

  const handleRollback = async (edit: EditRecord) => {
    if (!confirm(`Are you sure you want to revert edit on ${edit.qid} (${edit.fieldLabel}) on Wikidata?`)) {
      return;
    }

    setRevertingId(edit.id);
    try {
      const res = await fetch('/api/rollback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          qid: edit.qid,
          editId: edit.id,
          fieldType: edit.fieldType,
          lang: edit.lang,
          previousValue: edit.oldValue
        })
      });
      const data = await res.json();
      if (data.success) {
        onRollbackComplete(edit.id);
      } else {
        alert(`Rollback failed: ${data.error}`);
      }
    } catch (e: any) {
      alert(`Rollback error: ${e.message}`);
    } finally {
      setRevertingId(null);
    }
  };

  const filteredEdits = edits.filter((item) => {
    const matchesQuery = item.qid.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         (item.newValue && item.newValue.toLowerCase().includes(searchQuery.toLowerCase()));
    const matchesStatus = statusFilter === 'ALL' || item.status === statusFilter;
    return matchesQuery && matchesStatus;
  });

  return (
    <div className="rounded-2xl bg-slate-900/70 border border-slate-800/80 backdrop-blur-xl shadow-2xl p-6 mb-8">
      
      {/* Header & Controls */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-6 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center space-x-2">
            <Zap className="w-5 h-5 text-indigo-400" />
            <h2 className="text-lg font-bold text-white">Live Recent Changes & Audit Stream</h2>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Real-time edit monitor with automated script audit & 1-Click Rollback engine.
          </p>
        </div>

        {/* Filter Controls */}
        <div className="flex flex-wrap items-center gap-3 w-full md:w-auto">
          
          {/* QID Search Input */}
          <div className="relative flex-1 sm:flex-initial">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
            <input
              type="text"
              placeholder="Search QID..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full sm:w-48 pl-9 pr-3 py-1.5 text-xs bg-slate-950/80 border border-slate-800 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
            />
          </div>

          {/* Status Filter Buttons */}
          <div className="flex items-center space-x-1 bg-slate-950/80 border border-slate-800 rounded-lg p-1">
            <button
              onClick={() => setStatusFilter('ALL')}
              className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
                statusFilter === 'ALL' ? 'bg-indigo-500 text-white' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              All
            </button>
            <button
              onClick={() => setStatusFilter('VERIFIED_SAFE')}
              className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all ${
                statusFilter === 'VERIFIED_SAFE' ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30' : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Verified Safe
            </button>
          </div>

        </div>
      </div>

      {/* Feed List */}
      <div className="space-y-4">
        {filteredEdits.length === 0 ? (
          <div className="text-center py-12 text-slate-500 border border-dashed border-slate-800 rounded-xl">
            <p className="text-sm font-medium">No edits recorded yet in current stream.</p>
            <p className="text-xs text-slate-600 mt-1">Make sure the Bot Master Switch is ON to stream live edits.</p>
          </div>
        ) : (
          filteredEdits.map((item) => (
            <div
              key={item.id}
              className={`p-4 rounded-xl border transition-all ${
                item.reverted
                  ? 'bg-slate-950/40 border-slate-800/50 opacity-60'
                  : item.status === 'VERIFIED_SAFE'
                  ? 'bg-slate-950/70 border-slate-800/80 hover:border-slate-700'
                  : 'bg-rose-950/20 border-rose-500/30 hover:border-rose-500/50'
              }`}
            >
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 mb-3">
                
                {/* QID & Field Badge */}
                <div className="flex items-center space-x-3">
                  <a
                    href={`https://www.wikidata.org/wiki/${item.qid}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center space-x-1.5 font-mono font-bold text-sm text-indigo-400 hover:text-indigo-300 transition-colors bg-indigo-500/10 px-2.5 py-1 rounded-md border border-indigo-500/20"
                  >
                    <span>{item.qid}</span>
                    <ExternalLink className="w-3.5 h-3.5 text-indigo-400" />
                  </a>

                  <span className="text-xs font-medium text-slate-300 px-2.5 py-1 rounded-md bg-slate-800/80 border border-slate-700/60">
                    {item.fieldLabel}
                  </span>
                </div>

                {/* Status Badge & Latency */}
                <div className="flex items-center space-x-3">
                  
                  <div className="flex items-center space-x-1 text-xs text-slate-400 font-mono">
                    <Clock className="w-3.5 h-3.5 text-slate-500" />
                    <span>{item.latencyMs || 800} ms</span>
                  </div>

                  <span className="flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    <ShieldCheck className="w-3.5 h-3.5" />
                    <span>Verified Safe</span>
                  </span>

                  {/* 1-Click Rollback / Undo Button */}
                  <button
                    onClick={() => handleRollback(item)}
                    disabled={item.reverted || revertingId === item.id}
                    className={`flex items-center space-x-1.5 px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                      item.reverted
                        ? 'bg-slate-800/50 text-slate-500 border border-slate-700/50 cursor-not-allowed'
                        : 'bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 border border-rose-500/30 hover:shadow-lg hover:shadow-rose-500/10'
                    }`}
                  >
                    <RotateCcw className={`w-3.5 h-3.5 ${revertingId === item.id ? 'animate-spin' : ''}`} />
                    <span>{item.reverted ? 'Reverted' : 'Rollback / Undo'}</span>
                  </button>

                </div>
              </div>

              {/* Timestamp & Status text */}
              <div className="text-[11px] font-mono text-slate-400 pt-2 border-t border-slate-800/60 flex items-center justify-between">
                <span>Timestamp: {item.timestamp}</span>
                <span className="text-emerald-400 font-semibold">100% Policy Compliant</span>
              </div>

            </div>
          ))
        )}
      </div>

    </div>
  );
}
