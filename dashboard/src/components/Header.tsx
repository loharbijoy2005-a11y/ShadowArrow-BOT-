'use client';

import React, { useState } from 'react';
import { Activity, Play, Pause, Zap, ShieldCheck, AlertOctagon, Sliders } from 'lucide-react';

interface HeaderProps {
  botStatus: 'RUNNING' | 'PAUSED' | 'RATE_LIMITED';
  requestDelay: number;
  onStatusChange: (status: 'RUNNING' | 'PAUSED' | 'RATE_LIMITED') => void;
  onDelayChange: (delay: number) => void;
}

export default function Header({ botStatus, requestDelay, onStatusChange, onDelayChange }: HeaderProps) {
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
    if (!confirm('EMERGENCY KILL SWITCH: Are you sure you want to halt all outgoing Wikidata write requests instantly?')) {
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

  const handleDelaySlider = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    onDelayChange(val);
    try {
      await fetch('/api/stats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'set_delay', delay: val })
      });
    } catch (err) {
      console.error('Delay change error', err);
    }
  };

  return (
    <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4 flex flex-col md:flex-row items-center justify-between gap-4">
        
        {/* Brand & Title */}
        <div className="flex items-center space-x-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-500 to-pink-500 p-0.5 shadow-lg shadow-indigo-500/20 flex items-center justify-center">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
              <Zap className="w-5 h-5 text-indigo-400 animate-pulse" />
            </div>
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h1 className="text-xl font-bold bg-gradient-to-r from-white via-slate-100 to-slate-400 bg-clip-text text-transparent">
                Wikidata Automation Engine
              </h1>
              <span className="px-2 py-0.5 text-[10px] font-mono font-semibold uppercase tracking-wider bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 rounded-md">
                v2.0 Zero-Error
              </span>
            </div>
            <p className="text-xs text-slate-400 font-medium">
              Live Recent Changes & Quality Audit Feed
            </p>
          </div>
        </div>

        {/* Status Indicator & Bot Controls */}
        <div className="flex flex-wrap items-center gap-3">
          
          {/* Status Badge */}
          <div className="flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-slate-950/90 border border-slate-800 shadow-md">
            <span className="text-xs text-slate-400 font-medium">Bot State:</span>
            <div className="flex items-center space-x-2">
              <span className={`w-3 h-3 rounded-full ${
                botStatus === 'RUNNING' ? 'bg-emerald-500 shadow-[0_0_12px_rgba(16,185,129,0.9)] animate-pulse' :
                botStatus === 'RATE_LIMITED' ? 'bg-amber-500 shadow-[0_0_12px_rgba(245,158,11,0.9)]' :
                'bg-rose-500 shadow-[0_0_12px_rgba(244,63,94,0.9)]'
              }`} />
              <span className={`text-xs font-extrabold uppercase tracking-wider ${
                botStatus === 'RUNNING' ? 'text-emerald-400' :
                botStatus === 'RATE_LIMITED' ? 'text-amber-400' :
                'text-rose-400'
              }`}>
                {botStatus === 'RUNNING' ? 'ONLINE (ACTIVE)' : 'OFFLINE (PAUSED)'}
              </span>
            </div>
          </div>

          {/* Request Delay Indicator */}
          <div className="hidden sm:flex items-center space-x-2 px-3 py-2 rounded-xl bg-slate-950/80 border border-slate-800">
            <Zap className="w-3.5 h-3.5 text-indigo-400" />
            <span className="text-xs text-slate-400 font-medium">Safe Delay:</span>
            <span className="text-xs font-mono font-bold text-indigo-300">0.8s Rate-Limit</span>
          </div>

          {/* Main 1-Click BOT ON / OFF Button */}
          <button
            onClick={toggleStatus}
            disabled={loading}
            className={`flex items-center space-x-2 px-4 py-2 rounded-xl text-xs font-bold transition-all shadow-md active:scale-95 ${
              botStatus === 'RUNNING'
                ? 'bg-rose-500/15 hover:bg-rose-500/25 text-rose-300 border border-rose-500/40 shadow-rose-500/10'
                : 'bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/40 shadow-emerald-500/10'
            }`}
          >
            {botStatus === 'RUNNING' ? (
              <>
                <Pause className="w-4 h-4 text-rose-400" />
                <span>TURN BOT OFF</span>
              </>
            ) : (
              <>
                <Play className="w-4 h-4 text-emerald-400 animate-bounce" />
                <span>TURN BOT ON</span>
              </>
            )}
          </button>

          {/* Emergency Kill Switch */}
          <button
            onClick={handleKillSwitch}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-2 rounded-xl text-xs font-semibold bg-slate-950 hover:bg-rose-950/50 text-slate-400 hover:text-rose-300 border border-slate-800 hover:border-rose-500/40 transition-all"
          >
            <AlertOctagon className="w-3.5 h-3.5 text-rose-400" />
            <span>Emergency Kill</span>
          </button>

        </div>
      </div>
    </header>
  );
}
