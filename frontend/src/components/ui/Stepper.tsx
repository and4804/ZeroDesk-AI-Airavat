import { cn } from './GoldButton';
import { Check } from 'lucide-react';

export interface Step {
  id: string;
  label: string;
}

export function Stepper({ steps, currentStepId }: { steps: Step[]; currentStepId: string }) {
  const currentIndex = steps.findIndex(s => s.id === currentStepId);

  return (
    <div className="flex flex-col gap-0 w-full relative">
      {/* Background connector line */}
      <div className="absolute left-[11px] top-3 bottom-5 w-px bg-white/5" />
      
      {steps.map((step, index) => {
        const isCompleted = index < currentIndex;
        const isCurrent = index === currentIndex;
        const isPending = index > currentIndex;

        return (
          <div key={`${step.id}-${index}`} className="flex items-start gap-4 py-2 relative z-10 group">
            <div className="flex flex-col items-center shrink-0 w-6">
              <div
                className={cn(
                  'w-[22px] h-[22px] rounded-full flex items-center justify-center text-[10px] border-2 transition-all duration-300 shadow-sm bg-[#0B0B0C]',
                  isCompleted ? 'border-[#22C55E] text-[#22C55E]' :
                  isCurrent ? 'border-[#D6B36A] text-[#D6B36A] shadow-[0_0_10px_rgba(214,179,106,0.3)]' :
                  'border-white/10 text-white/20'
                )}
              >
                {isCompleted ? <Check className="w-3 h-3" strokeWidth={3} /> : (index + 1)}
              </div>
            </div>
            
            <div className={cn(
              'flex flex-col pt-0.5 transition-colors duration-300',
              isCompleted ? 'text-[#A1A1AA]' :
              isCurrent ? 'text-[#EAEAEA]' :
              'text-[#71717A]'
            )}>
              <span className={cn('text-sm font-medium tracking-tight', isCurrent && 'font-semibold')}>
                {step.label}
              </span>
              {isCurrent && (
                <span className="text-[10px] uppercase tracking-widest text-[#D6B36A] mt-1 animate-pulse">
                  Processing...
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
