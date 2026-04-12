import { RefObject } from 'react';
import { Camera, Bot, ShieldCheck } from 'lucide-react';
import { cn } from './ui/GoldButton';

export default function VideoPanel({
  videoRef,
  agentMessage,
  isProcessing,
  visionData,
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  agentMessage: string;
  isProcessing: boolean;
  visionData?: { liveness: number; age: number | null; isLive: boolean } | null;
  transcript?: any[];
}) {
  return (
    <div className="relative w-full h-full flex flex-col gap-4">
      {/* Video Container */}
      <div className={cn(
        "relative flex-1 surface-1 overflow-hidden transition-all duration-700",
        isProcessing ? "border-[#D6B36A]/50 shadow-[0_0_40px_rgba(214,179,106,0.15)]" : "border-white/5"
      )}>
        {/* Subtle glass overlay */}
        <div className="absolute inset-0 bg-gradient-to-b from-[#0B0B0C]/40 via-transparent to-[#0B0B0C]/80 z-10 pointer-events-none" />
        
        {/* Stream */}
        <video 
          ref={videoRef} 
          autoPlay 
          playsInline 
          muted 
          className="w-full h-full object-cover"
        />

        {/* Top HUD */}
        <div className="absolute top-6 left-6 right-6 flex justify-between items-start z-20">
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-[#0B0B0C]/80 border border-white/10 backdrop-blur-md">
            <Camera className="w-4 h-4 text-[#EAEAEA]" />
            <span className="text-xs font-medium text-[#EAEAEA]">Encrypted Feed</span>
          </div>

          {visionData && (
            <div className="flex flex-col items-end gap-2">
              <div className={cn(
                "px-3 py-1.5 rounded-full border backdrop-blur-md text-xs font-bold uppercase tracking-widest flex items-center gap-2",
                visionData.isLive 
                  ? "bg-[#22C55E]/10 border-[#22C55E]/30 text-[#22C55E]" 
                  : "bg-[#EF4444]/10 border-[#EF4444]/30 text-[#EF4444]"
              )}>
                {visionData.isLive ? <ShieldCheck className="w-3.5 h-3.5" /> : null}
                Liveness: {(visionData.liveness * 100).toFixed(0)}%
              </div>
              {visionData.age && (
                <div className="px-3 py-1 rounded-full bg-[#0B0B0C]/80 border border-white/10 text-[10px] text-[#A1A1AA] uppercase tracking-widest backdrop-blur-md">
                  Est. Age: {visionData.age}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Bottom HUD - AI Subtitles */}
        <div className="absolute bottom-8 left-12 right-12 z-20 text-center flex flex-col items-center gap-4 fade-in-up">
          <div className="p-2 rounded-full bg-[#D6B36A]/10 border border-[#D6B36A]/20">
            <Bot className="w-6 h-6 text-[#D6B36A]" />
          </div>
          <p className="text-lg md:text-xl font-medium text-[#EAEAEA] drop-shadow-md leading-relaxed max-w-2xl">
            {agentMessage}
          </p>
        </div>
      </div>
    </div>
  );
}
