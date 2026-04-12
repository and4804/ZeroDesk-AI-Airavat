import { cn } from './GoldButton';

type BadgeStatus = 'success' | 'error' | 'warning' | 'info' | 'neutral' | 'active';

export function StatusBadge({ status, label, className }: { status: BadgeStatus, label: string, className?: string }) {
  const styles: Record<BadgeStatus, string> = {
    success: 'bg-[#22C55E]/10 text-[#22C55E] border-[#22C55E]/20',
    error: 'bg-[#EF4444]/10 text-[#EF4444] border-[#EF4444]/20',
    warning: 'bg-[#F59E0B]/10 text-[#F59E0B] border-[#F59E0B]/20',
    info: 'bg-[#3B82F6]/10 text-[#3B82F6] border-[#3B82F6]/20',
    neutral: 'bg-[#161618] text-[#A1A1AA] border-[#A1A1AA]/20',
    active: 'bg-[#D6B36A]/10 text-[#D6B36A] border-[#D6B36A]/30',
  };

  return (
    <span className={cn('px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider rounded-md border inline-flex items-center whitespace-nowrap', styles[status], className)}>
      {label}
    </span>
  );
}
