'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { createSession } from '@/lib/api';

const DEMO_PERSONAS = [
  { name: 'Priya Sharma', id: 'PRIYA-001', desc: 'Good credit (740) · Salaried ₹60k · Expected: APPROVED', color: 'emerald' },
  { name: 'Rohit X',      id: 'ROHIT-002', desc: 'Bad credit (580) · VPN + age mismatch · Expected: REJECTED',  color: 'rose'    },
  { name: 'Meera Patil',  id: 'MEERA-003', desc: 'Borderline (680) · Self-employed · DPD event · Expected: REFER', color: 'amber' },
];



export default function HomePage() {
  const router = useRouter();
  const [loading, setLoading] = useState<string | null>(null);
  const [customName, setCustomName] = useState('');

  async function handleStart(name: string, id: string) {
    setLoading(id);
    try {
      const result = await createSession(name, id);
      router.push(`/session/${result.session_id}?token=${result.token}`);
    } catch (err) {
      alert('Failed to create session: ' + (err as Error).message);
    } finally {
      setLoading(null);
    }
  }

  async function handleCustomStart() {
    if (!customName.trim()) return;
    handleStart(customName.trim(), customName.trim().toUpperCase().replace(/\s+/g, ''));
  }

  return (
    <main className="min-h-screen relative overflow-hidden">
      {/* Background particles */}
      <div className="particles">
        {Array.from({ length: 20 }).map((_, i) => (
          <div
            key={i}
            className="particle"
            style={{
              left: `${((i * 37 + 13) % 100)}%`,
              animationDelay: `${(i * 1.3) % 8}s`,
              animationDuration: `${6 + (i * 0.7) % 6}s`,
            }}
          />
        ))}
      </div>

      <div className="relative z-10 max-w-6xl mx-auto px-4 py-12">
        {/* Header */}
        <header className="text-center mb-16 slide-up">
          <div className="inline-flex items-center gap-2 mb-6 px-4 py-2 rounded-full border border-indigo-500/30 bg-indigo-500/10">
            <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-sm text-indigo-300 font-medium">Airavat 3.0 • Problem Statement F1</span>
          </div>
          <h1 className="text-5xl md:text-7xl font-bold mb-4">
            <span className="bg-gradient-to-r from-indigo-400 via-violet-400 to-purple-400 bg-clip-text text-transparent">
              AgentFinance
            </span>
            <span className="text-white/90"> AI</span>
          </h1>
          <p className="text-xl text-slate-400 max-w-2xl mx-auto mb-2">
            Autonomous AI-Powered Loan Onboarding
          </p>
          <p className="text-sm text-slate-500 max-w-xl mx-auto">
            Click a link • Join a video call • Walk away with a personalised loan offer.
            <br />Zero human agents. Browser only. End to end.
          </p>
        </header>

        {/* Tier badges */}
        <div className="flex flex-wrap justify-center gap-2 mb-12 slide-up" style={{ animationDelay: '0.1s' }}>
          {['Session', 'STT', 'Consent', 'Liveness', 'LLM', 'Fraud', 'Bureau', 'Offer', 'Orchestrator', 'Dashboard'].map((tier, i) => (
            <span key={tier} className="px-3 py-1 text-xs rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
              T{i + 1}: {tier}
            </span>
          ))}
        </div>

        {/* Demo Personas */}
        <section className="mb-12">
          <h2 className="text-center text-lg font-semibold text-slate-300 mb-6 slide-up" style={{ animationDelay: '0.2s' }}>
            Start a Demo Session
          </h2>
          <div className="grid md:grid-cols-3 gap-6">
            {DEMO_PERSONAS.map((persona, i) => (
              <button
                key={persona.id}
                type="button"
                onClick={() => handleStart(persona.name, persona.id)}
                disabled={loading !== null}
                className="glass-card glow p-6 slide-up text-left cursor-pointer hover:border-indigo-500/40 transition-all duration-300 disabled:opacity-60"
                style={{ animationDelay: `${0.3 + i * 0.1}s` }}
              >
                <div className="flex items-center gap-3 mb-3">
                  <div className={`w-10 h-10 rounded-full flex items-center justify-center text-lg font-bold ${
                    persona.color === 'emerald'
                      ? 'bg-emerald-500/20 text-emerald-400'
                      : persona.color === 'rose'
                        ? 'bg-rose-500/20 text-rose-400'
                        : 'bg-amber-500/20 text-amber-400'
                  }`}>
                    {persona.name.charAt(0)}
                  </div>
                  <div>
                    <h3 className="font-semibold text-white">{persona.name}</h3>
                    <p className="text-xs text-slate-500 font-mono">{persona.id}</p>
                  </div>
                </div>
                <p className="text-sm text-slate-400">{persona.desc}</p>
              </button>
            ))}
          </div>
        </section>



        {/* Custom applicant */}
        <section className="glass-card glow max-w-md mx-auto p-6 mb-12 slide-up" style={{ animationDelay: '0.6s' }}>
          <h3 className="font-semibold text-white mb-3">Custom Applicant</h3>
          <div className="flex gap-3">
            <input
              type="text"
              placeholder="Enter applicant name..."
              value={customName}
              onChange={(e) => setCustomName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleCustomStart()}
              className="flex-1 px-4 py-3 rounded-xl bg-white/5 border border-indigo-500/20 text-white placeholder-slate-500 outline-none focus:border-indigo-500/50 transition-colors"
            />
            <button
              onClick={handleCustomStart}
              disabled={!customName.trim() || loading !== null}
              className="btn-primary"
            >
              Start
            </button>
          </div>
        </section>

        {/* Dashboard link */}
        <div className="text-center slide-up" style={{ animationDelay: '0.7s' }}>
          <a
            href="/dashboard"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-xl border border-indigo-500/20 text-indigo-300 hover:bg-indigo-500/10 transition-all"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
            </svg>
            Open Compliance Dashboard
          </a>
        </div>

        {/* Architecture info */}
        <section className="mt-16 grid md:grid-cols-5 gap-4 slide-up" style={{ animationDelay: '0.8s' }}>
          {[
            { label: 'Frontend', value: 'Next.js 14', icon: '⚡' },
            { label: 'Backend', value: 'FastAPI', icon: '🔧' },
            { label: 'STT', value: 'Whisper', icon: '🎤' },
            { label: 'LLM', value: 'Groq', icon: '🧠' },
            { label: 'Vision', value: 'MediaPipe', icon: '👁' },
          ].map((item) => (
            <div key={item.label} className="text-center p-4 rounded-xl bg-white/[0.02] border border-white/[0.05]">
              <div className="text-2xl mb-1">{item.icon}</div>
              <div className="text-xs text-slate-500">{item.label}</div>
              <div className="text-sm font-medium text-slate-300">{item.value}</div>
            </div>
          ))}
        </section>
      </div>
    </main>
  );
}
