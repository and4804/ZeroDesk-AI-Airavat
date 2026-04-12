import { ButtonHTMLAttributes, ReactNode } from 'react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

interface GoldButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode;
  variant?: 'primary' | 'outline' | 'ghost';
  isLoading?: boolean;
}

export function GoldButton({
  children,
  className,
  variant = 'primary',
  isLoading,
  disabled,
  ...props
}: GoldButtonProps) {
  const baseStyles = 'relative inline-flex items-center justify-center font-medium transition-all duration-200 rounded-lg text-sm px-5 py-2.5 outline-none';
  
  const variants = {
    primary: 'bg-[#D6B36A] hover:bg-[#A38A4A] text-[#0B0B0C] border border-transparent shadow-[0_4px_14px_0_rgba(214,179,106,0.2)] hover:shadow-[0_6px_20px_rgba(214,179,106,0.3)] hover:-translate-y-0.5',
    outline: 'bg-transparent border border-[#D6B36A] text-[#D6B36A] hover:bg-[#D6B36A]/10',
    ghost: 'bg-transparent text-[#EAEAEA] hover:text-[#D6B36A] hover:bg-[#D6B36A]/5'
  };

  const disabledStyles = 'opacity-50 cursor-not-allowed transform-none hover:transform-none hover:shadow-none';

  return (
    <button
      className={cn(baseStyles, variants[variant], (disabled || isLoading) && disabledStyles, className)}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <span className="flex items-center gap-2">
          <span className="spinner border-t-[#0B0B0C] border-2 border-[rgba(11,11,12,0.2)] w-4 h-4" />
          Processing...
        </span>
      ) : (
        children
      )}
    </button>
  );
}
