'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import * as api from '@/lib/api';

export default function DashboardPage() {
  const [sessions, setSessions] = useState<Record<string, unknown>[]>([]);
  const [analytics, setAnalytics] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<'sessions' | 'analytics'>('sessions');

  useEffect(() => {
    async function load() {
      try {
        const [sessData, analyticsData] = await Promise.all([
          api.getComplianceSessions(),
          api.getAnalytics(),
        ]);
        setSessions(sessData.sessions || []);
        setAnalytics(analyticsData);
      } catch (err) {
        console.error('Failed to load dashboard:', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  function StatusBadge({ status }: { status: string }) {
    const cls = status === 'completed' ? 'badge-pass' : status === 'active' ? 'badge-active' : status === 'declined' ? 'badge-fail' : 'badge-refer';
    return <span className={`badge ${cls}`}>{status}</span>;
  }

  function FraudBadge({ score, level }: { score: number; level: string }) {
    const cls = level === 'low' ? 'badge-low' : level === 'medium' ? 'badge-medium' : 'badge-high';
    return <span className={`badge ${cls}`}>Fraud: {score?.toFixed(0) ?? '—'}</span>;
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="spinner" />
      </div>
    );
  }

  return (
    <main className="min-h-screen p-6 max-w-7xl mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">
            Compliance Dashboard
          </h1>
          <p className="text-sm text-slate-400 mt-1">AgentFinance AI — Back Office</p>
        </div>
        <Link href="/" className="btn-secondary text-sm">
          ← Home
        </Link>
      </header>

      {/* Stats cards */}
      {analytics && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
          <div className="glass-card p-4 text-center">
            <div className="text-2xl font-bold text-indigo-400">{analytics.total_sessions as number}</div>
            <div className="text-xs text-slate-400 mt-1">Total Sessions</div>
          </div>
          <div className="glass-card p-4 text-center">
            <div className="text-2xl font-bold text-emerald-400">{analytics.completion_rate as number}%</div>
            <div className="text-xs text-slate-400 mt-1">Completion Rate</div>
          </div>
          <div className="glass-card p-4 text-center">
            <div className="text-2xl font-bold text-violet-400">{analytics.average_fraud_score as number}</div>
            <div className="text-xs text-slate-400 mt-1">Avg Fraud Score</div>
          </div>
          <div className="glass-card p-4 text-center">
            <div className="text-2xl font-bold text-amber-400">{analytics.acceptance_rate as number}%</div>
            <div className="text-xs text-slate-400 mt-1">Acceptance Rate</div>
          </div>
          <div className="glass-card p-4 text-center">
            <div className="text-2xl font-bold text-rose-400">
              {(analytics.consent_stats as Record<string, number>)?.granted ?? 0}
            </div>
            <div className="text-xs text-slate-400 mt-1">Consents</div>
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-2 mb-6">
        <button
          onClick={() => setTab('sessions')}
          className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
            tab === 'sessions' ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30' : 'text-slate-400 hover:text-white'
          }`}
        >
          Sessions ({sessions.length})
        </button>
        <button
          onClick={() => setTab('analytics')}
          className={`px-4 py-2 rounded-xl text-sm font-medium transition-all ${
            tab === 'analytics' ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30' : 'text-slate-400 hover:text-white'
          }`}
        >
          Analytics
        </button>
      </div>

      {/* Sessions tab */}
      {tab === 'sessions' && (
        <div className="glass-card overflow-hidden">
          {sessions.length === 0 ? (
            <div className="p-12 text-center text-slate-400">
              <div className="text-4xl mb-4">📋</div>
              <p>No sessions yet. Start a demo session from the home page.</p>
              <Link href="/" className="btn-primary inline-block mt-4 text-sm">Start Demo</Link>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Session ID</th>
                    <th>Applicant</th>
                    <th>Status</th>
                    <th>Fraud</th>
                    <th>Consent</th>
                    <th>Offer</th>
                    <th>Stage</th>
                    <th>Created</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {sessions.map((s) => (
                    <tr key={s.id as string}>
                      <td className="font-mono text-xs text-indigo-400">{(s.id as string)?.slice(0, 8)}...</td>
                      <td>{(s.applicant_name as string) || '—'}</td>
                      <td><StatusBadge status={s.status as string} /></td>
                      <td>
                        {s.fraud_score !== null && s.fraud_score !== undefined ? (
                          <FraudBadge score={s.fraud_score as number} level={s.fraud_risk_level as string} />
                        ) : '—'}
                      </td>
                      <td>
                        {s.is_consent !== null && s.is_consent !== undefined ? (
                          <span className={s.is_consent ? 'text-emerald-400' : 'text-rose-400'}>
                            {s.is_consent ? '✓' : '✗'}
                          </span>
                        ) : '—'}
                      </td>
                      <td>
                        {s.offer_amount ? (
                          <span className="text-amber-400">₹{((s.offer_amount as number) / 100000).toFixed(1)}L</span>
                        ) : '—'}
                      </td>
                      <td className="text-xs text-slate-500">{(s.pipeline_stage as string) || '—'}</td>
                      <td className="text-xs text-slate-500">
                        {s.created_at ? new Date(s.created_at as string).toLocaleString() : '—'}
                      </td>
                      <td>
                        <Link
                          href={`/dashboard/sessions/${s.id}`}
                          className="text-xs text-indigo-400 hover:text-indigo-300"
                        >
                          View →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Analytics tab */}
      {tab === 'analytics' && analytics && (
        <div className="grid md:grid-cols-2 gap-6">
          {/* Session Status Distribution */}
          <div className="glass-card p-6">
            <h3 className="text-sm font-semibold text-slate-300 mb-4">Session Status Distribution</h3>
            <div className="space-y-3">
              {Object.entries((analytics.session_status as Record<string, number>) || {}).map(([status, count]) => (
                <div key={status} className="flex items-center justify-between">
                  <StatusBadge status={status} />
                  <div className="flex items-center gap-3 flex-1 ml-4">
                    <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-indigo-500 rounded-full"
                        style={{ width: `${(count / (analytics.total_sessions as number || 1)) * 100}%` }}
                      />
                    </div>
                    <span className="text-sm text-slate-400 w-8 text-right">{count}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Fraud Distribution */}
          <div className="glass-card p-6">
            <h3 className="text-sm font-semibold text-slate-300 mb-4">Fraud Risk Distribution</h3>
            <div className="space-y-3">
              {Object.entries((analytics.fraud_distribution as Record<string, number>) || {}).map(([level, count]) => (
                <div key={level} className="flex items-center justify-between">
                  <span className={`badge badge-${level}`}>{level}</span>
                  <div className="flex items-center gap-3 flex-1 ml-4">
                    <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full rounded-full ${
                          level === 'low' ? 'bg-emerald-500' : level === 'medium' ? 'bg-amber-500' : 'bg-rose-500'
                        }`}
                        style={{ width: `${(count / (analytics.total_sessions as number || 1)) * 100}%` }}
                      />
                    </div>
                    <span className="text-sm text-slate-400 w-8 text-right">{count}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Pipeline Funnel */}
          <div className="glass-card p-6">
            <h3 className="text-sm font-semibold text-slate-300 mb-4">Pipeline Drop-off Funnel</h3>
            <div className="space-y-2">
              {Object.entries((analytics.pipeline_funnel as Record<string, number>) || {}).map(([stage, count]) => (
                <div key={stage} className="flex items-center gap-3 text-xs">
                  <span className="w-32 text-slate-400 truncate">{stage}</span>
                  <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                    <div className="h-full bg-violet-500 rounded-full" style={{ width: `${(count / (analytics.total_sessions as number || 1)) * 100}%` }} />
                  </div>
                  <span className="text-slate-400 w-6 text-right">{count}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Offer Stats */}
          <div className="glass-card p-6">
            <h3 className="text-sm font-semibold text-slate-300 mb-4">Offer Statistics</h3>
            <div className="space-y-3">
              {Object.entries((analytics.offer_stats as Record<string, number>) || {}).map(([status, count]) => (
                <div key={status} className="flex items-center justify-between">
                  <span className="text-sm text-slate-400 capitalize">{status}</span>
                  <span className="text-lg font-bold text-white">{count}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
