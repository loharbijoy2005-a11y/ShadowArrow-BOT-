'use client';

import React from 'react';
import { Database, ShieldCheck, CheckCircle2, Globe, TrendingUp, AlertTriangle } from 'lucide-react';

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
  };
}

export default function ExecutiveMetrics({ stats }: StatsProps) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
      
      {/* Card 1: Edits Today */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-xl hover:border-slate-700 transition-all shadow-xl shadow-slate-950/50">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Edits Today</span>
          <div className="w-8 h-8 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center">
            <TrendingUp className="w-4 h-4 text-indigo-400" />
          </div>
        </div>
        <div className="flex items-baseline space-x-2">
          <span className="text-3xl font-extrabold text-white font-mono">{stats.totalEditsToday}</span>
          <span className="text-xs font-semibold text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            +18/hr
          </span>
        </div>
        <p className="text-xs text-slate-400 mt-2">Active session writes</p>
      </div>

      {/* Card 2: Total Lifetime Edits */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-xl hover:border-slate-700 transition-all shadow-xl shadow-slate-950/50">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Lifetime Edits</span>
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
            <Database className="w-4 h-4 text-emerald-400" />
          </div>
        </div>
        <div className="flex items-baseline space-x-2">
          <span className="text-3xl font-extrabold text-white font-mono">{stats.totalEditsLifetime.toLocaleString()}</span>
        </div>
        <p className="text-xs text-emerald-400/90 font-medium mt-2 flex items-center space-x-1">
          <CheckCircle2 className="w-3 h-3 inline mr-1 text-emerald-400" />
          100% MediaWiki Compliant
        </p>
      </div>

      {/* Card 3: Error & Anomaly Rate */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-xl hover:border-slate-700 transition-all shadow-xl shadow-slate-950/50">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Anomaly Rate</span>
          <div className="w-8 h-8 rounded-lg bg-rose-500/10 border border-rose-500/20 flex items-center justify-center">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </div>
        </div>
        <div className="flex items-baseline space-x-2">
          <span className="text-3xl font-extrabold text-emerald-400 font-mono">{stats.anomalyRate.toFixed(1)}%</span>
          <span className="text-xs font-semibold text-slate-400">({stats.flaggedCount} flagged)</span>
        </div>
        <p className="text-xs text-slate-400 mt-2">Zero-Tolerance script guardrails</p>
      </div>

      {/* Card 4: Sitelink Hit Rate */}
      <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800/80 backdrop-blur-xl hover:border-slate-700 transition-all shadow-xl shadow-slate-950/50">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Sitelink Hit Rate</span>
          <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
            <Globe className="w-4 h-4 text-cyan-400" />
          </div>
        </div>
        <div className="flex items-baseline space-x-2">
          <span className="text-3xl font-extrabold text-cyan-400 font-mono">{stats.sitelinkHitRate.toFixed(1)}%</span>
        </div>
        <p className="text-xs text-slate-400 mt-2">Sourced from bnwiki / hiwiki</p>
      </div>

    </div>
  );
}
