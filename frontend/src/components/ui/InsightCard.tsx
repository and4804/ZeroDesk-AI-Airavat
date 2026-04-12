import { cn } from './GoldButton';
import { CheckCircle2, AlertTriangle, Info, XCircle } from 'lucide-react';

type InsightStatus = 'success' | 'warning' | 'error' | 'info';

export function InsightCard({
  status = 'info',
  message,
  timestamp,
  active = false
}: {
  status?: InsightStatus;
  message: string;
  timestamp?: string;
  active?: boolean;
}) {
  const Icon = {
    success: CheckCircle2,
    warning: AlertTriangle,
    error: XCircle,
    info: Info
  }[status];

  const colors = {
    success: 'text-[#22C55E]',
    warning: 'text-[#F59E0B]',
    error: 'text-[#EF4444]',
    info: 'text-[#A1A1AA]'
  };

  return (
    <div className={cn(
      'flex gap-3 p-3 rounded-xl border border-white/5 bg-[#161618] transition-all duration-300',
      active && 'border-white/10 bg-[#111113] shadow-md -translate-x-1'
    )}>
      <Icon className={cn('w-4 h-4 shrink-0 mt-0.5', colors[status])} />
      <div className="flex flex-col flex-1">
        <span className="text-xs text-[#EAEAEA] leading-relaxed">{message}</span>
        {timestamp && <span className="text-[9px] font-mono text-[#71717A] mt-1">{timestamp}</span>}
      </div>
    </div>
  );
}
