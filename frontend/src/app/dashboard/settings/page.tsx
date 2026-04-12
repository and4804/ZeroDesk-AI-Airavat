'use client';

import Sidebar from '@/components/Sidebar';
import Topbar from '@/components/Topbar';
import { SectionHeader } from '@/components/ui/SectionHeader';
import { GoldButton } from '@/components/ui/GoldButton';
import { Sliders, Shield, Zap } from 'lucide-react';
import { useState } from 'react';

export default function SettingsPage() {
  const [threshold, setThreshold] = useState(65);
  const [fraudSensitivity, setFraudSensitivity] = useState('Standard');

  return (
    <>
      <Sidebar activePage="settings" />
      <Topbar />

      <main className="min-h-screen bg-[#0B0B0C] pt-20 pl-16">
         <div className="max-w-4xl mx-auto p-6 md:p-8">
            <SectionHeader 
               title="System Constants & Constraints" 
               description="Global operational dials for the autonomous approval engine." 
               className="mb-8"
            />

            <div className="space-y-6">
               <div className="surface-1 p-6 flex flex-col gap-6">
                  <div className="flex items-center gap-3 border-b border-white/5 pb-4">
                     <Sliders className="w-5 h-5 text-[#D6B36A]" />
                     <h3 className="font-bold text-[#EAEAEA]">Risk Tolerance Threshold</h3>
                  </div>

                  <div>
                     <div className="flex justify-between text-sm mb-4">
                        <span className="text-[#A1A1AA]">Auto-Reject Score Cutoff</span>
                        <span className="font-bold text-[#D6B36A]">{threshold}/100</span>
                     </div>
                     <input 
                        type="range" 
                        min="0" 
                        max="100" 
                        value={threshold} 
                        onChange={(e) => setThreshold(parseInt(e.target.value))}
                        className="w-full h-1 bg-[#161618] rounded-full appearance-none cursor-pointer accent-[#D6B36A]"
                     />
                     <div className="flex justify-between text-[10px] text-[#71717A] mt-2 font-mono uppercase">
                        <span>Permissive</span>
                        <span>Strict</span>
                     </div>
                  </div>
               </div>

               <div className="surface-1 p-6 flex flex-col gap-6">
                  <div className="flex items-center gap-3 border-b border-white/5 pb-4">
                     <Shield className="w-5 h-5 text-[#D6B36A]" />
                     <h3 className="font-bold text-[#EAEAEA]">Fraud Agent Sensitivity</h3>
                  </div>

                  <div className="grid grid-cols-3 gap-4">
                     {['Permissive', 'Standard', 'Aggressive'].map((level, index) => (
                        <button 
                           key={`${level}-${index}`}
                           onClick={() => setFraudSensitivity(level)}
                           className={`p-4 rounded-xl border transition-all text-sm font-semibold tracking-wide ${
                              fraudSensitivity === level 
                              ? 'bg-[#D6B36A]/10 border-[#D6B36A]/50 text-[#D6B36A] shadow-[0_0_15px_rgba(214,179,106,0.1)]' 
                              : 'bg-[#0B0B0C] border-white/5 text-[#A1A1AA] hover:border-white/10'
                           }`}
                        >
                           {level}
                        </button>
                     ))}
                  </div>
               </div>
               
               <div className="flex justify-end pt-4">
                  <GoldButton className="gap-2 px-8">
                     <Zap className="w-4 h-4" /> Deploy Configuration
                  </GoldButton>
               </div>
            </div>
         </div>
      </main>
    </>
  );
}
