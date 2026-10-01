'use client';

import React, { useState, useEffect } from 'react';
import Header from '@/components/Header';
import BotControlCard from '@/components/BotControlCard';
import ExecutiveMetrics from '@/components/ExecutiveMetrics';
import RecentChangesStream from '@/components/RecentChangesStream';
import EntityInspector from '@/components/EntityInspector';
import { EditRecord } from '@/app/api/edits/route';
import { Globe, ShieldCheck, Heart } from 'lucide-react';

export default function DashboardHome() {
  const [botStatus, setBotStatus] = useState<'RUNNING' | 'PAUSED' | 'RATE_LIMITED'>('PAUSED');
  const [requestDelay, setRequestDelay] = useState(0.8);

  const [stats, setStats] = useState({
    totalEditsToday: 0,
    totalEditsLifetime: 0,
    anomalyRate: 0.0,
    botStatus: 'PAUSED',
    sitelinkHitRate: 98.2,
    requestDelay: 1.0,
    verifiedCount: 0,
    flaggedCount: 0,
    currentQid: null as string | null,
    statusMessage: 'Engine on Standby',
    editsPerMinute: 0,
    queueDepth: 0,
    mode: 'RENDER',
    errorsInSession: 0,
    skippedInSession: 0,
  });

  const [edits, setEdits] = useState<EditRecord[]>([]);

  // Fetch live stats & recent changes feed from live Render URL
  const fetchData = async () => {
    try {
      const [statsRes, editsRes] = await Promise.all([
        fetch('/api/stats'),
        fetch('/api/edits')
      ]);

      const statsData = await statsRes.json();
      const editsData = await editsRes.json();

      if (statsData.success && statsData.stats) {
        setStats(statsData.stats);
        setBotStatus(statsData.stats.botStatus);
        setRequestDelay(statsData.stats.requestDelay || 0.8);
      }

      if (editsData.success && Array.isArray(editsData.edits)) {
        setEdits(editsData.edits);
      }
    } catch (e) {
      console.error('Data fetch error', e);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 2000);
    return () => clearInterval(interval);
  }, []);

  const handleRollbackComplete = (editId: string) => {
    setEdits((prev) =>
      prev.map((item) => (item.id === editId ? { ...item, reverted: true } : item))
    );
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-blue-600 selection:text-white">
      
      {/* Navbar Header */}
      <Header
        botStatus={botStatus}
        requestDelay={requestDelay}
        onStatusChange={(status) => setBotStatus(status)}
        onDelayChange={(delay) => setRequestDelay(delay)}
      />

      {/* Main Dashboard Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        
        {/* Giant 1-Click Bot ON / OFF Control Card */}
        <BotControlCard
          botStatus={botStatus}
          onStatusChange={(newStatus) => setBotStatus(newStatus)}
          statusMessage={stats.statusMessage}
          currentQid={stats.currentQid}
        />

        {/* Executive Metrics Overview */}
        <ExecutiveMetrics stats={stats} />

        {/* Live Recent Changes & Quality Audit Feed */}
        <RecentChangesStream
          edits={edits}
          onRollbackComplete={handleRollbackComplete}
        />

        {/* Single Entity Inspector (Dry-Run Simulator) */}
        <EntityInspector />

      </main>

      {/* Authentic Wikimedia Style Footer */}
      <footer className="border-t border-slate-900 bg-slate-950 py-8 text-center text-xs text-slate-500">
        <div className="max-w-7xl mx-auto px-4 flex flex-col md:flex-row items-center justify-between gap-4 font-mono">
          <div className="flex items-center space-x-2 text-slate-400">
            <Globe className="w-4 h-4 text-blue-400" />
            <span>Wikimedia Cloud Toolforge Operator • Bot: <strong>SHADOWARROW_2026</strong></span>
          </div>
          <div className="flex items-center space-x-4">
            <a
              href="https://www.wikidata.org/wiki/Wikidata:Bots"
              target="_blank"
              rel="noopener noreferrer"
              className="hover:text-blue-400 transition-colors flex items-center"
            >
              <ShieldCheck className="w-3.5 h-3.5 mr-1 text-emerald-400" /> Wikidata Bot Policy
            </a>
            <span>•</span>
            <span className="text-slate-400">Rate Limit: <strong>0.8s Safe Interval</strong></span>
          </div>
        </div>
      </footer>

    </div>
  );
}
