import { cn } from './ui/GoldButton';
import { Activity } from 'lucide-react';

export default function Topbar({
  sessionId,
  currentStage,
  status
}: {
  sessionId?: string;
  currentStage?: string;
  status?: string;
}) {
  return (
    <div className="fixed top-0 left-16 right-0 h-16 bg-[#0B0B0C]/80 backdrop-blur-md border-b border-white/5 flex items-center justify-between px-6 z-40">
      <div className="flex items-center gap-4">
        {sessionId ? (
          <>
            <span className="text-[#A1A1AA] text-sm font-medium tracking-tight">Session //</span>
            <span className="text-[#EAEAEA] font-mono text-sm tracking-widest">{sessionId.slice(0, 8)}</span>
          </>
        ) : (
          <span className="text-[#EAEAEA] font-medium tracking-tight">System Environment</span>
        )}
      </div>

      <div className="flex items-center gap-4">
        {status && (
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#161618] border border-white/5">
            <span className={cn('w-2 h-2 rounded-full animate-pulse', status === 'active' ? 'bg-[#D6B36A]' : status === 'completed' ? 'bg-[#22C55E]' : 'bg-[#EF4444]')} />
            <span className="text-[10px] uppercase font-bold tracking-widest text-[#EAEAEA]">{status}</span>
          </div>
        )}
        {currentStage && (
          <div className="flex items-center gap-2 text-[#71717A] text-xs font-mono uppercase">
            <Activity className="w-3 h-3 text-[#D6B36A]" />
            {currentStage}
          </div>
        )}
      </div>
    </div>
  );
}
