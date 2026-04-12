'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import * as api from '@/lib/api';
import Sidebar from '@/components/Sidebar';
import Topbar from '@/components/Topbar';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { ArrowLeft, Download, ShieldCheck, ShieldAlert, FileText, CheckCircle2 } from 'lucide-react';
import { GoldButton } from '@/components/ui/GoldButton';

export default function SessionDetailPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('overview');

  useEffect(() => {
    async function load() {
      try {
        const detail = await api.getSessionDetail(sessionId);
        setData(detail);
      } catch (err) {} finally {
        setLoading(false);
      }
    }
    load();
  }, [sessionId]);

  if (loading) return <div className="min-h-screen bg-[#0B0B0C] flex items-center justify-center"><span className="spinner w-8 h-8" /></div>;
  if (!data) return <div className="min-h-screen bg-[#0B0B0C] flex items-center justify-center text-[#71717A]">Session not found</div>;

  const session = data.session as any;
  const transcript = data.transcript as any;
  const vision = data.vision as any[];
  const llm = data.llm_assessment as any;
  const fraud = data.fraud as any;
  const offer = data.offer as any;
  const events = data.audit_events as any[];

  return (
    <>
      <Sidebar activePage="dashboard" />
      <Topbar sessionId={sessionId} currentStage={data.pipeline ? (data.pipeline as any).current_stage : ''} />

      <main className="min-h-screen bg-[#0B0B0C] pt-20 pl-16">
        <div className="max-w-7xl mx-auto p-6 md:p-8">
          
          <button onClick={() => router.push('/dashboard')} className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-[#A1A1AA] hover:text-[#D6B36A] transition-colors mb-6">
            <ArrowLeft className="w-4 h-4" /> Back to Dashboard
          </button>

          <div className="flex flex-col md:flex-row md:items-end justify-between mb-8 gap-4">
            <div>
              <SectionHeader title={session.applicant_name || 'Unknown Applicant'} description="Full Audit capabilities and AI trace logs." />
              <div className="flex flex-wrap gap-2 mt-4">
                <StatusBadge status={session.status === 'completed' ? 'success' : session.status === 'active' ? 'active' : 'error'} label={session.status} />
                <span className="px-3 py-1 rounded-md bg-[#161618] border border-white/5 text-xs text-[#71717A] tracking-wider font-mono">ID: {sessionId}</span>
              </div>
            </div>
            
            <div className="flex gap-2">
              <GoldButton variant="outline" onClick={() => router.push(`/dashboard/sessions/${sessionId}/explain`)}>
                View AI Explainability
              </GoldButton>
              <GoldButton variant="outline" className="gap-2">
                <Download className="w-4 h-4" /> Export Complete Audit PDF
              </GoldButton>
            </div>
          </div>

          <div className="flex gap-1 mb-8 overflow-x-auto pb-2 border-b border-white/5">
            {['overview', 'transcript', 'vision', 'analysis', 'audit'].map((t, index) => (
              <button
                key={`${t}-${index}`}
                onClick={() => setActiveTab(t)}
                className={`px-4 py-2.5 rounded-t-lg text-xs font-bold uppercase tracking-widest whitespace-nowrap transition-colors border-b-2 ${activeTab === t ? 'bg-[#161618] text-[#EAEAEA] border-[#D6B36A]' : 'text-[#71717A] border-transparent hover:text-[#A1A1AA]'}`}
              >
                {t}
              </button>
            ))}
          </div>

          {activeTab === 'overview' && (
            <div className="grid md:grid-cols-3 gap-6">
              {/* Summary Cards */}
              <div className="surface-1 p-6 flex flex-col gap-6 md:col-span-2">
                <h3 className="text-sm font-bold text-[#EAEAEA]">Credit Offer Resolution</h3>
                {offer ? (
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
                     <div className="bg-[#0B0B0C] border border-white/5 p-4 rounded-xl">
                       <p className="text-[10px] text-[#A1A1AA] uppercase font-bold tracking-widest mb-1">Eligible Amt</p>
                       <p className="text-2xl font-bold text-[#D6B36A]">₹{(offer.eligible_amount / 100000).toFixed(1)}L</p>
                     </div>
                     <div className="bg-[#0B0B0C] border border-white/5 p-4 rounded-xl">
                       <p className="text-[10px] text-[#A1A1AA] uppercase font-bold tracking-widest mb-1">Interest</p>
                       <p className="text-2xl font-bold text-[#EAEAEA]">{offer.interest_rate}%</p>
                     </div>
                     <div className="bg-[#0B0B0C] border border-white/5 p-4 rounded-xl">
                       <p className="text-[10px] text-[#A1A1AA] uppercase font-bold tracking-widest mb-1">Tenure</p>
                       <p className="text-2xl font-bold text-[#EAEAEA]">{offer.default_tenure_months}mo</p>
                     </div>
                     <div className="bg-[#0B0B0C] border border-white/5 p-4 rounded-xl">
                       <p className="text-[10px] text-[#A1A1AA] uppercase font-bold tracking-widest mb-1">Status</p>
                       <p className={`text-lg mt-1 font-bold ${offer.status === 'accepted' ? 'text-[#22C55E]' : 'text-[#EF4444]'}`}>{offer.status.toUpperCase()}</p>
                     </div>
                  </div>
                ) : <span className="text-[#71717A] text-sm">No offer generated yet.</span>}

                <div className="h-px bg-white/5 my-2" />

                <h3 className="text-sm font-bold text-[#EAEAEA]">Fraud Overview</h3>
                {fraud ? (
                  <div className="flex items-center gap-6">
                    <div className="w-24 h-24 rounded-full border-[6px] flex items-center justify-center flex-col shrink-0" 
                      style={{ borderColor: fraud.risk_level === 'high' ? '#EF4444' : fraud.risk_level === 'medium' ? '#F59E0B' : '#22C55E' }}>
                      <span className="text-2xl font-bold text-[#EAEAEA]">{fraud.composite_score.toFixed(0)}</span>
                      <span className="text-[10px] uppercase tracking-widest text-[#A1A1AA]">Score</span>
                    </div>
                    <div className="space-y-2 flex-1">
                      {Object.entries(fraud.signal_breakdown || {}).slice(0,3).map(([key, info]: any, index) => (
                        <div key={`${key}-${index}`} className="flex justify-between items-center bg-[#0B0B0C] border border-white/5 px-4 py-2 rounded-lg">
                          <span className="text-xs text-[#A1A1AA] font-medium tracking-wide capitalize">{key.replace(/_/g, ' ')}</span>
                          <span className={`text-xs font-bold ${info.score > 60 ? 'text-[#EF4444]' : 'text-[#22C55E]'}`}>{info.score}/100</span>
                        </div>
                      ))}
                    </div>
                  </div>
                ) : <span className="text-[#71717A] text-sm">No fraud data assessed.</span>}
              </div>

              {/* Timeline sidebar */}
              <div className="surface-1 p-6 relative">
                 <h3 className="text-sm font-bold text-[#EAEAEA] mb-6">Device & Network</h3>
                 <div className="space-y-4 font-mono text-xs">
                    <div className="flex flex-col gap-1">
                       <span className="text-[#71717A]">IP Address</span>
                       <span className="text-[#EAEAEA]">{session.ip_address || '—'}</span>
                    </div>
                    <div className="flex flex-col gap-1">
                       <span className="text-[#71717A]">Fingerprint</span>
                       <span className="text-[#D6B36A] break-all">{session.device_fingerprint || '—'}</span>
                    </div>
                    <div className="flex flex-col gap-1 pt-4 border-t border-white/5">
                       <span className="text-[#71717A]">Creation Time</span>
                       <span className="text-[#EAEAEA]">{new Date(session.created_at).toLocaleString()}</span>
                    </div>
                 </div>
              </div>
            </div>
          )}

          {activeTab === 'transcript' && (
             <div className="surface-1 p-6">
                <h3 className="text-sm font-bold text-[#EAEAEA] mb-6">Conversation Log</h3>
                <div className="space-y-4 max-h-[600px] overflow-auto pr-4">
                  {transcript?.segments?.map((seg: any, i: number) => (
                    <div key={i} className="flex flex-col bg-[#0B0B0C] border border-white/5 rounded-xl p-4">
                      <p className="text-sm text-[#EAEAEA] leading-relaxed mb-2">{seg.text}</p>
                      <span className="text-[10px] font-mono text-[#71717A]">{seg.created_at}</span>
                    </div>
                  ))}
                  {(!transcript?.segments || transcript.segments.length === 0) && (
                    <span className="text-[#71717A] text-sm">No transcript captured.</span>
                  )}
                </div>
             </div>
          )}

          {activeTab === 'audit' && (
             <div className="surface-1 p-6">
                <h3 className="text-sm font-bold text-[#EAEAEA] mb-6">Complete Audit Trail</h3>
                <div className="space-y-2">
                  {events?.map((e, i) => (
                    <div key={i} className="flex gap-4 items-center bg-[#0B0B0C] border border-white/5 rounded-lg px-4 py-3">
                      <span className="text-[10px] font-mono text-[#D6B36A] w-16 shrinks-0">{e.event_type}</span>
                      <span className="text-[11px] font-mono text-[#71717A] w-24 shrink-0 px-2 border-l border-white/5">{e.stage}</span>
                      <span className="text-[11px] text-[#A1A1AA] flex-1 truncate font-mono">{JSON.stringify(e.data)}</span>
                      <span className="text-[10px] font-mono text-[#71717A] shrink-0">{e.timestamp.slice(11, 19)}</span>
                    </div>
                  ))}
                </div>
             </div>
          )}

          {activeTab === 'analysis' && (
             <div className="grid md:grid-cols-2 gap-6">
                <div className="surface-1 p-6">
                   <h3 className="text-sm font-bold text-[#EAEAEA] mb-6 flex items-center gap-2"><FileText className="w-4 h-4 text-[#D6B36A]"/> NLP Semantic Extraction</h3>
                   {llm ? (
                     <div className="space-y-6">
                        <div>
                          <span className="text-[10px] text-[#71717A] uppercase font-bold tracking-widest block mb-2">Primary Intent</span>
                          <span className="text-xl font-bold capitalize text-[#EAEAEA]">{llm.intent_category.replace(/_/g, ' ')}</span>
                          <span className="text-xs text-[#22C55E] ml-3">{(llm.intent_confidence * 100).toFixed(0)}% Confidence</span>
                        </div>
                        <div>
                          <span className="text-[10px] text-[#71717A] uppercase font-bold tracking-widest block mb-2">Classified Risk Persona</span>
                          <span className="text-xl font-bold capitalize text-[#F59E0B]">{llm.risk_persona.replace(/_/g, ' ')}</span>
                        </div>
                        <div className="pt-4 border-t border-white/5">
                           <span className="text-[10px] text-[#71717A] uppercase font-bold tracking-widest block mb-3">Reasoning Trace</span>
                           <div className="space-y-2">
                             {llm.reasoning_trace?.map((t: string, i: number) => (
                               <div key={i} className="text-xs text-[#A1A1AA] bg-[#0B0B0C] p-3 rounded-lg border border-white/5">{t}</div>
                             ))}
                           </div>
                        </div>
                     </div>
                   ) : <span className="text-[#71717A] text-sm">No analysis performed</span>}
                </div>
             </div>
          )}

          {activeTab === 'vision' && (
             <div className="surface-1 p-6">
                <h3 className="text-sm font-bold text-[#EAEAEA] mb-6 flex items-center gap-2"><ShieldCheck className="w-4 h-4 text-[#D6B36A]"/> Security Vision Checks</h3>
                {vision?.length > 0 ? (
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                     {vision.slice(0,10).map((v, i) => (
                       <div key={i} className="bg-[#0B0B0C] border border-white/5 p-4 rounded-xl flex flex-col items-center justify-center gap-2 text-center">
                         <span className="text-[10px] font-mono text-[#D6B36A]">FRAME {v.frame_index}</span>
                         {v.is_live ? <CheckCircle2 className="w-6 h-6 text-[#22C55E]" /> : <ShieldAlert className="w-6 h-6 text-[#EF4444]" />}
                         <div className="text-xs font-bold text-[#EAEAEA]">{(v.liveness_score * 100).toFixed(0)}% Live</div>
                       </div>
                     ))}
                  </div>
                ) : <span className="text-[#71717A] text-sm">No frames captured.</span>}
             </div>
          )}

        </div>
      </main>
    </>
  );
}
