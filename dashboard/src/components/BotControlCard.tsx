'use client';

import React, { useState } from 'react';
import { Power, Zap, Activity, Pause, Play, ShieldCheck, CheckCircle2, ExternalLink } from 'lucide-react';

interface BotControlCardProps {
  botStatus: 'RUNNING' | 'PAUSED' | 'RATE_LIMITED';
  onStatusChange: (newStatus: 'RUNNING' | 'PAUSED' | 'RATE_LIMITED') => void;
  statusMessage?: string;
  currentQid?: string | null;
}

export default function BotControlCard({
  botStatus,
  onStatusChange,
  statusMessage,
  currentQid
}: BotControlCardProps) {
  const [loading, setLoading] = useState(false);

  const isRunning = botStatus === 'RUNNING';

  const handleToggle = async () => {
    setLoading(true);
    const targetAction = isRunning ? 'pause' : 'resume';
    const nextStatus = isRunning ? 'PAUSED' : 'RUNNING';

    try {
      const res = await fetch('/api/stats', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: targetAction })
      });

      const data = await res.json();
      if (data.success) {
        onStatusChange(data.botStatus === 'RUNNING' ? 'RUNNING' : 'PAUSED');
      } else {
        onStatusChange(nextStatus);
      }
    } catch (err) {
      console.error('Error toggling bot power state:', err);
      onStatusChange(nextStatus);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={`relative overflow-hidden rounded-3xl p-6 sm:p-8 mb-8 border transition-all duration-300 shadow-2xl ${
      isRunning
        ? 'bg-gradient-to-r from-emerald-950/80 via-slate-900 to-slate-950 border-emerald-500/40 shadow-emerald-500/10'
        : 'bg-gradient-to-r from-slate-900 via-slate-900 to-slate-950 border-slate-800 shadow-slate-950/50'
    }`}>
      {/* Background Decorative Glow */}
      <div className={`absolute -right-20 -bottom-20 w-80 h-80 rounded-full blur-3xl pointer-events-none opacity-20 transition-all ${
        isRunning ? 'bg-emerald-500' : 'bg-blue-600'
      }`} />

      <div className="relative z-10 flex flex-col md:flex-row items-center justify-between gap-6">
        
        {/* Left Side: Telemetry Status */}
        <div className="flex items-center space-x-5 w-full md:w-auto">
          {/* Glowing Power Icon Badge */}
          <div className={`w-16 h-16 rounded-2xl flex items-center justify-center shrink-0 border transition-all ${
            isRunning
              ? 'bg-emerald-500/20 border-emerald-500/40 text-emerald-400 shadow-[0_0_25px_rgba(16,185,129,0.4)] animate-pulse'
              : 'bg-slate-800/80 border-slate-700 text-slate-400'
          }`}>
            <Power className="w-8 h-8" />
          </div>

          <div>
            <div className="flex items-center space-x-3">
              <h2 className="text-2xl font-black tracking-tight text-white font-sans">
                BOT MASTER POWER SWITCH
              </h2>
              <span className={`px-3 py-1 text-xs font-black uppercase tracking-wider rounded-full border shadow-sm ${
                isRunning
                  ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 shadow-emerald-500/20'
                  : 'bg-rose-500/20 text-rose-300 border-rose-500/40 shadow-rose-500/20'
              }`}>
                {isRunning ? '● ONLINE (ACTIVE)' : '○ OFFLINE (PAUSED)'}
              </span>
            </div>

            <p className="text-sm text-slate-300 font-medium mt-1">
              {isRunning
                ? statusMessage || 'Processing Wikidata batch queue @ 0.8s rate-limit interval'
                : 'Bot is paused. Click the button to activate live Wikidata edits.'}
            </p>

            {/* Currently Processing Entity Tag */}
            {currentQid && isRunning && (
              <div className="mt-2.5 inline-flex items-center space-x-2 text-xs font-mono bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 px-3 py-1 rounded-lg">
                <Activity className="w-3.5 h-3.5 animate-spin text-emerald-400" />
                <span>Currently Enriching:</span>
                <a
                  href={`https://www.wikidata.org/wiki/${currentQid}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="font-bold underline hover:text-white flex items-center"
                >
                  {currentQid} <ExternalLink className="w-3 h-3 ml-1" />
                </a>
              </div>
            )}
          </div>
        </div>

        {/* Right Side: GIANT 1-CLICK POWER ON / OFF BUTTON */}
        <div className="w-full md:w-auto shrink-0 flex flex-col sm:flex-row items-center gap-3">
          <button
            onClick={handleToggle}
            disabled={loading}
            className={`w-full sm:w-auto px-8 py-4 rounded-2xl text-base font-black tracking-wide uppercase transition-all transform active:scale-95 shadow-2xl flex items-center justify-center space-x-3 cursor-pointer ${
              isRunning
                ? 'bg-gradient-to-r from-rose-600 via-rose-500 to-pink-600 hover:from-rose-500 hover:to-pink-500 text-white shadow-rose-600/30 border border-rose-400/50'
                : 'bg-gradient-to-r from-emerald-600 via-emerald-500 to-teal-500 hover:from-emerald-500 hover:to-teal-400 text-white shadow-emerald-600/30 border border-emerald-400/50 animate-pulse'
            }`}
          >
            {loading ? (
              <>
                <Zap className="w-6 h-6 animate-spin" />
                <span>SWITCHING STATE...</span>
              </>
            ) : isRunning ? (
              <>
                <Pause className="w-6 h-6" />
                <span>TURN BOT OFF</span>
              </>
            ) : (
              <>
                <Play className="w-6 h-6 fill-current" />
                <span>TURN BOT ON</span>
              </>
            )}
          </button>
        </div>

      </div>
    </div>
  );
}
