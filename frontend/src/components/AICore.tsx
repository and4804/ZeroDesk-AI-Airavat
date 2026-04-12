import { cn } from './ui/GoldButton';
import { ShieldCheck } from 'lucide-react';

export default function AICore({
  mode,
  statusText
}: {
  mode: 'idle' | 'listening' | 'analyzing' | 'confident';
  statusText: string;
}) {
  return (
    <div className="flex flex-col items-center py-6 border-b border-white/5 w-full">
      <div className="relative mb-6">
        {/* Outer Ring */}
        <div className={cn(
          "absolute inset-[-12px] rounded-full border border-[#D6B36A]/20 transition-all duration-1000",
          mode === 'analyzing' ? 'animate-[spin_4s_linear_infinite] scale-110 opacity-100' :
          mode === 'listening' ? 'scale-105 opacity-80' : 'scale-95 opacity-30'
        )} />
        
        {/* Secondary Ring */}
        <div className={cn(
          "absolute inset-[-6px] rounded-full border border-dashed border-[#D6B36A]/40 transition-all duration-700",
          mode === 'analyzing' ? 'animate-[spin_3s_linear_infinite_reverse] opacity-100' :
          mode === 'listening' ? 'animate-[spin_8s_linear_infinite] opacity-70' : 'opacity-20'
        )} />
        
        {/* Core */}
        <div className={cn(
          "relative w-12 h-12 rounded-full flex items-center justify-center transition-all duration-500",
          mode === 'confident' ? "bg-[#22C55E]/20 shadow-[0_0_20px_rgba(34,197,94,0.4)]" :
          "bg-[#D6B36A]/10 shadow-[0_0_15px_rgba(214,179,106,0.3)]",
          mode === 'analyzing' && "animate-pulse"
        )}>
          {mode === 'confident' ? (
            <ShieldCheck className="w-5 h-5 text-[#22C55E]" />
          ) : (
            <div className="w-4 h-4 rounded-full bg-[#D6B36A] opacity-80 shadow-[0_0_10px_rgba(214,179,106,0.8)]" />
          )}
        </div>
      </div>

      <div className="text-center">
        <h3 className="text-[#EAEAEA] font-medium tracking-tight text-sm mb-1">Cortex System</h3>
        <p className="text-[10px] text-[#D6B36A] uppercase font-bold tracking-widest">{statusText}</p>
      </div>
    </div>
  );
}
