'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import * as api from '@/lib/api';
import Sidebar from '@/components/Sidebar';
import Topbar from '@/components/Topbar';
import { KPICard } from '@/components/ui/KPICard';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { GoldButton } from '@/components/ui/GoldButton';
import { Search, Filter, Activity, CheckCircle, ShieldAlert, Users } from 'lucide-react';
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, Tooltip as RechartsTooltip, ResponsiveContainer, Cell } from 'recharts';

export default function DashboardPage() {
  const router = useRouter();
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

  const ChartTooltip = ({ active, payload, label }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-[#161618] border border-white/10 p-3 rounded-lg shadow-xl">
          <p className="text-xs text-[#A1A1AA] mb-1">{label}</p>
          <p className="font-bold text-[#EAEAEA]">{payload[0].value}</p>
        </div>
      );
    }
    return null;
  };

  const fraudData = analytics ? Object.entries(analytics.fraud_distribution as Record<string, number> || {}).map(([name, value]) => ({ name: name.toUpperCase(), value })) : [];
  const funnelData = analytics ? Object.entries(analytics.pipeline_funnel as Record<string, number> || {}).map(([name, value]) => ({ name: name.split('_')[0], value })) : [];

  if (loading) {
    return (
      <div className="min-h-screen bg-[#0B0B0C] flex items-center justify-center">
        <span className="spinner border-t-[#D6B36A] border-2 border-white/10 w-8 h-8" />
      </div>
    );
  }

  return (
    <>
      <Sidebar activePage="dashboard" />
      <Topbar />

      <main className="min-h-screen bg-[#0B0B0C] pt-20 pl-16">
        <div className="max-w-7xl mx-auto p-6 md:p-8">
          
          <div className="flex justify-between items-end mb-8">
            <SectionHeader 
              title="System Intelligence Dashboard" 
              description="Global metrics, active sessions, and multi-agent operations trace." 
            />
            <div className="flex gap-2">
              <button 
                className={`text-xs font-semibold px-4 py-2 uppercase tracking-wide rounded-md transition-colors ${tab === 'sessions' ? 'bg-[#D6B36A]/10 text-[#D6B36A]' : 'text-[#71717A] hover:text-[#A1A1AA]'}`}
                onClick={() => setTab('sessions')}
              >
                Data Grid
              </button>
              <button 
                className={`text-xs font-semibold px-4 py-2 uppercase tracking-wide rounded-md transition-colors ${tab === 'analytics' ? 'bg-[#D6B36A]/10 text-[#D6B36A]' : 'text-[#71717A] hover:text-[#A1A1AA]'}`}
                onClick={() => setTab('analytics')}
              >
                Analytics
              </button>
            </div>
          </div>

          {/* KPI Row */}
          {analytics && (
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
              <KPICard title="Total Sessions" value={analytics.total_sessions as string} icon={<Activity />} trend={{ value: '+12%', positive: true }} />
              <KPICard title="Approval Rate" value={`${analytics.acceptance_rate}%`} icon={<CheckCircle />} trend={{ value: '+4.2%', positive: true }} />
              <KPICard title="Avg Fraud Score" value={analytics.average_fraud_score as string} icon={<ShieldAlert />} trend={{ value: '-2.1', positive: true }} />
              <KPICard title="Consent Rate" value={`${Math.round(((analytics.consent_stats as any)?.granted || 0) / Math.max((analytics.total_sessions as number), 1) * 100)}%`} icon={<Users />} />
            </div>
          )}

          {tab === 'sessions' && (
            <div className="surface-1 overflow-hidden">
              <div className="p-4 border-b border-white/5 flex gap-4">
                <div className="relative flex-1 max-w-sm">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
                  <input type="text" placeholder="Search applicant or ID..." className="w-full bg-[#161618] text-sm text-[#EAEAEA] rounded-md pl-10 pr-4 py-2 outline-none border border-white/5 focus:border-[#D6B36A]/50 transition-colors" />
                </div>
                <div className="relative">
                  <Filter className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#71717A]" />
                  <select className="bg-[#161618] text-sm text-[#EAEAEA] rounded-md pl-10 pr-8 py-2 outline-none border border-white/5 appearance-none cursor-pointer">
                    <option>All Statuses</option>
                    <option>Completed</option>
                    <option>Active</option>
                  </select>
                </div>
              </div>

              {sessions.length === 0 ? (
                 <div className="p-16 text-center text-[#A1A1AA]">
                   <p className="mb-4">No active sessions detected.</p>
                   <GoldButton onClick={() => router.push('/')}>Deploy New Session</GoldButton>
                 </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-[#161618]/50 border-b border-white/5 text-[10px] uppercase font-bold tracking-widest text-[#71717A]">
                        <th className="font-normal py-4 px-6">ID</th>
                        <th className="font-normal py-4 px-6">Applicant</th>
                        <th className="font-normal py-4 px-6">Status</th>
                        <th className="font-normal py-4 px-6">Fraud Score</th>
                        <th className="font-normal py-4 px-6">Offer</th>
                        <th className="font-normal py-4 px-6">Created</th>
                      </tr>
                    </thead>
                    <tbody className="text-sm divide-y divide-white/5">
                      {sessions.map((s, index) => (
                        <tr 
                          key={`${s.id}-${index}`} 
                          onClick={() => router.push(`/dashboard/sessions/${s.id}`)}
                          className="hover:bg-[#161618] cursor-pointer transition-colors group"
                        >
                          <td className="py-4 px-6 text-[#71717A] font-mono group-hover:text-[#D6B36A] transition-colors">
                            {(s.id as string).slice(0,8)}
                          </td>
                          <td className="py-4 px-6 font-medium text-[#EAEAEA]">
                            {s.applicant_name as string || 'Unknown'}
                          </td>
                          <td className="py-4 px-6">
                            <StatusBadge 
                              status={(s.status === 'completed' ? 'success' : s.status === 'active' ? 'active' : 'error') as any} 
                              label={s.status as string} 
                            />
                          </td>
                          <td className="py-4 px-6">
                            {s.fraud_score !== null && s.fraud_score !== undefined ? (
                               <StatusBadge
                                 status={(s.fraud_risk_level === 'high' ? 'error' : s.fraud_risk_level === 'medium' ? 'warning' : 'success') as any}
                                 label={`${(s.fraud_score as number).toFixed(0)} - ${s.fraud_risk_level}`}
                               />
                            ) : (
                               <span className="text-[#71717A]">—</span>
                            )}
                          </td>
                          <td className="py-4 px-6 font-medium text-[#EAEAEA]">
                             {s.offer_amount ? `₹${((s.offer_amount as number) / 100000).toFixed(1)}L` : <span className="text-[#71717A]">—</span>}
                          </td>
                          <td className="py-4 px-6 text-[#A1A1AA] text-xs">
                             {new Date(s.created_at as string).toLocaleDateString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {tab === 'analytics' && analytics && (
            <div className="grid md:grid-cols-2 gap-6">
               <div className="surface-1 p-6">
                 <h3 className="text-xs font-bold tracking-widest text-[#71717A] uppercase mb-6">Pipeline Velocity & Dropoff</h3>
                 <div className="h-64">
                   <ResponsiveContainer width="100%" height="100%">
                     <LineChart data={funnelData}>
                       <XAxis dataKey="name" stroke="#3F3F46" tick={{ fill: '#71717A', fontSize: 10 }} />
                       <YAxis stroke="#3F3F46" tick={{ fill: '#71717A', fontSize: 10 }} />
                       <RechartsTooltip content={<ChartTooltip />} cursor={{ stroke: '#3F3F46', strokeWidth: 1, strokeDasharray: '4 4' }} />
                       <Line type="monotone" dataKey="value" stroke="#D6B36A" strokeWidth={3} dot={{ fill: '#0B0B0C', stroke: '#D6B36A', strokeWidth: 2, r: 4 }} activeDot={{ r: 6 }} />
                     </LineChart>
                   </ResponsiveContainer>
                 </div>
               </div>
               
               <div className="surface-1 p-6">
                 <h3 className="text-xs font-bold tracking-widest text-[#71717A] uppercase mb-6">Fraud Risk Allocation</h3>
                 <div className="h-64">
                   <ResponsiveContainer width="100%" height="100%">
                     <BarChart data={fraudData} margin={{ top: 20 }}>
                       <XAxis dataKey="name" stroke="#3F3F46" tick={{ fill: '#71717A', fontSize: 10 }} />
                       <RechartsTooltip content={<ChartTooltip />} cursor={{ fill: '#161618' }} />
                       <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                         {fraudData.map((entry, index) => (
                           <Cell key={`cell-${index}`} fill={entry.name === 'HIGH' ? '#EF4444' : entry.name === 'MEDIUM' ? '#F59E0B' : '#22C55E'} />
                         ))}
                       </Bar>
                     </BarChart>
                   </ResponsiveContainer>
                 </div>
               </div>
            </div>
          )}
        </div>
      </main>
    </>
  );
}
