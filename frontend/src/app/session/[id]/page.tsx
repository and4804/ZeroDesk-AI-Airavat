'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import * as api from '@/lib/api';

const PIPELINE_STAGES = [
  { key: 'SESSION_INIT', label: 'Init', icon: '🔗' },
  { key: 'METADATA_CAPTURE', label: 'Device', icon: '📱' },
  { key: 'STT_ACTIVE', label: 'Listening', icon: '🎤' },
  { key: 'FIELD_EXTRACTION', label: 'Extract', icon: '📋' },
  { key: 'CONSENT_CHECK', label: 'Consent', icon: '✅' },
  { key: 'LIVENESS_CHECK', label: 'Liveness', icon: '👤' },
  { key: 'LLM_ANALYSIS', label: 'Analysis', icon: '🧠' },
  { key: 'FRAUD_SCORING', label: 'Fraud', icon: '🛡️' },
  { key: 'BUREAU_CHECK', label: 'Bureau', icon: '🏦' },
  { key: 'OFFER_GENERATION', label: 'Offer', icon: '💰' },
  { key: 'SESSION_COMPLETE', label: 'Done', icon: '🎉' },
];

export default function SessionPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const sessionId = params.id as string;
  const token = searchParams.get('token');

  // State
  const [status, setStatus] = useState<string>('connecting');
  const [currentStage, setCurrentStage] = useState<string>('SESSION_INIT');
  const [transcript, setTranscript] = useState<Array<{ text: string; timestamp: string }>>([]);
  const [fields, setFields] = useState<Record<string, { value: string; confidence: number }>>({});
  const [consent, setConsent] = useState<{ detected: boolean; phrase?: string } | null>(null);
  const [vision, setVision] = useState<{ liveness: number; age: number | null; isLive: boolean } | null>(null);
  const [fraud, setFraud] = useState<{ score: number; level: string } | null>(null);
  const [offer, setOffer] = useState<Record<string, unknown> | null>(null);
  const [agentMessage, setAgentMessage] = useState('Welcome! I\'m your AI loan advisor. Let me set up your session...');
  const [textInput, setTextInput] = useState('');
  const [isProcessing, setIsProcessing] = useState(false);
  const [negotiationInput, setNegotiationInput] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Refs
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const transcriptEndRef = useRef<HTMLDivElement>(null);
  const frameCountRef = useRef(0);
  const streamRef = useRef<MediaStream | null>(null);

  // Generate device fingerprint
  function getFingerprint(): string {
    const nav = window.navigator;
    const screen = window.screen;
    const raw = `${nav.userAgent}|${nav.language}|${screen.width}x${screen.height}|${screen.colorDepth}|${new Date().getTimezoneOffset()}`;
    let hash = 0;
    for (let i = 0; i < raw.length; i++) {
      const c = raw.charCodeAt(i);
      hash = ((hash << 5) - hash) + c;
      hash |= 0;
    }
    return Math.abs(hash).toString(36) + Date.now().toString(36);
  }

  // Generate canvas hash for device fingerprinting
  function getCanvasHash(): string {
    try {
      const canvas = document.createElement('canvas');
      canvas.width = 200;
      canvas.height = 50;
      const ctx = canvas.getContext('2d');
      if (!ctx) return '';
      ctx.textBaseline = 'top';
      ctx.font = '14px Arial';
      ctx.fillStyle = '#f60';
      ctx.fillRect(125, 1, 62, 20);
      ctx.fillStyle = '#069';
      ctx.fillText('fingerprint', 2, 15);
      ctx.fillStyle = 'rgba(102,204,0,0.7)';
      ctx.fillText('fingerprint', 4, 17);
      const dataUrl = canvas.toDataURL();
      // Simple hash of the last 64 chars
      let h = 0;
      const tail = dataUrl.slice(-64);
      for (let i = 0; i < tail.length; i++) {
        h = ((h << 5) - h) + tail.charCodeAt(i);
        h |= 0;
      }
      return Math.abs(h).toString(36);
    } catch {
      return '';
    }
  }

  // Get browser geolocation (GPS)
  function getBrowserGeo(): Promise<{ lat: number; lng: number } | null> {
    return new Promise((resolve) => {
      if (!navigator.geolocation) {
        resolve(null);
        return;
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => resolve({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
        () => resolve(null),
        { timeout: 5000, maximumAge: 60000 }
      );
    });
  }

  // TTS speak
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

  // Initialize session
  useEffect(() => {
    let heartbeatInterval: ReturnType<typeof setInterval> | null = null;

    async function init() {
      try {
        // Step 1: Validate the tokenised link
        if (!token) {
          setError('No session token provided. Please use a valid session link.');
          setStatus('error');
          return;
        }

        setStatus('validating');
        try {
          await api.validateSession(sessionId, token);
        } catch {
          setError('Invalid or expired session link. Please request a new one.');
          setStatus('error');
          return;
        }

        // Step 2: Capture device metadata + browser geolocation
        setStatus('initializing');
        const browserGeo = await getBrowserGeo();

        await api.storeMetadata(sessionId, {
          device_fingerprint: getFingerprint(),
          user_agent: navigator.userAgent,
          screen_resolution: `${screen.width}x${screen.height}`,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          language: navigator.language,
          platform: navigator.platform,
          webrtc_supported: !!window.RTCPeerConnection,
          canvas_hash: getCanvasHash(),
          browser_geo_lat: browserGeo?.lat ?? null,
          browser_geo_lng: browserGeo?.lng ?? null,
        });

        // Step 3: Advance pipeline
        await api.advancePipeline(sessionId);
        setCurrentStage('METADATA_CAPTURE');

        // Step 4: Start video (local camera preview)
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
          streamRef.current = stream;
          if (videoRef.current) {
            videoRef.current.srcObject = stream;
          }
        } catch {
          console.warn('Camera/mic access denied — running in text-only mode');
        }

        setStatus('active');
        setCurrentStage('STT_ACTIVE');
        setAgentMessage('Great! Your session is active. Please tell me about yourself — your name, age, employment, income, and the loan you need. You can also type below.');
        speak('Great! Your session is active. Please tell me about yourself. Your name, age, employment, income, and the loan you need.');

        // Step 5: Start frame capture for liveness
        startFrameCapture();

        // Step 6: Start heartbeat (every 30s)
        heartbeatInterval = setInterval(() => {
          api.heartbeat(sessionId).catch(() => {});
        }, 30000);

      } catch (err) {
        setError((err as Error).message);
        setStatus('error');
      }
    }
    init();

    return () => {
      streamRef.current?.getTracks().forEach(t => t.stop());
      window.speechSynthesis?.cancel();
      if (heartbeatInterval) clearInterval(heartbeatInterval);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // Auto-scroll transcript
  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [transcript]);

  // Frame capture for liveness
  const startFrameCapture = useCallback(() => {
    const interval = setInterval(async () => {
      if (!videoRef.current || !canvasRef.current) return;
      const video = videoRef.current;
      const canvas = canvasRef.current;
      canvas.width = 320;
      canvas.height = 240;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.drawImage(video, 0, 0, 320, 240);
      const dataUrl = canvas.toDataURL('image/jpeg', 0.7);
      const base64 = dataUrl.split(',')[1];
      if (!base64) return;

      try {
        const result = await api.analyzeVision(
          sessionId,
          base64,
          fields.age ? parseInt(fields.age.value) : undefined,
          frameCountRef.current++,
        );
        setVision({
          liveness: result.liveness_score,
          age: result.estimated_age,
          isLive: result.is_live,
        });
      } catch {
        // Vision might not be ready yet
      }
    }, 3000);

    return () => clearInterval(interval);
  }, [sessionId, fields]);

  // Handle text input (manual transcript entry)
  async function handleTextSubmit() {
    if (!textInput.trim() || isProcessing) return;
    setIsProcessing(true);

    const text = textInput.trim();
    setTextInput('');
    setTranscript(prev => [...prev, { text, timestamp: new Date().toISOString() }]);

    try {
      // Add to transcript
      await api.addTextTranscript(sessionId, text);

      // Check for consent
      const consentResult = await api.checkConsent(sessionId, text);
      if (consentResult.consent_detected) {
        setConsent({ detected: true, phrase: consentResult.record?.phrase_detected });
        setCurrentStage('CONSENT_CHECK');
      }

      // Try extracting fields
      const extracted = await api.extractFields(sessionId);
      if (extracted.fields) {
        setFields(extracted.fields);
        setCurrentStage('FIELD_EXTRACTION');
      }

      // Check if enough fields for LLM analysis
      const filledFields = Object.values(extracted.fields || {}).filter(
        (f: unknown) => (f as {value: string | null}).value !== null
      ).length;

      if (filledFields >= 3 && !consent?.detected) {
        setAgentMessage('Thank you for sharing that. Before I proceed, I need your verbal consent. Could you please say "I agree" or "Yes, I consent" to continue with the loan application?');
        speak('Thank you. Before I proceed, I need your verbal consent. Could you please say I agree to continue?');
      } else if (filledFields >= 3 && consent?.detected) {
        // Run full pipeline
        await runFullPipeline();
      } else {
        // Get clarification question
        try {
          const clarify = await api.getClarification(sessionId);
          if (clarify.question) {
            setAgentMessage(clarify.question);
            speak(clarify.question);
          }
        } catch {
          setAgentMessage('Please tell me more details — your monthly income, the loan amount you need, and what it\'s for.');
        }
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsProcessing(false);
    }
  }

  // Run full pipeline after consent
  async function runFullPipeline() {
    setIsProcessing(true);
    try {
      // LLM Analysis
      setCurrentStage('LLM_ANALYSIS');
      setAgentMessage('Analyzing your application...');
      await api.analyzeLLM(sessionId);
      await api.advancePipeline(sessionId);

      // Fraud scoring
      setCurrentStage('FRAUD_SCORING');
      setAgentMessage('Running security checks...');
      const fraudResult = await api.scoreFraud(sessionId);
      setFraud({ score: fraudResult.composite_score, level: fraudResult.risk_level });
      await api.advancePipeline(sessionId);

      // Bureau check
      setCurrentStage('BUREAU_CHECK');
      setAgentMessage('Checking your credit profile...');
      const session = await api.getSession(sessionId);
      await api.checkBureau(sessionId, session.applicant_id);
      await api.advancePipeline(sessionId);

      // Offer generation
      setCurrentStage('OFFER_GENERATION');
      setAgentMessage('Preparing your personalised loan offer...');
      const offerResult = await api.generateOffer(sessionId);
      setOffer(offerResult);
      setCurrentStage('OFFER_GENERATION');

      const msg = `Great news! Based on your profile, you're eligible for a loan of ₹${(offerResult.eligible_amount / 100000).toFixed(1)} lakhs at ${offerResult.interest_rate}% interest. Your EMI would be ₹${Math.round(offerResult.default_emi).toLocaleString()} per month for ${offerResult.default_tenure_months} months. Would you like to accept this offer?`;
      setAgentMessage(msg);
      speak(msg);

    } catch (err) {
      setError((err as Error).message);
      setAgentMessage('I encountered an issue processing your application. Let me retry some steps.');
    } finally {
      setIsProcessing(false);
    }
  }

  // Handle offer acceptance
  async function handleAcceptOffer() {
    setIsProcessing(true);
    try {
      await api.acceptOffer(sessionId);
      setCurrentStage('SESSION_COMPLETE');
      setStatus('completed');
      setAgentMessage('Congratulations! Your loan has been approved and the offer is accepted. You\'ll receive the documentation shortly. Thank you for banking with us!');
      speak('Congratulations! Your loan has been approved. Thank you for banking with us!');
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsProcessing(false);
    }
  }

  // Handle negotiation
  async function handleNegotiate() {
    if (!negotiationInput.trim()) return;
    setIsProcessing(true);
    try {
      const result = await api.negotiateOffer(sessionId, negotiationInput);
      setNegotiationInput('');
      if (result.current_offer) {
        setOffer(result.current_offer);
      }
      if (result.response) {
        setAgentMessage(result.response);
        speak(result.response);
      }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsProcessing(false);
    }
  }

  // Handle decline
  async function handleDecline() {
    await api.declineOffer(sessionId);
    setStatus('declined');
    setAgentMessage('I understand. Thank you for your time. You can always start a new session if you change your mind.');
  }

  // Get stage progress
  const stageIndex = PIPELINE_STAGES.findIndex(s => s.key === currentStage);
  const progressPercent = ((stageIndex + 1) / PIPELINE_STAGES.length) * 100;

  if (error && status === 'error') {
    return (
      <div className="min-h-screen flex items-center justify-center p-4">
        <div className="glass-card p-8 max-w-md text-center">
          <div className="text-4xl mb-4">⚠️</div>
          <h2 className="text-xl font-bold text-rose-400 mb-2">Session Error</h2>
          <p className="text-slate-400 mb-4">{error}</p>
          <a href="/" className="btn-primary">Back to Home</a>
        </div>
      </div>
    );
  }

  return (
    <main className="min-h-screen p-4 max-w-7xl mx-auto">
      {/* Hidden canvas for frame capture */}
      <canvas ref={canvasRef} className="hidden" />

      {/* Header */}
      <header className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">
            AgentFinance AI
          </h1>
          <span className="badge badge-active">{status}</span>
        </div>
        <div className="text-xs text-slate-500 font-mono">{sessionId.slice(0, 8)}...</div>
      </header>

      {/* Progress bar */}
      <div className="mb-6">
        <div className="flex justify-between mb-2">
          {PIPELINE_STAGES.map((stage, i) => (
            <div
              key={stage.key}
              className={`text-center flex-1 ${
                i <= stageIndex ? 'text-indigo-400' : 'text-slate-600'
              }`}
            >
              <div className="text-lg">{stage.icon}</div>
              <div className="text-[10px] hidden md:block">{stage.label}</div>
            </div>
          ))}
        </div>
        <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-indigo-500 to-violet-500 rounded-full stage-bar"
            style={{ width: `${progressPercent}%` }}
          />
        </div>
      </div>

      {/* Main layout */}
      <div className="grid lg:grid-cols-3 gap-4">
        {/* Left: Video + Agent */}
        <div className="lg:col-span-2 space-y-4">
          {/* Video */}
          <div className="video-container aspect-video relative">
            <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover" />
            {/* Liveness overlay */}
            {vision && (
              <div className="absolute top-3 left-3 glass-card px-3 py-1.5 text-xs">
                <span className={vision.isLive ? 'text-emerald-400' : 'text-rose-400'}>
                  {vision.isLive ? '● LIVE' : '○ NOT LIVE'}
                </span>
                <span className="text-slate-400 ml-2">Score: {(vision.liveness * 100).toFixed(0)}%</span>
                {vision.age && <span className="text-slate-400 ml-2">Age: ~{vision.age}</span>}
              </div>
            )}
            {/* Fraud score overlay */}
            {fraud && (
              <div className="absolute top-3 right-3 glass-card px-3 py-1.5 text-xs">
                <span className={`badge badge-${fraud.level}`}>
                  Fraud: {fraud.score.toFixed(0)}
                </span>
              </div>
            )}
          </div>

          {/* Agent message */}
          <div className="glass-card p-4 glow">
            <div className="flex items-start gap-3">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 flex items-center justify-center text-sm flex-shrink-0">
                AI
              </div>
              <div>
                <p className="text-sm text-slate-300">{agentMessage}</p>
                {isProcessing && (
                  <div className="flex items-center gap-2 mt-2 text-xs text-indigo-400">
                    <span className="spinner !w-3 !h-3" /> Processing...
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Text input (fallback for STT) */}
          {status === 'active' && !offer && (
            <div className="flex gap-3">
              <input
                type="text"
                value={textInput}
                onChange={(e) => setTextInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleTextSubmit()}
                placeholder="Type your response here (or speak into microphone)..."
                className="flex-1 px-4 py-3 rounded-xl bg-white/5 border border-indigo-500/20 text-white placeholder-slate-500 outline-none focus:border-indigo-500/50"
                disabled={isProcessing}
              />
              <button onClick={handleTextSubmit} disabled={isProcessing} className="btn-primary">
                Send
              </button>
            </div>
          )}

          {/* Offer card */}
          {offer && (
            <div className="glass-card p-6 glow slide-up">
              <h3 className="text-lg font-bold text-white mb-4">Your Personalised Loan Offer</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
                <div className="text-center p-3 rounded-xl bg-indigo-500/10">
                  <div className="text-xs text-slate-400">Amount</div>
                  <div className="text-xl font-bold text-indigo-400">
                    ₹{((offer.eligible_amount as number) / 100000).toFixed(1)}L
                  </div>
                </div>
                <div className="text-center p-3 rounded-xl bg-violet-500/10">
                  <div className="text-xs text-slate-400">Interest</div>
                  <div className="text-xl font-bold text-violet-400">{offer.interest_rate as number}%</div>
                </div>
                <div className="text-center p-3 rounded-xl bg-emerald-500/10">
                  <div className="text-xs text-slate-400">Tenure</div>
                  <div className="text-xl font-bold text-emerald-400">{offer.default_tenure_months as number}mo</div>
                </div>
                <div className="text-center p-3 rounded-xl bg-amber-500/10">
                  <div className="text-xs text-slate-400">EMI</div>
                  <div className="text-xl font-bold text-amber-400">
                    ₹{Math.round(offer.default_emi as number).toLocaleString()}
                  </div>
                </div>
              </div>

              {/* EMI Table */}
              {(offer.emi_table as Array<{tenure_months: number; emi: number; total_payment: number; total_interest: number}>)?.length > 0 && (
                <div className="mb-6 overflow-x-auto">
                  <table className="data-table text-sm">
                    <thead>
                      <tr>
                        <th>Tenure</th>
                        <th>Monthly EMI</th>
                        <th>Total Payment</th>
                        <th>Total Interest</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(offer.emi_table as Array<{tenure_months: number; emi: number; total_payment: number; total_interest: number}>).map((row) => (
                        <tr key={row.tenure_months} className={row.tenure_months === offer.default_tenure_months ? 'bg-indigo-500/10' : ''}>
                          <td>{row.tenure_months} months</td>
                          <td>₹{Math.round(row.emi).toLocaleString()}</td>
                          <td>₹{Math.round(row.total_payment).toLocaleString()}</td>
                          <td>₹{Math.round(row.total_interest).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {/* Negotiation */}
              {status === 'active' && (offer.status === 'generated' || offer.status === undefined) && (
                <>
                  <div className="flex gap-3 mb-4">
                    <input
                      type="text"
                      value={negotiationInput}
                      onChange={(e) => setNegotiationInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && handleNegotiate()}
                      placeholder="Negotiate: 'Can I get a higher amount?' or 'Lower the rate...'"
                      className="flex-1 px-4 py-2 rounded-xl bg-white/5 border border-indigo-500/20 text-white placeholder-slate-500 outline-none focus:border-indigo-500/50 text-sm"
                    />
                    <button onClick={handleNegotiate} disabled={isProcessing} className="btn-secondary text-sm">
                      Negotiate
                    </button>
                  </div>
                  <div className="flex gap-3">
                    <button onClick={handleAcceptOffer} disabled={isProcessing} className="btn-primary flex-1">
                      Accept Offer
                    </button>
                    <button onClick={handleDecline} className="btn-secondary flex-1 text-rose-400 hover:border-rose-500/40">
                      Decline
                    </button>
                  </div>
                </>
              )}

              {status === 'completed' && (
                <div className="text-center p-4 rounded-xl bg-emerald-500/10 border border-emerald-500/30">
                  <div className="text-2xl mb-2">🎉</div>
                  <p className="text-emerald-400 font-semibold">Offer Accepted!</p>
                  <p className="text-sm text-slate-400 mt-1">Reference: {(offer.offer_id as string)?.slice(0, 8)}</p>
                  <a href="/dashboard" className="inline-block mt-3 btn-secondary text-sm">
                    View in Dashboard →
                  </a>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right sidebar */}
        <div className="space-y-4">
          {/* Transcript */}
          <div className="glass-card p-4">
            <h3 className="text-sm font-semibold text-slate-300 mb-3 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              Live Transcript
            </h3>
            <div className="transcript-scroll space-y-2">
              {transcript.length === 0 && (
                <p className="text-xs text-slate-500 italic">Waiting for input...</p>
              )}
              {transcript.map((seg, i) => (
                <div key={i} className="text-xs text-slate-300 p-2 rounded-lg bg-white/[0.03] fade-in">
                  <span className="text-slate-500 text-[10px]">
                    {new Date(seg.timestamp).toLocaleTimeString()}
                  </span>
                  <p>{seg.text}</p>
                </div>
              ))}
              <div ref={transcriptEndRef} />
            </div>
          </div>

          {/* Extracted Fields */}
          {Object.keys(fields).length > 0 && (
            <div className="glass-card p-4 fade-in">
              <h3 className="text-sm font-semibold text-slate-300 mb-3">Extracted Fields</h3>
              <div className="space-y-2">
                {Object.entries(fields).map(([key, val]) => (
                  <div key={key} className="flex justify-between items-center text-xs">
                    <span className="text-slate-400 capitalize">{key.replace(/_/g, ' ')}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-white">{val?.value || '—'}</span>
                      <span className={`px-1.5 py-0.5 rounded text-[10px] ${
                        (val?.confidence || 0) >= 0.7 ? 'bg-emerald-500/20 text-emerald-400' :
                        (val?.confidence || 0) >= 0.4 ? 'bg-amber-500/20 text-amber-400' :
                        'bg-rose-500/20 text-rose-400'
                      }`}>
                        {((val?.confidence || 0) * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Consent Status */}
          {consent && (
            <div className={`glass-card p-4 fade-in border ${consent.detected ? 'border-emerald-500/30' : 'border-rose-500/30'}`}>
              <h3 className="text-sm font-semibold text-slate-300 mb-2">Consent</h3>
              <div className="flex items-center gap-2">
                <span className={consent.detected ? 'text-emerald-400' : 'text-rose-400'}>
                  {consent.detected ? '✓ Obtained' : '✗ Not yet'}
                </span>
                {consent.phrase && (
                  <span className="text-xs text-slate-500">"{consent.phrase}"</span>
                )}
              </div>
            </div>
          )}

          {/* Pipeline Events */}
          <div className="glass-card p-4">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">Pipeline Status</h3>
            <div className="space-y-1.5">
              {PIPELINE_STAGES.map((stage, i) => {
                const isCurrent = stage.key === currentStage;
                const isComplete = i < stageIndex;
                return (
                  <div key={stage.key} className={`flex items-center gap-2 text-xs p-1.5 rounded ${
                    isCurrent ? 'bg-indigo-500/10 text-indigo-400' :
                    isComplete ? 'text-emerald-400' : 'text-slate-600'
                  }`}>
                    <span>{isComplete ? '✓' : isCurrent ? '●' : '○'}</span>
                    <span>{stage.label}</span>
                    {isCurrent && <span className="spinner !w-3 !h-3 ml-auto" />}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
