import { ReactNode } from 'react';
import { cn } from './GoldButton';

export function PageContainer({
  children,
  className
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn('min-h-screen bg-[var(--bg-base)] text-[var(--text-primary)]', className)}>
      <div className="mx-auto max-w-6xl px-6 py-12 lg:px-8">
        {children}
      </div>
    </div>
  );
}
