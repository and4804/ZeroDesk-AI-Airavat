'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useSearchParams, useRouter } from 'next/navigation';
import * as api from '@/lib/api';
import Sidebar from '@/components/Sidebar';
import Topbar from '@/components/Topbar';
import AICore from '@/components/AICore';
import VideoPanel from '@/components/VideoPanel';
import DecisionPanel from '@/components/DecisionPanel';
import { Stepper } from '@/components/ui/Stepper';
import { InsightCard } from '@/components/ui/InsightCard';
import { Send } from 'lucide-react';

const PIPELINE_STAGES = [
  { id: 'SESSION_INIT', label: 'Initialize' },
  { id: 'METADATA_CAPTURE', label: 'Device Verify' },
  { id: 'STT_ACTIVE', label: 'Data Extraction' },
  { id: 'CONSENT_CHECK', label: 'Verbal Consent' },
  { id: 'LIVENESS_CHECK', label: 'Biometrics' },
  { id: 'LLM_ANALYSIS', label: 'Intent Analysis' },
  { id: 'FRAUD_SCORING', label: 'Fraud Detection' },
  { id: 'BUREAU_CHECK', label: 'Bureau Validation' },
  { id: 'OFFER_GENERATION', label: 'Term Decision' },
  { id: 'SESSION_COMPLETE', label: 'Contract Secured' },
];

export default function SessionPage() {
  const router = useRouter();
  const params = useParams();
  const sessionId = params.id as string;
  const searchParams = useSearchParams();

  const [status, setStatus] = useState<string>('connecting');
  const [currentStage, setCurrentStage] = useState<string>('SESSION_INIT');
  const [fields, setFields] = useState<Record<string, { value: string; confidence: number }>>({});
  const [consent, setConsent] = useState<{ detected: boolean; phrase?: string } | null>(null);
  const [vision, setVision] = useState<{ liveness: number; age: number | null; isLive: boolean } | null>(null);
  const [fraud, setFraud] = useState<{ score: number; level: string } | null>(null);
  const [offer, setOffer] = useState<Record<string, unknown> | null>(null);
  const [agentMessage, setAgentMessage] = useState('Initializing sovereign intelligence system…');
  const [textInput, setTextInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [aiMode, setAiMode] = useState<'idle' | 'listening' | 'analyzing' | 'confident'>('idle');
  const [aiStatusText, setAiStatusText] = useState('System initializing…');

  const [intelEvents, setIntelEvents] = useState<Array<{ id: string, status: any, message: string, timestamp: string }>>([]);
  const [showDecision, setShowDecision] = useState(false);

  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameCountRef = useRef(0);
  const streamRef = useRef<MediaStream | null>(null);
  
  function nextEventId() { return Math.random().toString(36).substr(2, 9); }
  function nowTime() { return new Date().toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }); }

  function addIntel(status: 'success' | 'warning' | 'error' | 'info', message: string) {
    setIntelEvents(prev => [{ id: nextEventId(), status, message, timestamp: nowTime() }, ...prev]);
  }

  function speak(text: string) {
    if ('speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1;
      utterance.pitch = 1;
      utterance.lang = 'en-US';
      window.speechSynthesis.speak(utterance);
    }
  }

  useEffect(() => {
    async function init() {
      try {
        setStatus('initializing');
        setAiMode('analyzing');
        setAiStatusText('Establishing secure connection…');
        addIntel('info', 'Initializing session protocol…');

        await api.storeMetadata(sessionId, {
          device_fingerprint: "MOCK_FINGERPRINT",
          user_agent: navigator.userAgent,
          webrtc_supported: true,
        });

        addIntel('success', 'Device metadata captured');
        await api.advancePipeline(sessionId);
        setCurrentStage('METADATA_CAPTURE');

        try {
          const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
          streamRef.current = stream;
          if (videoRef.current) videoRef.current.srcObject = stream;
          addIntel('success', 'Camera and microphone active');
        } catch {
          addIntel('warning', 'Camera access denied. Operating in fallback mode.');
        }

        setStatus('active');
        setCurrentStage('STT_ACTIVE');
        setAiMode('listening');
        setAiStatusText('Listening…');
        addIntel('info', 'Awaiting applicant input…');
        setAgentMessage('Session active. Please provide your data.');
        
        startFrameCapture();
      } catch (err) {
        setError((err as Error).message);
        setStatus('error');
      }
    }
    init();

    return () => {
      streamRef.current?.getTracks().forEach(t => t.stop());
      window.speechSynthesis?.cancel();
    };
  }, [sessionId]);

  const startFrameCapture = useCallback(() => {
    const interval = setInterval(async () => {
      if (!videoRef.current || !canvasRef.current) return;
      const canvas = canvasRef.current;
      canvas.width = 320; canvas.height = 240;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.drawImage(videoRef.current, 0, 0, 320, 240);
      const dataUrl = canvas.toDataURL('image/jpeg', 0.7);
      const base64 = dataUrl.split(',')[1];
      if (!base64) return;

      try {
        const result = await api.analyzeVision(sessionId, base64, undefined, frameCountRef.current++);
        setVision({ liveness: result.liveness_score, age: result.estimated_age, isLive: result.is_live });

        if (frameCountRef.current === 1) {
          addIntel(result.is_live ? 'success' : 'warning', `Liveness detection: ${(result.liveness_score * 100).toFixed(1)}%`);
        }
      } catch {}
    }, 3000);
    return () => clearInterval(interval);
  }, [sessionId]);

  async function handleTextSubmit() {
    if (!textInput.trim() || isProcessing) return;
    setIsProcessing(true);
    setAiMode('analyzing');
    setAiStatusText('Processing…');
    const text = textInput.trim();
    setTextInput('');

    try {
      await api.addTextTranscript(sessionId, text);
      const consentResult = await api.checkConsent(sessionId, text);
      
      if (consentResult.consent_detected) {
        setConsent({ detected: true, phrase: consentResult.record?.phrase_detected });
        setCurrentStage('CONSENT_CHECK');
        addIntel('success', `Consent captured: "${consentResult.record?.phrase_detected}"`);
      }

      const extracted = await api.extractFields(sessionId);
      if (extracted.fields) {
        setFields(extracted.fields);
        setCurrentStage('STT_ACTIVE');
        Object.entries(extracted.fields).forEach(([key, val]: any) => {
          if (val.value) addIntel('success', `${key.replace(/_/g, ' ')}: ${val.value}`);
        });
      }

      const filled = Object.values(extracted.fields || {}).filter((f: any) => f.value !== null).length;
      if (filled >= 3 && !consent?.detected) {
        setAiMode('listening');
        setAiStatusText('Awaiting consent');
        setAgentMessage('I require verbal consent to proceed. Please explicitly agree.');
      } else if (filled >= 3 && consent?.detected) {
        await runFullPipeline();
      } else {
        setAiMode('listening');
        setAiStatusText('Gathering data');
        setAgentMessage('Please provide more details (income, age, loan amount).');
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsProcessing(false);
    }
  }

  async function runFullPipeline() {
    setIsProcessing(true);
    try {
      setCurrentStage('LLM_ANALYSIS');
      setAiMode('analyzing');
      setAiStatusText('Multi-layer analysis');
      addIntel('info', 'Executing behavioral analysis');
      await api.analyzeLLM(sessionId);
      await api.advancePipeline(sessionId);
      
      setCurrentStage('FRAUD_SCORING');
      addIntel('info', 'Evaluating fraud vectors');
      const fraudResult = await api.scoreFraud(sessionId);
      setFraud({ score: fraudResult.composite_score, level: fraudResult.risk_level });
      await api.advancePipeline(sessionId);
      addIntel(fraudResult.risk_level === 'high' ? 'error' : 'success', `Fraud risk: ${fraudResult.risk_level}`);

      setCurrentStage('BUREAU_CHECK');
      const session = await api.getSession(sessionId);
      await api.checkBureau(sessionId, session.applicant_id);
      await api.advancePipeline(sessionId);
      addIntel('success', 'Bureau verification passed');

      setCurrentStage('OFFER_GENERATION');
      const offerResult = await api.generateOffer(sessionId);
      setOffer(offerResult);
      addIntel('success', `Offer generated: ₹${(offerResult.eligible_amount / 100000).toFixed(1)}L`);

      setAiMode('confident');
      setAiStatusText('Decision Locked');
      await new Promise(r => setTimeout(r, 800));
      setShowDecision(true);
    } catch {
      setError('Pipeline execution failed');
    } finally {
      setIsProcessing(false);
    }
  }

  if (error) {
     return <div className="min-h-screen text-red-500 flex items-center justify-center bg-black">{error}</div>;
  }

  return (
    <>
      <Sidebar activePage="session" />
      <Topbar sessionId={sessionId} currentStage={currentStage} status={status} />
      <canvas ref={canvasRef} className="hidden" />

      <main className="min-h-screen pt-16 pl-16 flex bg-[#0B0B0C]">
        {/* Left Column: Progress & State */}
        <div className="w-[300px] flex-shrink-0 border-r border-white/5 bg-[#111113] p-6 flex flex-col gap-8 custom-scrollbar overflow-y-auto">
          <AICore mode={aiMode} statusText={aiStatusText} />
          
          <div>
             <h3 className="text-xs font-bold tracking-widest text-[#71717A] uppercase mb-4">Pipeline Status</h3>
             <Stepper steps={PIPELINE_STAGES} currentStepId={currentStage} />
          </div>

          {Object.keys(fields).length > 0 && (
            <div className="pt-6 border-t border-white/5">
              <h3 className="text-xs font-bold tracking-widest text-[#71717A] uppercase mb-4">Live Memory Cache</h3>
              <div className="space-y-3 relative before:absolute before:inset-y-0 before:-left-3 before:w-px before:bg-white/5">
                 {Object.entries(fields).map(([key, val], index) => (val?.value && (
                   <div key={`${key}-${index}`} className="flex flex-col gap-0.5">
                     <span className="text-[10px] uppercase tracking-wider text-[#A1A1AA]">{key.replace(/_/g, ' ')}</span>
                     <span className="text-sm font-medium text-[#EAEAEA]">{val.value}</span>
                   </div>
                 )))}
              </div>
            </div>
          )}
        </div>

        {/* Center Column: Video & Chat */}
        <div className="flex-1 flex flex-col p-6 min-w-0">
          <VideoPanel videoRef={videoRef} agentMessage={agentMessage} isProcessing={isProcessing} visionData={vision} />
          
          <div className="pt-6">
            <div className="relative">
              <input
                type="text"
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleTextSubmit()}
                placeholder="Provide vocal input or type here..."
                disabled={isProcessing}
                className="w-full bg-[#161618] border border-white/10 rounded-xl pl-6 pr-16 py-4 text-sm text-[#EAEAEA] outline-none focus:border-[#D6B36A] transition-colors"
              />
              <button
                onClick={handleTextSubmit}
                disabled={isProcessing || !textInput.trim()}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-2 rounded-lg bg-[#D6B36A] hover:bg-[#A38A4A] transition-colors disabled:opacity-50"
              >
                {isProcessing ? <span className="spinner border-t-black w-4 h-4" /> : <Send className="w-4 h-4 text-[#0B0B0C]" />}
              </button>
            </div>
          </div>
        </div>

        {/* Right Column: AI Insights Stream */}
        <div className="w-[320px] flex-shrink-0 border-l border-white/5 bg-[#111113] p-6 flex flex-col">
          <h3 className="text-xs font-bold tracking-widest text-[#71717A] uppercase mb-6 flex items-center justify-between">
            <span>Machine Intelligence</span>
            <span className="flex items-center gap-2 text-[10px] font-mono text-[#D6B36A] normal-case bg-[#D6B36A]/10 px-2 py-0.5 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-[#D6B36A] animate-pulse" />
              Live Sync
            </span>
          </h3>
          
          <div className="flex-1 overflow-y-auto space-y-3 pr-2 scrollbar-hide flex flex-col">
            {intelEvents.map((evt, i) => (
              <InsightCard key={`${evt.id}-${i}`} status={evt.status} message={evt.message} timestamp={evt.timestamp} active={i === 0} />
            ))}
            {intelEvents.length === 0 && (
              <p className="text-[#A1A1AA] text-sm text-center pt-10">Awaiting stream events...</p>
            )}
          </div>
        </div>
      </main>

      <DecisionPanel
        visible={showDecision}
        decision={fraud && fraud.score > 60 ? 'REJECTED' : 'APPROVED'}
        loanAmount={offer?.eligible_amount as number}
        interestRate={offer?.interest_rate as number}
        tenure={offer?.default_tenure_months as number}
        emi={offer?.default_emi as number}
        onAccept={() => {
           api.acceptOffer(sessionId).then(() => {
             router.push(`/dashboard/sessions/${sessionId}`);
           });
        }}
        onDecline={() => {
           api.declineOffer(sessionId).then(() => {
             setShowDecision(false);
           });
        }}
        onNegotiate={() => {}}
        isProcessing={isProcessing}
        offerId={offer?.offer_id as string}
      />
    </>
  );
}
