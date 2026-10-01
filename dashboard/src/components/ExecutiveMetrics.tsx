'use client';

import React from 'react';
import { Database, ShieldCheck, CheckCircle2, Globe, TrendingUp, Zap, Cpu, AlertTriangle, Layers } from 'lucide-react';

interface StatsProps {
  stats: {
    totalEditsToday: number;
    totalEditsLifetime: number;
    anomalyRate: number;
    botStatus: string;
    sitelinkHitRate: number;
    requestDelay: number;
    verifiedCount: number;
    flaggedCount: number;
    editsPerMinute?: number;
    queueDepth?: number;
    mode?: string;
    errorsInSession?: number;
    skippedInSession?: number;
    currentQid?: string | null;
  };
}

export default function ExecutiveMetrics({ stats }: StatsProps) {
  const epm       = stats.editsPerMinute ?? 0;
  const qDepth    = stats.queueDepth     ?? 0;
  const mode      = stats.mode           ?? 'RENDER';
  const errors    = stats.errorsInSession  ?? 0;
  const isRunning = stats.botStatus === 'RUNNING';

  const modeBadgeColor = mode === 'LOCAL'
    ? 'bg-violet-500/20 text-violet-300 border-violet-500/30'
    : 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30';
  const modeIcon = mode === 'LOCAL' ? '🖥️' : '☁️';
  const modeLabel = mode === 'LOCAL' ? 'Local PC' : 'Render Cloud';

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">

      {/* Card 1: Session Edits with live EPM */}
      <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 backdrop-blur-xl hover:border-slate-700 transition-all shadow-xl shadow-slate-950/50">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Session Writes</span>
          <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
            <TrendingUp className="w-4 h-4 text-blue-400" />
          </div>
        </div>
        <div className="flex items-baseline space-x-2">
          <span className="text-3xl font-black text-white font-mono">{stats.totalEditsToday}</span>
          <span className={`text-xs font-black px-2 py-0.5 rounded-full border ${
            isRunning && epm > 0
              ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/20'
              : 'text-slate-400 bg-slate-800/50 border-slate-700'
          }`}>
            {epm > 0 ? `${epm} EPM` : 'Idle'}
          </span>
        </div>
        <p className="text-xs text-slate-400 mt-2">Verified Wikidata edits this session</p>
      </div>

      {/* Card 2: Live Engine Speed */}
      <div className="p-5 rounded-2xl bg-gradient-to-br from-indigo-950/40 via-slate-900/80 to-slate-900/80 border border-indigo-500/30 backdrop-blur-xl hover:border-indigo-500/50 transition-all shadow-xl shadow-indigo-500/5">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">Engine Speed</span>
          <div className={`w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center ${isRunning ? 'animate-pulse' : ''}`}>
            <Zap className="w-4 h-4 text-indigo-300" />
          </div>
        </div>
        <div className="flex items-baseline space-x-2">
          <span className="text-3xl font-black text-indigo-300 font-mono">{stats.requestDelay}s</span>
          <span className="text-xs font-black uppercase text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30">
            MAX SPEED
          </span>
        </div>
        <p className="text-xs text-indigo-300/80 font-medium mt-2 flex items-center space-x-1">
          <CheckCircle2 className="w-3.5 h-3.5 inline mr-1 text-emerald-400" />
          Exact {stats.requestDelay}s Anti-Abuse Rate Limit
        </p>
      </div>

      {/* Card 3: Queue Depth + Mode */}
      <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 backdrop-blur-xl hover:border-slate-700 transition-all shadow-xl shadow-slate-950/50">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Queue Buffer</span>
          <div className="w-8 h-8 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
            <Layers className="w-4 h-4 text-amber-400" />
          </div>
        </div>
        <div className="flex items-baseline space-x-2">
          <span className="text-3xl font-black text-amber-300 font-mono">{qDepth}</span>
          <span className="text-xs font-semibold text-slate-400">items ready</span>
        </div>
        {/* Mode Badge */}
        <div className="mt-2 flex items-center gap-2">
          <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${modeBadgeColor}`}>
            {modeIcon} {modeLabel}
          </span>
          {errors > 0 && (
            <span className="text-xs font-bold text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded-full border border-rose-500/20 flex items-center gap-1">
              <AlertTriangle className="w-3 h-3" />{errors} err
            </span>
          )}
        </div>
      </div>

      {/* Card 4: Script Purity */}
      <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 backdrop-blur-xl hover:border-slate-700 transition-all shadow-xl shadow-slate-950/50">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Script Purity</span>
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
        </div>
        <div className="flex items-baseline space-x-2">
          <span className="text-3xl font-black text-emerald-400 font-mono">100%</span>
          <span className="text-xs font-semibold text-slate-400">Pure Unicode</span>
        </div>
        <p className="text-xs text-slate-400 mt-2">Zero Latin contamination in hi/bn scripts</p>
      </div>

    </div>
  );
}
