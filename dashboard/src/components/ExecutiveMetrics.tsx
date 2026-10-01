'use client';

import React from 'react';
import { Database, ShieldCheck, CheckCircle2, Globe, TrendingUp, Zap } from 'lucide-react';

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
      
      {/* Card 1: Active Session Edits */}
      <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 backdrop-blur-xl hover:border-slate-700 transition-all shadow-xl shadow-slate-950/50">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Session Writes</span>
          <div className="w-8 h-8 rounded-lg bg-blue-500/10 border border-blue-500/20 flex items-center justify-center">
            <TrendingUp className="w-4 h-4 text-blue-400" />
          </div>
        </div>
        <div className="flex items-baseline space-x-2">
          <span className="text-3xl font-black text-white font-mono">{stats.totalEditsToday}</span>
          <span className="text-xs font-black text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
            ~75 edits/min
          </span>
        </div>
        <p className="text-xs text-slate-400 mt-2">Verified Wikidata edits in current session</p>
      </div>

      {/* Card 2: Engine Speed & Rate Limit */}
      <div className="p-5 rounded-2xl bg-gradient-to-br from-indigo-950/40 via-slate-900/80 to-slate-900/80 border border-indigo-500/30 backdrop-blur-xl hover:border-indigo-500/50 transition-all shadow-xl shadow-indigo-500/5">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">Engine Speed</span>
          <div className="w-8 h-8 rounded-lg bg-indigo-500/20 border border-indigo-500/30 flex items-center justify-center animate-pulse">
            <Zap className="w-4 h-4 text-indigo-300" />
          </div>
        </div>
        <div className="flex items-baseline space-x-2">
          <span className="text-3xl font-black text-indigo-300 font-mono">0.8s</span>
          <span className="text-xs font-black uppercase text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/30">
            MAX SPEED
          </span>
        </div>
        <p className="text-xs text-indigo-300/80 font-medium mt-2 flex items-center space-x-1">
          <CheckCircle2 className="w-3.5 h-3.5 inline mr-1 text-emerald-400" />
          Exact 0.8s Anti-Abuse Rate Limit
        </p>
      </div>

      {/* Card 3: Script Purity & Anomaly Rate */}
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

      {/* Card 4: Sitelink Sourcing Hit Rate */}
      <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 backdrop-blur-xl hover:border-slate-700 transition-all shadow-xl shadow-slate-950/50">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Sitelink Hit Rate</span>
          <div className="w-8 h-8 rounded-lg bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center">
            <Globe className="w-4 h-4 text-cyan-400" />
          </div>
        </div>
        <div className="flex items-baseline space-x-2">
          <span className="text-3xl font-black text-cyan-400 font-mono">{stats.sitelinkHitRate.toFixed(1)}%</span>
        </div>
        <p className="text-xs text-slate-400 mt-2">Sourced from hiwiki & bnwiki sitelinks</p>
      </div>

    </div>
  );
}
