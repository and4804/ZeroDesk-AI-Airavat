import { cn } from './GoldButton';

export function SectionHeader({
  title,
  description,
  className
}: {
  title: string;
  description?: string;
  className?: string;
}) {
  return (
    <div className={cn('flex flex-col gap-1.5', className)}>
      <h2 className="text-lg font-bold tracking-tight text-[#EAEAEA]">{title}</h2>
      {description && <p className="text-sm text-[#A1A1AA]">{description}</p>}
    </div>
  );
}
