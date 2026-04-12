'use client';

import { useParams, useRouter } from 'next/navigation';
import Sidebar from '@/components/Sidebar';
import Topbar from '@/components/Topbar';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { ArrowLeft, Brain, Target, ShieldAlert } from 'lucide-react';
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Cell } from 'recharts';

export default function ExplainabilityPage() {
  const params = useParams();
  const router = useRouter();
  const sessionId = params.id as string;

  const featureImportance = [
    { name: 'Income Verified', value: 85 },
    { name: 'Fraud Score', value: -40 },
    { name: 'Liveness Match', value: 95 },
    { name: 'Credit Utilization', value: -15 },
    { name: 'Lending History', value: 65 }
  ];

  return (
    <>
      <Sidebar activePage="dashboard" />
      <Topbar sessionId={sessionId} currentStage="AUDIT_EXPLAIN" />

      <main className="min-h-screen bg-[#0B0B0C] pt-20 pl-16">
        <div className="max-w-5xl mx-auto p-6 md:p-8">
          
          <button onClick={() => router.push(`/dashboard/sessions/${sessionId}`)} className="flex items-center gap-2 text-xs font-semibold uppercase tracking-widest text-[#A1A1AA] hover:text-[#D6B36A] transition-colors mb-6">
            <ArrowLeft className="w-4 h-4" /> Back to Case Detail
          </button>

          <SectionHeader 
            title="AI Model Explainability" 
            description="Deconstructing the autonomous neural evaluation and deterministic rule engine." 
            className="mb-8"
          />

          <div className="grid md:grid-cols-2 gap-6">
             <div className="surface-1 p-6">
               <div className="flex items-center gap-3 mb-6 border-b border-white/5 pb-4">
                 <Target className="w-5 h-5 text-[#D6B36A]" />
                 <h3 className="font-bold text-[#EAEAEA]">Feature Importance Vector</h3>
               </div>
               
               <div className="h-64">
                 <ResponsiveContainer width="100%" height="100%">
                   <BarChart data={featureImportance} layout="vertical" margin={{ left: 40, right: 20 }}>
                     <XAxis type="number" stroke="#3F3F46" tick={{ fill: '#71717A', fontSize: 10 }} />
                     <YAxis dataKey="name" type="category" stroke="#3F3F46" tick={{ fill: '#EAEAEA', fontSize: 11 }} width={120} />
                     <Tooltip 
                       cursor={{ fill: '#161618' }}
                       contentStyle={{ background: '#161618', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#A1A1AA' }}
                     />
                     <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={20}>
                       {featureImportance.map((entry, index) => (
                         <Cell key={`cell-${index}`} fill={entry.value > 0 ? '#22C55E' : '#EF4444'} />
                       ))}
                     </Bar>
                   </BarChart>
                 </ResponsiveContainer>
               </div>
             </div>

             <div className="flex flex-col gap-6">
               <div className="surface-1 p-6">
                 <div className="flex items-center gap-3 mb-6 border-b border-white/5 pb-4">
                   <Brain className="w-5 h-5 text-[#D6B36A]" />
                   <h3 className="font-bold text-[#EAEAEA]">LLM Deduction Nodes</h3>
                 </div>
                 
                 <div className="space-y-4">
                    <div className="bg-[#0B0B0C] border border-white/5 p-4 rounded-xl">
                      <span className="text-[10px] uppercase font-bold tracking-widest text-[#71717A] mb-1 block">Vector Match 1</span>
                      <p className="text-sm text-[#EAEAEA]">Voice input matched verified identity dataset with 98.2% semantic similarity.</p>
                    </div>
                    <div className="bg-[#0B0B0C] border border-white/5 p-4 rounded-xl border-l-[3px] border-l-[#EF4444]">
                      <span className="text-[10px] uppercase font-bold tracking-widest text-[#EF4444] mb-1 block">Risk Flag</span>
                      <p className="text-sm text-[#EAEAEA]">Stated income deviates from inferred geographic average by 2.4 sigma. Requiring multi-layer verification.</p>
                    </div>
                 </div>
               </div>
               
               <div className="surface-1 p-6 border border-[#D6B36A]/20 bg-[#D6B36A]/5">
                 <div className="flex items-center gap-3 mb-2">
                   <ShieldAlert className="w-5 h-5 text-[#D6B36A]" />
                   <h3 className="font-bold text-[#D6B36A]">Deterministic Fallback</h3>
                 </div>
                 <p className="text-sm text-[#EAEAEA]/80">System guarantees that no loan is disbursed solely on LLM logic. Generative outputs are constrained by hardcoded Bureau Policy constraints before final authorization.</p>
               </div>
             </div>
          </div>
        </div>
      </main>
    </>
  );
}
