'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { createSession } from '@/lib/api';
import { ShieldAlert, Code } from 'lucide-react';
import { GoldButton } from '@/components/ui/GoldButton';

export default function HomePage() {
  const router = useRouter();
  const [loading, setLoading] = useState<boolean>(false);

  async function handleStart() {
    setLoading(true);
    try {
      const result = await createSession("Applicant", "LIVE_APPLICANT_" + Date.now());
      router.push(`/session/${result.session_id}?token=${result.token}`);
    } catch (err) {
      alert('Failed to create session: ' + (err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="min-h-screen bg-[#0B0B0C] text-[#EAEAEA] font-sans selection:bg-[#D6B36A] selection:text-[#0B0B0C] flex flex-col">
      {/* Navigation */}
      <nav className="absolute top-0 w-full py-6 px-8 flex justify-between items-center z-10 glass-panel border-b-0">
        <div className="flex items-center gap-2">
          <ShieldAlert className="w-6 h-6 text-[#D6B36A]" />
          <span className="font-bold text-lg tracking-tight">AgentFinance <span className="text-[#A1A1AA] font-normal">AI</span></span>
        </div>
        <div className="flex gap-4">
          <button onClick={() => router.push('/dashboard')} className="text-sm font-medium text-[#A1A1AA] hover:text-[#D6B36A] transition-colors">
            Compliance Dashboard
          </button>
        </div>
      </nav>

      {/* Hero Section */}
      <section className="flex-1 relative flex flex-col justify-center items-center text-center px-6 lg:px-8 max-w-7xl mx-auto w-full">
        {/* Subtle glow behind hero */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-[#D6B36A] rounded-full opacity-[0.03] blur-[100px] pointer-events-none" />
        
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-[#D6B36A]/30 bg-[#D6B36A]/10 text-[#D6B36A] text-xs font-semibold tracking-widest uppercase mb-8 fade-in">
          <span className="w-1.5 h-1.5 rounded-full bg-[#D6B36A] animate-pulse" />
          Sovereign Intelligence System
        </div>
        
        <h1 className="text-5xl md:text-7xl font-bold tracking-tight mb-6 max-w-4xl fade-in-up" style={{ animationDelay: '0.1s' }}>
          Autonomous <span className="text-[#D6B36A]">Loan Intelligence</span>
        </h1>
        <p className="text-lg md:text-xl text-[#A1A1AA] max-w-2xl mb-12 fade-in-up" style={{ animationDelay: '0.2s' }}>
          AI agents verify identity, assess risk, and strictly underwrite loans in real-time, eliminating manual back-office tasks without increasing systemic risk.
        </p>

        <div className="fade-in-up" style={{ animationDelay: '0.3s' }}>
          <GoldButton onClick={handleStart} className="px-10 py-4 text-lg font-bold shadow-[0_0_20px_rgba(214,179,106,0.3)] hover:shadow-[0_0_30px_rgba(214,179,106,0.5)]" isLoading={loading}>
            Start Live Originator
          </GoldButton>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-white/5 bg-[#0B0B0C] py-12 text-center text-sm text-[#71717A]">
        <div className="flex items-center justify-center gap-2 mb-4">
          <Code className="w-4 h-4" />
          <span>AgentFinance AI Architecture v3.0</span>
        </div>
        <div className="flex justify-center gap-6 text-xs uppercase tracking-widest font-semibold">
          <a href="#" className="hover:text-[#D6B36A] transition-colors">Documentation</a>
          <a href="#" className="hover:text-[#D6B36A] transition-colors">System Metrics</a>
          <a href="#" className="hover:text-[#D6B36A] transition-colors">Security Setup</a>
        </div>
      </footer>
    </main>
  );
}
