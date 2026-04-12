import { ReactNode } from 'react';
import { cn } from './GoldButton';

export function KPICard({
  title,
  value,
  icon,
  trend,
  className
}: {
  title: string;
  value: string | number;
  icon?: ReactNode;
  trend?: { value: string; positive?: boolean };
  className?: string;
}) {
  return (
    <div className={cn('surface-1 p-5 flex flex-col', className)}>
      <div className="flex items-center justify-between mb-3 text-[#A1A1AA]">
        <span className="text-xs font-semibold uppercase tracking-wider">{title}</span>
        {icon && <span className="text-[#71717A] opacity-70 w-4 h-4">{icon}</span>}
      </div>
      <div className="flex items-end justify-between mt-auto">
        <span className="text-2xl font-bold text-[#EAEAEA] tracking-tight">{value}</span>
        {trend && (
          <span className={cn('text-xs flex items-center font-medium', trend.positive ? 'text-[#22C55E]' : 'text-[#EF4444]')}>
            {trend.positive ? '↑' : '↓'} {trend.value}
          </span>
        )}
      </div>
    </div>
  );
}
