'use client';

import { useState, useEffect } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import * as api from '@/lib/api';

export default function SessionDetailPage() {
  const params = useParams();
  const sessionId = params.id as string;
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [report, setReport] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

  // Replay SSE state
  const [replayActive, setReplayActive] = useState(false);
  const [replayEvents, setReplayEvents] = useState<Array<Record<string, unknown>>>([]);
  const [replayDone, setReplayDone] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const detail = await api.getSessionDetail(sessionId);
        setData(detail);
      } catch (err) {
        console.error('Failed to load session:', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [sessionId]);

  async function handleExportReport() {
    try {
      const r = await api.getAuditReport(sessionId);
      setReport(r);
      // Download as JSON
      const blob = new Blob([JSON.stringify(r, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-report-${sessionId.slice(0, 8)}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert('Failed to generate report: ' + (err as Error).message);
    }
  }

  async function handleDownloadPdf() {
    try {
      await api.downloadAuditPdf(sessionId);
    } catch (err) {
      alert('PDF export failed: ' + (err as Error).message);
    }
  }

  function handleReplay() {
    if (replayActive) return;
    setReplayEvents([]);
    setReplayDone(false);
    setReplayActive(true);
    setActiveTab('audit');

    const es = api.createReplayEventSource(sessionId, 600);
    es.addEventListener('audit_event', (e: MessageEvent) => {
      try {
        const evt = JSON.parse(e.data) as Record<string, unknown>;
        setReplayEvents(prev => [...prev, evt]);
      } catch { /* ignore parse errors */ }
    });
    es.addEventListener('done', () => {
      setReplayDone(true);
      setReplayActive(false);
      es.close();
    });
    es.onerror = () => {
      setReplayActive(false);
      es.close();
    };
  }

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center"><div className="spinner" /></div>;
  }

  if (!data) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="glass-card p-8 text-center">
          <p className="text-slate-400">Session not found</p>
          <Link href="/dashboard" className="btn-primary mt-4 inline-block text-sm">Back</Link>
        </div>
      </div>
    );
  }

  const session = data.session as Record<string, unknown>;
  const transcript = data.transcript as { segments: Array<{text: string; created_at: string}>; full_text: string };
  const fields = data.extracted_fields as Array<{field_name: string; field_value: string; confidence: number}>;
  const consentRecords = data.consent as Array<Record<string, unknown>>;
  const visionResults = data.vision as Array<Record<string, unknown>>;
  const llm = data.llm_assessment as Record<string, unknown> | null;
  const fraud = data.fraud as Record<string, unknown> | null;
  const bureau = data.bureau as Record<string, unknown> | null;
  const offer = data.offer as Record<string, unknown> | null;
  const events = data.audit_events as Array<Record<string, unknown>>;
  const pipeline = data.pipeline as Record<string, unknown> | null;

  const tabs = ['overview', 'transcript', 'consent', 'vision', 'analysis', 'fraud', 'bureau', 'offer', 'audit'];

  return (
    <main className="min-h-screen p-6 max-w-7xl mx-auto">
      <header className="flex items-center justify-between mb-6">
        <div>
          <Link href="/dashboard" className="text-xs text-indigo-400 hover:text-indigo-300 mb-2 inline-block">
            ← Dashboard
          </Link>
          <h1 className="text-xl font-bold text-white">Session: {sessionId.slice(0, 8)}...</h1>
          <div className="flex items-center gap-3 mt-1">
            <span className={`badge badge-${session.status === 'completed' ? 'pass' : session.status === 'active' ? 'active' : 'fail'}`}>
              {session.status as string}
            </span>
            <span className="text-xs text-slate-500">{session.applicant_name as string}</span>
            <span className="text-xs text-slate-600">{session.created_at as string}</span>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleReplay}
            disabled={replayActive}
            className="btn-secondary text-sm"
            title="Replay all audit events in chronological order"
          >
            {replayActive ? '⏳ Replaying…' : '▶ Replay Session'}
          </button>
          <button onClick={handleDownloadPdf} className="btn-secondary text-sm">⬇ PDF</button>
          <button onClick={handleExportReport} className="btn-primary text-sm">Export JSON</button>
        </div>
      </header>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 overflow-x-auto pb-2">
        {tabs.map(t => (
          <button
            key={t}
            onClick={() => setActiveTab(t)}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all ${
              activeTab === t ? 'bg-indigo-500/20 text-indigo-400 border border-indigo-500/30' : 'text-slate-400 hover:text-white'
            }`}
          >
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {/* Overview */}
      {activeTab === 'overview' && (
        <div className="grid md:grid-cols-2 gap-6">
          <div className="glass-card p-6">
            <h3 className="font-semibold text-white mb-4">Session Info</h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between"><span className="text-slate-400">ID</span><span className="font-mono text-xs">{session.id as string}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Applicant</span><span>{session.applicant_name as string || '—'}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">IP</span><span>{session.ip_address as string || '—'}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Device</span><span className="text-xs truncate max-w-[200px]">{(session.device_fingerprint as string)?.slice(0, 20) || '—'}</span></div>
              <div className="flex justify-between"><span className="text-slate-400">Pipeline Stage</span><span>{(pipeline?.current_stage as string) || '—'}</span></div>
            </div>
          </div>
          <div className="glass-card p-6">
            <h3 className="font-semibold text-white mb-4">Quick Stats</h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="text-center p-3 rounded-xl bg-indigo-500/10">
                <div className="text-lg font-bold text-indigo-400">{transcript?.segments?.length || 0}</div>
                <div className="text-xs text-slate-400">Transcript Segs</div>
              </div>
              <div className="text-center p-3 rounded-xl bg-emerald-500/10">
                <div className="text-lg font-bold text-emerald-400">{visionResults?.length || 0}</div>
                <div className="text-xs text-slate-400">Vision Frames</div>
              </div>
              <div className="text-center p-3 rounded-xl bg-amber-500/10">
                <div className="text-lg font-bold text-amber-400">{(fraud?.composite_score as number)?.toFixed(0) ?? '—'}</div>
                <div className="text-xs text-slate-400">Fraud Score</div>
              </div>
              <div className="text-center p-3 rounded-xl bg-violet-500/10">
                <div className="text-lg font-bold text-violet-400">{events?.length || 0}</div>
                <div className="text-xs text-slate-400">Audit Events</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Transcript */}
      {activeTab === 'transcript' && (
        <div className="glass-card p-6">
          <h3 className="font-semibold text-white mb-4">Full Transcript</h3>
          {transcript?.segments?.length > 0 ? (
            <div className="space-y-2 max-h-[600px] overflow-y-auto">
              {transcript.segments.map((seg, i) => (
                <div key={i} className="p-3 rounded-lg bg-white/[0.03] text-sm">
                  <span className="text-xs text-slate-500 mr-2">#{i + 1}</span>
                  <span className="text-slate-300">{seg.text}</span>
                  <span className="text-xs text-slate-600 ml-2">{seg.created_at}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500">No transcript recorded</p>
          )}
        </div>
      )}

      {/* Consent */}
      {activeTab === 'consent' && (
        <div className="glass-card p-6">
          <h3 className="font-semibold text-white mb-4">Consent Trail</h3>
          {consentRecords?.length > 0 ? (
            <div className="space-y-4">
              {consentRecords.map((c, i) => (
                <div key={i} className={`p-4 rounded-xl border ${c.is_consent ? 'border-emerald-500/30 bg-emerald-500/5' : 'border-rose-500/30 bg-rose-500/5'}`}>
                  <div className="flex items-center gap-2 mb-2">
                    <span className={c.is_consent ? 'text-emerald-400' : 'text-rose-400'}>
                      {c.is_consent ? '✓ Consent Granted' : '✗ Opt-Out'}
                    </span>
                    <span className="text-xs text-slate-500">{c.timestamp as string}</span>
                  </div>
                  <p className="text-sm text-slate-300">Phrase: "{c.phrase_detected as string}"</p>
                  <p className="text-xs text-slate-500 font-mono mt-1">Hash: {(c.segment_hash as string)?.slice(0, 32)}...</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-slate-500">No consent records</p>
          )}
        </div>
      )}

      {/* Vision */}
      {activeTab === 'vision' && (
        <div className="glass-card p-6">
          <h3 className="font-semibold text-white mb-4">Liveness & Age Detection</h3>
          {visionResults?.length > 0 ? (
            <div className="space-y-2">
              <div className="grid grid-cols-4 gap-4 mb-4">
                <div className="text-center p-3 rounded-xl bg-emerald-500/10">
                  <div className="text-lg font-bold text-emerald-400">
                    {visionResults.filter(v => v.is_live).length}/{visionResults.length}
                  </div>
                  <div className="text-xs text-slate-400">Live Frames</div>
                </div>
                <div className="text-center p-3 rounded-xl bg-indigo-500/10">
                  <div className="text-lg font-bold text-indigo-400">
                    {(visionResults.reduce((s, v) => s + (v.liveness_score as number || 0), 0) / visionResults.length * 100).toFixed(0)}%
                  </div>
                  <div className="text-xs text-slate-400">Avg Liveness</div>
                </div>
              </div>
              <div className="overflow-x-auto">
                <table className="data-table text-xs">
                  <thead>
                    <tr><th>#</th><th>Live</th><th>Score</th><th>Age</th><th>Blink</th><th>Texture</th></tr>
                  </thead>
                  <tbody>
                    {visionResults.slice(0, 20).map((v, i) => (
                      <tr key={i}>
                        <td>{v.frame_index as number}</td>
                        <td className={v.is_live ? 'text-emerald-400' : 'text-rose-400'}>{v.is_live ? '✓' : '✗'}</td>
                        <td>{((v.liveness_score as number) * 100).toFixed(0)}%</td>
                        <td>{v.estimated_age as number || '—'}</td>
                        <td>{v.blink_detected ? '✓' : '—'}</td>
                        <td>{(v.texture_score as number)?.toFixed(0) || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p className="text-slate-500">No vision data</p>
          )}
        </div>
      )}

      {/* LLM Analysis */}
      {activeTab === 'analysis' && (
        <div className="glass-card p-6">
          <h3 className="font-semibold text-white mb-4">LLM Assessment</h3>
          {llm ? (
            <div className="space-y-4">
              <div className="grid md:grid-cols-2 gap-4">
                <div className="p-4 rounded-xl bg-indigo-500/10">
                  <div className="text-xs text-slate-400 mb-1">Intent Category</div>
                  <div className="text-lg font-bold text-indigo-400 capitalize">{(llm.intent_category as string)?.replace(/_/g, ' ')}</div>
                  <div className="text-xs text-slate-500">Confidence: {((llm.intent_confidence as number || 0) * 100).toFixed(0)}%</div>
                </div>
                <div className="p-4 rounded-xl bg-violet-500/10">
                  <div className="text-xs text-slate-400 mb-1">Risk Persona</div>
                  <div className="text-lg font-bold text-violet-400 capitalize">{(llm.risk_persona as string)?.replace(/_/g, ' ')}</div>
                  <div className="text-xs text-slate-500">Confidence: {((llm.risk_confidence as number || 0) * 100).toFixed(0)}%</div>
                </div>
              </div>
              <div>
                <h4 className="text-sm font-semibold text-slate-300 mb-2">Chain-of-Thought Reasoning</h4>
                <div className="space-y-1">
                  {(llm.reasoning_trace as string[])?.map((step, i) => (
                    <div key={i} className="text-sm text-slate-400 p-2 rounded bg-white/[0.03]">{step}</div>
                  ))}
                </div>
              </div>
              {(llm.contradictions as unknown[])?.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-rose-400 mb-2">Contradictions Detected</h4>
                  {(llm.contradictions as Array<{description: string; severity: string}>).map((c, i) => (
                    <div key={i} className="p-2 rounded bg-rose-500/10 text-sm text-rose-300 mb-1">
                      {c.description} <span className="badge badge-fail text-[10px]">{c.severity}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="text-slate-500">No LLM assessment</p>
          )}
        </div>
      )}

      {/* Fraud */}
      {activeTab === 'fraud' && (
        <div className="glass-card p-6">
          <h3 className="font-semibold text-white mb-4">Fraud Signal Breakdown</h3>
          {fraud ? (
            <div className="space-y-4">
              <div className="flex items-center gap-4 mb-6">
                <div className={`text-4xl font-bold ${
                  (fraud.risk_level as string) === 'low' ? 'text-emerald-400' :
                  (fraud.risk_level as string) === 'medium' ? 'text-amber-400' : 'text-rose-400'
                }`}>
                  {(fraud.composite_score as number)?.toFixed(1)}
                </div>
                <div>
                  <span className={`badge badge-${fraud.risk_level}`}>{fraud.risk_level as string}</span>
                  <div className="text-xs text-slate-500 mt-1">Composite Score (0-100)</div>
                </div>
              </div>
              <div className="space-y-3">
                {Object.entries((fraud.signal_breakdown as Record<string, {score: number; detail: string}>) || {}).map(([signal, info]) => (
                  <div key={signal} className="p-3 rounded-xl bg-white/[0.03]">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-slate-300 capitalize">{signal.replace(/_/g, ' ')}</span>
                      <span className={`text-sm font-bold ${info.score <= 20 ? 'text-emerald-400' : info.score <= 50 ? 'text-amber-400' : 'text-rose-400'}`}>
                        {info.score}
                      </span>
                    </div>
                    <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden mb-1">
                      <div className={`h-full rounded-full ${info.score <= 20 ? 'bg-emerald-500' : info.score <= 50 ? 'bg-amber-500' : 'bg-rose-500'}`} style={{ width: `${info.score}%` }} />
                    </div>
                    <p className="text-xs text-slate-500">{info.detail}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <p className="text-slate-500">No fraud scoring data</p>
          )}
        </div>
      )}

      {/* Bureau */}
      {activeTab === 'bureau' && (
        <div className="glass-card p-6">
          <h3 className="font-semibold text-white mb-4">Bureau & Policy Decision</h3>
          {bureau ? (
            <div className="space-y-4">
              <div className="grid grid-cols-3 gap-4">
                <div className="text-center p-3 rounded-xl bg-indigo-500/10">
                  <div className="text-2xl font-bold text-indigo-400">{bureau.credit_score as number}</div>
                  <div className="text-xs text-slate-400">Credit Score</div>
                </div>
                <div className="text-center p-3 rounded-xl bg-violet-500/10">
                  <div className="text-2xl font-bold text-violet-400">{bureau.active_loans as number}</div>
                  <div className="text-xs text-slate-400">Active Loans</div>
                </div>
                <div className="text-center p-3 rounded-xl">
                  <span className={`badge badge-${bureau.policy_decision === 'pass' ? 'pass' : bureau.policy_decision === 'fail' ? 'fail' : 'refer'} text-lg`}>
                    {bureau.policy_decision as string}
                  </span>
                  <div className="text-xs text-slate-400 mt-1">Decision</div>
                </div>
              </div>
              {(bureau.rule_evaluations as Array<{rule: string; passed: boolean; explanation: string}>)?.length > 0 && (
                <div>
                  <h4 className="text-sm font-semibold text-slate-300 mb-2">Rule Evaluations</h4>
                  {(bureau.rule_evaluations as Array<{rule: string; passed: boolean; explanation: string}>).map((r, i) => (
                    <div key={i} className="flex items-center gap-2 p-2 text-sm border-b border-white/5">
                      <span className={r.passed ? 'text-emerald-400' : 'text-rose-400'}>{r.passed ? '✓' : '✗'}</span>
                      <span className="text-slate-300">{r.explanation}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <p className="text-slate-500">No bureau data</p>
          )}
        </div>
      )}

      {/* Offer */}
      {activeTab === 'offer' && (
        <div className="glass-card p-6">
          <h3 className="font-semibold text-white mb-4">Loan Offer</h3>
          {offer ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                <div className="text-center p-3 rounded-xl bg-indigo-500/10">
                  <div className="text-xl font-bold text-indigo-400">₹{((offer.eligible_amount as number) / 100000).toFixed(1)}L</div>
                  <div className="text-xs text-slate-400">Amount</div>
                </div>
                <div className="text-center p-3 rounded-xl bg-violet-500/10">
                  <div className="text-xl font-bold text-violet-400">{offer.interest_rate as number}%</div>
                  <div className="text-xs text-slate-400">Rate</div>
                </div>
                <div className="text-center p-3 rounded-xl bg-emerald-500/10">
                  <div className="text-xl font-bold text-emerald-400">{offer.tenure_months as number}mo</div>
                  <div className="text-xs text-slate-400">Tenure</div>
                </div>
                <div className="text-center p-3 rounded-xl bg-amber-500/10">
                  <div className="text-xl font-bold text-amber-400">₹{Math.round(offer.emi_amount as number || 0).toLocaleString()}</div>
                  <div className="text-xs text-slate-400">EMI</div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`badge badge-${offer.status === 'accepted' ? 'pass' : offer.status === 'declined' ? 'fail' : 'active'}`}>
                  {offer.status as string}
                </span>
                <span className="text-xs text-slate-500">Rounds: {offer.negotiation_rounds as number}</span>
                {Boolean(offer.accepted_at) && <span className="text-xs text-slate-500">Accepted: {String(offer.accepted_at)}</span>}
              </div>
            </div>
          ) : (
            <p className="text-slate-500">No offer generated</p>
          )}
        </div>
      )}

      {/* Audit Events */}
      {activeTab === 'audit' && (
        <div className="space-y-4">
          {/* Live Replay Stream */}
          {(replayActive || replayDone) && (
            <div className="glass-card p-4 border border-indigo-500/30">
              <div className="flex items-center gap-2 mb-3">
                <span className={`w-2 h-2 rounded-full ${replayActive ? 'bg-indigo-400 animate-pulse' : 'bg-emerald-400'}`} />
                <span className="text-sm font-semibold text-white">
                  {replayActive ? 'Live Replay…' : `Replay Complete — ${replayEvents.length} events`}
                </span>
              </div>
              <div className="space-y-1 max-h-[300px] overflow-y-auto">
                {replayEvents.map((e, i) => (
                  <div key={i} className="flex items-start gap-3 p-2 rounded text-xs bg-indigo-500/5 animate-pulse-once">
                    <span className="text-indigo-400 w-40 font-mono">{e.event_type as string}</span>
                    <span className="text-slate-500 w-20">{e.module as string}</span>
                    <span className="text-slate-400 flex-1 truncate">{JSON.stringify(e.data)}</span>
                    <span className="text-slate-600 w-20">{(e.timestamp as string)?.slice(11, 19)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          <div className="glass-card p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-white">Full Audit Event Trail ({events?.length || 0} events)</h3>
              <button onClick={handleExportReport} className="btn-secondary text-xs">Download JSON</button>
            </div>
            {events?.length > 0 ? (
              <div className="space-y-1 max-h-[600px] overflow-y-auto">
                {events.map((e, i) => (
                  <div key={i} className="flex items-start gap-3 p-2 rounded text-xs hover:bg-white/[0.03]">
                    <span className="text-slate-600 w-8">{i + 1}</span>
                    <span className="text-indigo-400 w-40 font-mono">{e.event_type as string}</span>
                    <span className="text-slate-500 w-24">{e.module as string}</span>
                    <span className="text-slate-400 flex-1 truncate">{JSON.stringify(e.data)}</span>
                    <span className="text-slate-600 w-20">{(e.timestamp as string)?.slice(11, 19)}</span>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-slate-500">No audit events</p>
            )}
          </div>
        </div>
      )}

      {/* Exported Report */}
      {report && (
        <div className="glass-card p-6 mt-6 border border-emerald-500/30">
          <h3 className="font-semibold text-emerald-400 mb-2">✓ Audit Report Generated & Downloaded</h3>
          <p className="text-xs text-slate-500 font-mono">Report Hash: {(report.report_hash as string)?.slice(0, 32)}...</p>
        </div>
      )}
    </main>
  );
}
