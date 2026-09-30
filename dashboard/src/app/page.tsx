'use client';

import React, { useState, useEffect } from 'react';
import Header from '@/components/Header';
import ExecutiveMetrics from '@/components/ExecutiveMetrics';
import RecentChangesStream from '@/components/RecentChangesStream';
import EntityInspector from '@/components/EntityInspector';
import { EditRecord } from '@/app/api/edits/route';

export default function DashboardHome() {
  const [botStatus, setBotStatus] = useState<'RUNNING' | 'PAUSED' | 'RATE_LIMITED'>('RUNNING');
  const [requestDelay, setRequestDelay] = useState(1.8);

  const [stats, setStats] = useState({
    totalEditsToday: 142,
    totalEditsLifetime: 1284,
    anomalyRate: 0.0,
    botStatus: 'RUNNING',
    sitelinkHitRate: 96.4,
    requestDelay: 1.8,
    verifiedCount: 1284,
    flaggedCount: 0
  });

  const [edits, setEdits] = useState<EditRecord[]>([]);

  // Fetch live stats & recent changes feed
  const fetchData = async () => {
    try {
      const [statsRes, editsRes] = await Promise.all([
        fetch('/api/stats'),
        fetch('/api/edits')
      ]);

      const statsData = await statsRes.json();
      const editsData = await editsRes.json();

      if (statsData.success) {
        setStats(statsData.stats);
        setBotStatus(statsData.stats.botStatus);
        setRequestDelay(statsData.stats.requestDelay);
      }

      if (editsData.success) {
        setEdits(editsData.edits);
      }
    } catch (e) {
      console.error('Data fetch error', e);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3500);
    return () => clearInterval(interval);
  }, []);

  const handleRollbackComplete = (editId: string) => {
    setEdits((prev) =>
      prev.map((item) => (item.id === editId ? { ...item, reverted: true } : item))
    );
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans selection:bg-indigo-500 selection:text-white">
      
      {/* Navbar Header */}
      <Header
        botStatus={botStatus}
        requestDelay={requestDelay}
        onStatusChange={(status) => setBotStatus(status)}
        onDelayChange={(delay) => setRequestDelay(delay)}
      />

      {/* Main Dashboard Container */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        
        {/* Executive Metrics Overview */}
        <ExecutiveMetrics stats={stats} />

        {/* Live Recent Changes & Quality Audit Feed (Hero Feature) */}
        <RecentChangesStream
          edits={edits}
          onRollbackComplete={handleRollbackComplete}
        />

        {/* Single Entity Inspector (Dry-Run Simulator) */}
        <EntityInspector />

      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-slate-950 py-6 text-center text-xs text-slate-500">
        <p>Wikidata Automation Engine v2.0 • Sitelink-Only Verified Architecture • 100% Policy Compliant</p>
      </footer>

    </div>
  );
}
