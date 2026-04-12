import { GoldButton } from './ui/GoldButton';
import { CheckCircle2, XCircle } from 'lucide-react';

export default function DecisionPanel({
  visible,
  decision,
  confidence,
  loanAmount,
  interestRate,
  tenure,
  emi,
  onAccept,
  onDecline,
  onNegotiate,
  isProcessing,
  isAccepted,
  offerId,
  negotiationInput,
  onNegotiationInputChange
}: any) {
  if (!visible) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-[#0B0B0C]/90 backdrop-blur-sm transition-opacity" />
      
      <div className="relative surface-1 w-full max-w-3xl overflow-hidden shadow-2xl fade-in-up">
        {/* Glow */}
        <div className={`absolute -top-32 -left-32 w-64 h-64 rounded-full blur-[100px] opacity-20 pointer-events-none ${decision === 'APPROVED' ? 'bg-[#22C55E]' : 'bg-[#EF4444]'}`} />
        
        <div className="p-10">
          <div className="flex items-start justify-between mb-10">
            <div>
              <div className="flex items-center gap-3 mb-2">
                {decision === 'APPROVED' ? (
                  <CheckCircle2 className="w-8 h-8 text-[#22C55E]" />
                ) : (
                  <XCircle className="w-8 h-8 text-[#EF4444]" />
                )}
                <h2 className="text-3xl font-bold tracking-tight text-[#EAEAEA]">Final Decision</h2>
              </div>
              <p className="text-[#A1A1AA] text-sm font-mono mt-2">Evaluation Reference: {offerId}</p>
            </div>
            
            <div className={`px-4 py-2 rounded-lg border text-sm font-bold uppercase tracking-widest ${decision === 'APPROVED' ? 'bg-[#22C55E]/10 border-[#22C55E]/30 text-[#22C55E]' : 'bg-[#EF4444]/10 border-[#EF4444]/30 text-[#EF4444]'}`}>
              {decision}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-10">
            {[
              { label: 'Authorized Amount', value: `₹${(loanAmount / 100000).toFixed(1)}L` },
              { label: 'Dynamic Interest Rate', value: `${interestRate}%` },
              { label: 'Calculated Tenure', value: `${tenure} Months` },
              { label: 'Monthly Repayment', value: `₹${Math.round(emi).toLocaleString()}` }
            ].map((stat, i) => (
              <div key={i} className="surface-2 p-5 flex flex-col justify-between">
                <span className="text-[#A1A1AA] text-xs font-bold uppercase tracking-wider mb-2">{stat.label}</span>
                <span className={`text-2xl font-bold ${stat.label === 'Authorized Amount' ? 'text-[#D6B36A]' : 'text-[#EAEAEA]'}`}>{stat.value}</span>
              </div>
            ))}
          </div>

          {!isAccepted && decision === 'APPROVED' && (
            <div className="space-y-6">
              <div className="flex gap-4">
                <input
                  type="text"
                  value={negotiationInput}
                  onChange={(e) => onNegotiationInputChange?.(e.target.value)}
                  placeholder="Request adjustment (e.g., 'Lower rate' or 'Higher amount')..."
                  className="flex-1 bg-[#0B0B0C] border border-white/10 rounded-lg px-4 py-3 text-sm text-[#EAEAEA] outline-none focus:border-[#D6B36A]/50 transition-colors"
                  disabled={isProcessing}
                />
                <GoldButton variant="outline" onClick={() => onNegotiate(negotiationInput)} isLoading={isProcessing} disabled={!negotiationInput.trim()}>
                  Negotiate Policy
                </GoldButton>
              </div>

              <div className="flex gap-4 pt-4 border-t border-white/5">
                <GoldButton className="flex-1" onClick={onAccept} isLoading={isProcessing}>
                  Authorize & Accept Terms
                </GoldButton>
                <GoldButton className="flex-1" variant="ghost" onClick={onDecline} disabled={isProcessing}>
                  Decline Offer
                </GoldButton>
              </div>
            </div>
          )}

          {isAccepted && (
            <div className="p-4 rounded-lg bg-[#22C55E]/10 border border-[#22C55E]/20 text-[#22C55E] text-sm text-center font-medium">
              Contract mathematically secured. Funds queued for transfer.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
