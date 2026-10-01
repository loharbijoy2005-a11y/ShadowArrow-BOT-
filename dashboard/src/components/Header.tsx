'use client';

import React, { useState } from 'react';
import { Activity, Play, Pause, Zap, ShieldCheck, AlertOctagon, ExternalLink, Globe } from 'lucide-react';

interface HeaderProps {
  botStatus: 'RUNNING' | 'PAUSED' | 'RATE_LIMITED';
  requestDelay: number;
  onStatusChange: (status: 'RUNNING' | 'PAUSED' | 'RATE_LIMITED') => void;
  onDelayChange: (delay: number) => void;
}

export default function Header({ botStatus, requestDelay, onStatusChange }: HeaderProps) {
  const [loading, setLoading] = useState(false);

  const toggleStatus = async () => {
    setLoading(true);
    const newStatus = botStatus === 'RUNNING' ? 'PAUSED' : 'RUNNING';
    try {
      await fetch('/api/stats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: newStatus === 'PAUSED' ? 'pause' : 'resume' })
      });
      onStatusChange(newStatus);
    } catch (e) {
      console.error('Status change error', e);
    } finally {
      setLoading(false);
    }
  };

  const handleKillSwitch = async () => {
    if (!confirm('EMERGENCY KILL SWITCH: Halt all outgoing Wikidata write requests instantly?')) {
      return;
    }
    setLoading(true);
    try {
      await fetch('/api/stats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'kill' })
      });
      onStatusChange('PAUSED');
    } catch (e) {
      console.error('Kill switch error', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <header className="border-b border-slate-800 bg-slate-950/90 backdrop-blur-xl sticky top-0 z-50 shadow-2xl">
      {/* Top Wikimedia Status Bar */}
      <div className="bg-gradient-to-r from-blue-950 via-slate-900 to-indigo-950 text-[11px] py-1 px-4 border-b border-slate-800/80 flex items-center justify-between font-mono">
        <div className="flex items-center space-x-3 text-slate-300">
          <span className="inline-flex items-center text-blue-400 font-bold">
            <Globe className="w-3 h-3 mr-1" /> WIKIMEDIA TOOLFORGE OPERATOR
          </span>
          <span className="text-slate-600">•</span>
          <span>BOT: <strong className="text-white font-mono">SHADOWARROW_2026</strong></span>
          <span className="text-slate-600">•</span>
          <span>API: <span className="text-emerald-400 font-bold">www.wikidata.org</span></span>
        </div>
        <div className="hidden md:flex items-center space-x-3 text-slate-400">
          <a
            href="https://www.wikidata.org/wiki/User:SHADOWARROW_2026"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-blue-400 transition-colors flex items-center"
          >
            User Page <ExternalLink className="w-2.5 h-2.5 ml-1" />
          </a>
          <span>•</span>
          <span className="text-emerald-400 font-semibold">0.8s Rate-Limit Compliant</span>
        </div>
      </div>

      {/* Main Header Nav */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-3.5 flex flex-col md:flex-row items-center justify-between gap-4">
        
        {/* Branding & Logo */}
        <div className="flex items-center space-x-3.5">
          {/* Authentic Wikimedia Style Logo Badge */}
          <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-blue-600 via-indigo-600 to-teal-500 p-0.5 shadow-lg shadow-blue-500/20 shrink-0">
            <div className="w-full h-full bg-slate-950 rounded-[14px] flex items-center justify-center font-black text-xl text-blue-400 font-serif tracking-tighter">
              Wd
            </div>
          </div>
          <div>
            <div className="flex items-center space-x-2.5">
              <h1 className="text-lg font-black tracking-tight text-white font-sans">
                WIKIDATA AUTOMATION ENGINE
              </h1>
              <span className="px-2 py-0.5 text-[10px] font-mono font-black uppercase tracking-wider bg-blue-500/10 text-blue-400 border border-blue-500/30 rounded-md">
                SPECIAL ADMIN v2.0
              </span>
            </div>
            <p className="text-xs text-slate-400 font-medium">
              Sitelink-Verified Indian Entities • Zero-Error Multi-Language Pipeline
            </p>
          </div>
        </div>

        {/* Master Control Buttons */}
        <div className="flex flex-wrap items-center gap-3">
          
          {/* Status Badge */}
          <div className="flex items-center space-x-2 px-3.5 py-1.5 rounded-xl bg-slate-900 border border-slate-800 shadow-inner">
            <span className="text-xs text-slate-400 font-semibold">Engine:</span>
            <div className="flex items-center space-x-2">
              <span className={`w-2.5 h-2.5 rounded-full ${
                botStatus === 'RUNNING' ? 'bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.9)] animate-pulse' : 'bg-rose-500'
              }`} />
              <span className={`text-xs font-black uppercase tracking-wider ${
                botStatus === 'RUNNING' ? 'text-emerald-400' : 'text-rose-400'
              }`}>
                {botStatus === 'RUNNING' ? 'ACTIVE' : 'PAUSED'}
              </span>
            </div>
          </div>

          {/* Speed Throttle Badge */}
          <div className="hidden sm:flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-blue-950/40 border border-blue-500/30 text-blue-300 text-xs font-mono font-bold">
            <Zap className="w-3.5 h-3.5 text-blue-400" />
            <span>0.8s (75 edits/min)</span>
          </div>

          {/* 1-Click BOT ON / OFF Switch */}
          <button
            onClick={toggleStatus}
            disabled={loading}
            className={`flex items-center space-x-2 px-4 py-2 rounded-xl text-xs font-black tracking-wide uppercase transition-all shadow-md active:scale-95 ${
              botStatus === 'RUNNING'
                ? 'bg-rose-600 hover:bg-rose-500 text-white shadow-rose-600/20 border border-rose-400/40'
                : 'bg-emerald-600 hover:bg-emerald-500 text-white shadow-emerald-600/20 border border-emerald-400/40 animate-pulse'
            }`}
          >
            {botStatus === 'RUNNING' ? (
              <>
                <Pause className="w-4 h-4" />
                <span>TURN BOT OFF</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4 fill-current" />
                <span>TURN BOT ON</span>
              </>
            )}
          </button>

          {/* Emergency Kill Switch */}
          <button
            onClick={handleKillSwitch}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-2 rounded-xl text-xs font-bold bg-slate-900 hover:bg-rose-950/60 text-slate-300 hover:text-rose-300 border border-slate-800 hover:border-rose-500/40 transition-all"
          >
            <AlertOctagon className="w-3.5 h-3.5 text-rose-400" />
            <span>Emergency Kill</span>
          </button>

        </div>
      </div>
    </header>
  );
}
