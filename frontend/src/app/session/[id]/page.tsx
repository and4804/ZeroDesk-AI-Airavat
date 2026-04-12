'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import * as api from '@/lib/api';

// ──────────────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────────────

type VoiceState = 'idle' | 'speaking' | 'listening' | 'processing';
type ConversationMode = 'interview' | 'chatting' | 'negotiating' | 'complete';

interface ChatMessage {
  role: 'ai' | 'user';
  text: string;
  timestamp: string;
  stage?: string;
}

// ──────────────────────────────────────────────────────────────────
// SpeechRecognition types (Web Speech API)
// ──────────────────────────────────────────────────────────────────

interface SpeechRecognitionEvent {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionResultList {
  length: number;
  item(index: number): SpeechRecognitionResult;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionResult {
  isFinal: boolean;
  length: number;
  item(index: number): SpeechRecognitionAlternative;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionInstance extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
}

const INTERVIEW_LABELS: Record<string, string> = {
  INTERVIEW_GREETING: 'Welcome',
  AWAIT_NAME: 'Your Name',
  AWAIT_AGE: 'Your Age',
  AWAIT_EMPLOYMENT: 'Employment',
  AWAIT_INCOME: 'Income',
  AWAIT_LOAN_PURPOSE: 'Loan Purpose',
  AWAIT_AMOUNT: 'Loan Amount',
  AWAIT_CONSENT: 'Consent',
};

const PIPELINE_STAGES = [
  { key: 'SESSION_INIT',       label: 'Start',     icon: '🔗' },
  { key: 'METADATA_CAPTURE',   label: 'Device',    icon: '📱' },
  { key: 'INTERVIEW_GREETING', label: 'Greeting',  icon: '👋' },
  { key: 'AWAIT_NAME',         label: 'Name',      icon: '🪪' },
  { key: 'AWAIT_AGE',          label: 'Age',       icon: '🎂' },
  { key: 'AWAIT_EMPLOYMENT',   label: 'Job',       icon: '💼' },
  { key: 'AWAIT_INCOME',       label: 'Income',    icon: '💵' },
  { key: 'AWAIT_LOAN_PURPOSE', label: 'Purpose',   icon: '🎯' },
  { key: 'AWAIT_AMOUNT',       label: 'Amount',    icon: '💰' },
  { key: 'AWAIT_CONSENT',      label: 'Consent',   icon: '✅' },
  { key: 'LIVENESS_CHECK',     label: 'Liveness',  icon: '👤' },
  { key: 'LLM_ANALYSIS',       label: 'Analysis',  icon: '🧠' },
  { key: 'FRAUD_SCORING',      label: 'Fraud',     icon: '🛡️' },
  { key: 'BUREAU_CHECK',       label: 'Bureau',    icon: '🏦' },
  { key: 'OFFER_GENERATION',   label: 'Offer',     icon: '💎' },
  { key: 'SESSION_COMPLETE',   label: 'Done',      icon: '🎉' },
];

// ──────────────────────────────────────────────────────────────────
// Component
// ──────────────────────────────────────────────────────────────────

export default function SessionPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const sessionId = params.id as string;
  const token = searchParams.get('token');

  // Core state
  const [status, setStatus] = useState<string>('connecting');
  const [voiceState, setVoiceState] = useState<VoiceState>('idle');
  const [mode, setMode] = useState<ConversationMode>('interview');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [interviewStep, setInterviewStep] = useState(0);
  const [totalSteps, setTotalSteps] = useState(8);
  const [currentStage, setCurrentStage] = useState('SESSION_INIT');

  // Data state
  const [fields, setFields] = useState<Record<string, { value: string; confidence: number }>>({});
  const [consent, setConsent] = useState<{ detected: boolean; phrase?: string } | null>(null);
  const [vision, setVision] = useState<{ liveness: number; age: number | null; isLive: boolean } | null>(null);
  const [fraud, setFraud] = useState<{ score: number; level: string } | null>(null);
  const [offer, setOffer] = useState<Record<string, unknown> | null>(null);
  const [avgConfidence, setAvgConfidence] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);

  // Guardrail banner
  const [guardrail, setGuardrail] = useState<{ off_topic: boolean; redirect_msg?: string } | null>(null);

  // Text fallback
  const [textInput, setTextInput] = useState('');
  const [micEnabled, setMicEnabled] = useState(true);

  // Refs
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const frameCountRef = useRef(0);
  const streamRef = useRef<MediaStream | null>(null);
  const recognitionRef = useRef<SpeechRecognitionInstance | null>(null);
  const isSpeakingRef = useRef(false);
  const shouldListenRef = useRef(true);
  const aiLockedRef = useRef(false);  // HARD LOCK — blocks all mic input while AI is active
  const isInitRef = useRef(false);    // Prevents React strict mode double-init
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);
  // Stable refs for values used inside recognition callbacks — avoids stale closures
  const statusRef = useRef(status);
  const micEnabledRef = useRef(micEnabled);
  const modeRef = useRef<ConversationMode>('interview');  // Synced ref for stale closure fix
  const offerRef = useRef<Record<string, unknown> | null>(null);  // Synced ref for stale closure fix
  const currentStageRef = useRef('SESSION_INIT');  // Synced ref for stale closure fix

  // ──────────────────────────────────────────────────────────────
  // Keep refs synced with state (fixes stale closure in SpeechRecognition callbacks)
  // ──────────────────────────────────────────────────────────────
  useEffect(() => { modeRef.current = mode; }, [mode]);
  useEffect(() => { offerRef.current = offer; }, [offer]);
  useEffect(() => { currentStageRef.current = currentStage; }, [currentStage]);
  useEffect(() => { statusRef.current = status; }, [status]);
  useEffect(() => { micEnabledRef.current = micEnabled; }, [micEnabled]);

  // ──────────────────────────────────────────────────────────────
  // Helpers
  // ──────────────────────────────────────────────────────────────

  function getFingerprint(): string {
    const nav = window.navigator;
    const scr = window.screen;
    const raw = `${nav.userAgent}|${nav.language}|${scr.width}x${scr.height}|${scr.colorDepth}|${new Date().getTimezoneOffset()}`;
    let hash = 0;
    for (let i = 0; i < raw.length; i++) {
      hash = ((hash << 5) - hash) + raw.charCodeAt(i);
      hash |= 0;
    }
    return Math.abs(hash).toString(36) + Date.now().toString(36);
  }

  function addMessage(role: 'ai' | 'user', text: string, stage?: string) {
    setMessages(prev => [...prev, { role, text, timestamp: new Date().toISOString(), stage }]);
  }

  // ──────────────────────────────────────────────────────────────
  // TTS — AI speaks
  // ──────────────────────────────────────────────────────────────

  const speak = useCallback((text: string): Promise<void> => {
    return new Promise((resolve) => {
      if (!('speechSynthesis' in window)) { resolve(); return; }
      window.speechSynthesis.cancel();

      // HARD LOCK
      aiLockedRef.current = true;
      isSpeakingRef.current = true;
      shouldListenRef.current = false;
      setVoiceState('speaking');

      // Kill any active recognition
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch { /* ignore */ }
        recognitionRef.current = null;
      }

      // MUTE mic hardware tracks
      if (streamRef.current) {
        streamRef.current.getAudioTracks().forEach(track => { track.enabled = false; });
      }

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.05;
      utterance.pitch = 1;
      utterance.lang = 'en-US';

      const voices = window.speechSynthesis.getVoices();
      const preferred = voices.find(v => v.name.includes('Google') && v.lang.startsWith('en')) || voices.find(v => v.lang.startsWith('en'));
      if (preferred) utterance.voice = preferred;

      const onFinish = () => {
        isSpeakingRef.current = false;
        setVoiceState('idle');
        // 2-second cooldown, then unlock and resolve
        setTimeout(() => {
          // UN-MUTE mic
          if (streamRef.current) {
            streamRef.current.getAudioTracks().forEach(track => { track.enabled = true; });
          }
          aiLockedRef.current = false;
          shouldListenRef.current = true;
          resolve();
        }, 2000);
      };

      utterance.onend = onFinish;
      utterance.onerror = onFinish;

      window.speechSynthesis.speak(utterance);
    });
  }, []);

  // ──────────────────────────────────────────────────────────────
  // STT — Web Speech API
  // ──────────────────────────────────────────────────────────────

  const startListening = useCallback(() => {
    // All guards use refs — no stale closure risk
    if (!micEnabledRef.current || isSpeakingRef.current || aiLockedRef.current) return;
    if (statusRef.current !== 'active') return;

    const SpeechRecognition = (window as unknown as { SpeechRecognition?: new () => SpeechRecognitionInstance; webkitSpeechRecognition?: new () => SpeechRecognitionInstance }).SpeechRecognition
      || (window as unknown as { webkitSpeechRecognition?: new () => SpeechRecognitionInstance }).webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    if (recognitionRef.current) {
      try { recognitionRef.current.stop(); } catch { /* ignore */ }
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      if (aiLockedRef.current || isSpeakingRef.current) {
        try { recognition.abort(); } catch { /* */ }
        return;
      }
      setVoiceState('listening');
    };

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      if (aiLockedRef.current || isSpeakingRef.current) return;

      let finalTranscript = '';
      for (let i = event.resultIndex; i < event.results.length; i++) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        }
      }
      if (finalTranscript.trim()) {
        try { recognition.stop(); } catch { /* */ }
        handleUserSpeech(finalTranscript.trim());
      }
    };

    recognition.onerror = (event: { error: string }) => {
      const ignoredErrors = ['no-speech', 'aborted'];
      if (!ignoredErrors.includes(event.error)) {
        console.warn('Speech recognition error:', event.error);
      }
      // network errors (Chrome) and no-speech both let onend handle the restart
      if (event.error === 'no-speech' || event.error === 'network') {
        setVoiceState('listening');
        return;
      }
      setVoiceState('idle');
    };

    recognition.onend = () => {
      setVoiceState('idle');
      // Use refs — never reads stale state values
      if (
        shouldListenRef.current &&
        micEnabledRef.current &&
        !isSpeakingRef.current &&
        !aiLockedRef.current &&
        statusRef.current === 'active'
      ) {
        setTimeout(() => {
          if (shouldListenRef.current && !isSpeakingRef.current && !aiLockedRef.current) {
            startListening();
          }
        }, 300);
      }
    };

    recognitionRef.current = recognition;
    try { recognition.start(); } catch { /* already started */ }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ──────────────────────────────────────────────────────────────
  // Process user speech/text
  // ──────────────────────────────────────────────────────────────

  // eslint-disable-next-line react-hooks/exhaustive-deps
  async function handleUserSpeech(text: string) {
    // REJECT if AI is locked (still speaking or in cooldown)
    if (isProcessing || !text.trim() || aiLockedRef.current || isSpeakingRef.current) return;
    setIsProcessing(true);
    setVoiceState('processing');
    shouldListenRef.current = false;

    // Stop mic immediately to prevent picking up TTS
    if (recognitionRef.current) {
      try { recognitionRef.current.abort(); } catch { /* ignore */ }
      recognitionRef.current = null;
    }

    addMessage('user', text, currentStage);

    try {
      // 4. Determine what to do based on current mode (use refs to avoid stale closures)
      const currentMode = modeRef.current;
      const currentOffer = offerRef.current;

      // FAST PATH: During negotiation, check accept/decline keywords IMMEDIATELY
      // before any expensive API calls (extractFields, consent, etc.)
      if (currentMode === 'negotiating' && currentOffer) {
        // Just log the text to backend transcript (non-blocking)
        api.addTextTranscript(sessionId, text).catch(() => {});
        await handleNegotiationMessage(text);
        return; // Skip everything below — fields are already collected
      }

      // 1. Add to backend transcript
      await api.addTextTranscript(sessionId, text);

      // 2. Check for consent
      const consentResult = await api.checkConsent(sessionId, text);
      if (consentResult.consent_detected && consentResult.is_consent) {
        setConsent({ detected: true, phrase: consentResult.record?.phrase_detected });
      }

      // 3. Extract fields
      const extracted = await api.extractFields(sessionId);
      if (extracted.fields) {
        setFields(extracted.fields);
        // Calculate avg confidence
        const vals = Object.values(extracted.fields as Record<string, { value: string; confidence: number }>);
        const filled = vals.filter(v => v?.value);
        if (filled.length > 0) {
          setAvgConfidence(filled.reduce((sum, v) => sum + (v.confidence || 0), 0) / filled.length);
        }
      }

      // 3b. Guardrail — check topic relevance (non-blocking)
      api.checkGuardrail(text).then(gr => {
        if (!gr.is_relevant) {
          setGuardrail({ off_topic: true, redirect_msg: gr.redirect_msg ?? undefined });
          setTimeout(() => setGuardrail(null), 5000);
        } else {
          setGuardrail(null);
        }
      }).catch(() => { /* guardrail is advisory, never block the flow */ });

      if (currentMode === 'interview') {
        await handleInterviewMessage(text);
      } else {
        // General chat at any other stage
        const chatResult = await api.chatWithAI(sessionId, text, currentStage);
        const cleanResponse = cleanAIResponse(chatResult.response);
        addMessage('ai', cleanResponse, currentStage);
        await speak(cleanResponse);
      }
    } catch (err) {
      const errMsg = (err as Error).message;
      setError(errMsg);
      addMessage('ai', 'I had a small hiccup. Could you repeat that?', currentStage);
      await speak('I had a small hiccup. Could you repeat that?');
    } finally {
      setIsProcessing(false);
      shouldListenRef.current = true;
      // Use refs so we never read stale state values
      if (micEnabledRef.current && statusRef.current === 'active' && !aiLockedRef.current) {
        startListening();
      } else if (micEnabledRef.current && statusRef.current === 'active') {
        // AI still in TTS cooldown — poll until unlocked then restart
        const waitForUnlock = setInterval(() => {
          if (!aiLockedRef.current && !isSpeakingRef.current) {
            clearInterval(waitForUnlock);
            startListening();
          }
        }, 300);
        setTimeout(() => clearInterval(waitForUnlock), 12000);
      }
    }
  }

  // Clean AI response — strip any leaked JSON from the response text
  function cleanAIResponse(text: string): string {
    if (!text) return 'Could you tell me more?';
    // If the response contains raw JSON, try to extract just the text part
    const jsonMatch = text.match(/\{\s*"response"\s*:\s*"([^"]+)"/);
    if (jsonMatch) return jsonMatch[1];
    // Strip any JSON objects that leaked into the text
    const cleaned = text.replace(/\{[^}]*"response"[^}]*\}/g, '').trim();
    return cleaned || text;
  }

  // Handle interview-mode messages — simple: extract → next question
  async function handleInterviewMessage(text: string) {
    // Check if consent was just given
    if (consent?.detected || currentStage === 'AWAIT_CONSENT') {
      const consentResult = await api.checkConsent(sessionId, text);
      if (consentResult.consent_detected && consentResult.is_consent) {
        setConsent({ detected: true, phrase: consentResult.record?.phrase_detected });
      }
    }

    // Get next interview question (backend checks which fields are filled)
    const nextQ = await api.interviewNext(sessionId);

    if (nextQ.interview_complete) {
      addMessage('ai', 'Perfect! I have everything I need. Let me process your application now.', 'PROCESSING');
      await speak('Perfect! I have everything I need. Let me process your application now.');
      await runFullPipeline();
      return;
    }

    // If the stage hasn't changed, the field wasn't captured — ask a
    // conversational follow-up instead of repeating the exact same question
    // NOTE: use currentStageRef (not currentStage) to avoid stale closure from SpeechRecognition
    if (nextQ.current_stage === currentStageRef.current) {
      const fieldLabel = nextQ.expected_field?.replace(/_/g, ' ') || 'that';
      const nudge = `I didn't quite catch your ${fieldLabel}. Could you please say it again clearly?`;
      addMessage('ai', nudge, nextQ.current_stage);
      await speak(nudge);
      return;
    }

    // Update progress
    setInterviewStep(nextQ.step);
    setTotalSteps(nextQ.total_steps);
    setCurrentStage(nextQ.current_stage);
    currentStageRef.current = nextQ.current_stage;  // Immediately update ref too

    // Add AI question to transcript so the LLM extractor has full Q&A context
    // e.g. "AI asked: What is your monthly income?" → user says "50000"
    try {
      await api.addTextTranscript(sessionId, `[AI Question: ${nextQ.question}]`);
    } catch { /* non-critical */ }

    // Just speak the next question — clean and simple
    addMessage('ai', nextQ.question, nextQ.current_stage);
    await speak(nextQ.question);
  }

  // Handle negotiation-mode messages
  async function handleNegotiationMessage(text: string) {
    const lower = text.toLowerCase();
    
    // Direct keyword detection for accept/decline (more reliable than LLM intent)
    const acceptPhrases = [
      'i accept', 'accept the offer', 'accept it', 'i agree', 'yes i accept',
      'deal', 'i\'ll take it', 'sounds good', 'let\'s go', 'ok i accept',
      'yes please', 'go ahead', 'i\'m in', 'sure', 'absolutely',
      'yes', 'yeah', 'yep', 'ok', 'okay', 'accept', 'approved',
      'that works', 'perfect', 'let\'s do it', 'i want it', 'take it',
    ];
    const declinePhrases = [
      'i decline', 'no thanks', 'not interested', 'cancel', 'i don\'t want',
      'forget it', 'no deal', 'reject', 'decline', 'pass', 'no way',
      'i refuse', 'not for me', 'nah', 'nope',
    ];
    
    if (acceptPhrases.some(p => lower.includes(p))) {
      await handleAcceptOffer();
      return;
    }
    
    if (declinePhrases.some(p => lower.includes(p))) {
      await handleDecline();
      return;
    }
    
    // Everything else is negotiation — send to negotiate endpoint directly
    try {
      const negResult = await api.negotiateOffer(sessionId, text);
      if (negResult.current_offer) {
        setOffer(negResult.current_offer);
        offerRef.current = negResult.current_offer;
      }
      const response = cleanAIResponse(negResult.response);
      addMessage('ai', response, 'NEGOTIATION');
      await speak(response);
    } catch (e) {
      console.error('[Negotiation] Error:', e);
      // Fallback: use chat endpoint
      const chatResult = await api.chatWithAI(sessionId, text, 'NEGOTIATION');
      const response = cleanAIResponse(chatResult.response);
      addMessage('ai', response, 'NEGOTIATION');
      await speak(response);
    }
  }

  // ──────────────────────────────────────────────────────────────
  // Full pipeline (post-interview)
  // ──────────────────────────────────────────────────────────────

  async function runFullPipeline() {
    setIsProcessing(true);
    try {
      // Step 1: LLM Analysis (non-blocking — pipeline continues even if this fails)
      setCurrentStage('LLM_ANALYSIS');
      try {
        await api.analyzeLLM(sessionId);
      } catch (e) {
        console.error('[Pipeline] LLM analysis failed (continuing):', e);
      }

      // Step 2: Fraud scoring
      setCurrentStage('FRAUD_SCORING');
      try {
        const fraudResult = await api.scoreFraud(sessionId);
        setFraud({ score: fraudResult.composite_score, level: fraudResult.risk_level });
      } catch (e) {
        console.error('[Pipeline] Fraud scoring failed (continuing):', e);
      }

      // Step 3: Bureau check
      setCurrentStage('BUREAU_CHECK');
      try {
        const session = await api.getSession(sessionId);
        const applicantId = session?.applicant_id || sessionId;
        await api.checkBureau(sessionId, applicantId);
      } catch (e) {
        console.error('[Pipeline] Bureau check failed (continuing):', e);
      }

      // Step 4: Offer generation (critical — this must succeed)
      setCurrentStage('OFFER_GENERATION');
      const offerResult = await api.generateOffer(sessionId);
      setOffer(offerResult);

      // Build offer message — NO discount mentioned upfront, only during negotiation
      const amountLakh = (offerResult.eligible_amount / 100000).toFixed(1);
      const emi = Math.round(offerResult.default_emi).toLocaleString();
      const msg = `Great news! Based on your profile, you're eligible for a loan of ${amountLakh} lakh rupees at ${offerResult.interest_rate}% annual interest. Your monthly EMI would be ${emi} rupees for ${offerResult.default_tenure_months} months. Would you like to accept this offer, or would you like to negotiate the terms?`;

      setMode('negotiating');
      setCurrentStage('NEGOTIATION');
      addMessage('ai', msg, 'OFFER_GENERATION');
      await speak(msg);

    } catch (err) {
      console.error('[Pipeline] Critical failure:', err);
      setError((err as Error).message);
      addMessage('ai', 'I encountered an issue processing your application. Let me retry.', currentStage);
      await speak('I encountered an issue processing your application. Let me retry.');
    } finally {
      setIsProcessing(false);
      shouldListenRef.current = true;
      // Use the polling approach to restart mic after AI finishes speaking
      const waitForUnlock = setInterval(() => {
        if (!aiLockedRef.current && !isSpeakingRef.current) {
          clearInterval(waitForUnlock);
          startListening();
        }
      }, 500);
      setTimeout(() => clearInterval(waitForUnlock), 10000);
    }
  }

  // ──────────────────────────────────────────────────────────────
  // Offer actions
  // ──────────────────────────────────────────────────────────────

  async function handleAcceptOffer() {
    setIsProcessing(true);
    try {
      await api.acceptOffer(sessionId);
      setCurrentStage('SESSION_COMPLETE');
      setStatus('completed');
      setMode('complete');
      const msg = 'Congratulations! Your loan has been approved and the offer is accepted. You\'ll receive the documentation shortly. Thank you for banking with us!';
      addMessage('ai', msg, 'SESSION_COMPLETE');
      await speak(msg);

      // Upload & clip-extract session recording (non-blocking, best-effort)
      try {
        const recorder = mediaRecorderRef.current;
        if (recorder && recorder.state !== 'inactive') {
          recorder.stop();
          await new Promise<void>(r => { recorder.onstop = () => r(); setTimeout(r, 800); });
        }
        if (recordedChunksRef.current.length > 0) {
          const blob = new Blob(recordedChunksRef.current, { type: 'video/webm' });
          await api.uploadVideo(sessionId, blob);
          await api.extractVideoClips(sessionId);
        }
      } catch { /* non-critical — session already accepted */ }
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsProcessing(false);
    }
  }

  async function handleDecline() {
    await api.declineOffer(sessionId);
    setStatus('declined');
    setMode('complete');
    const msg = 'I understand. Thank you for your time. You can always start a new session if you change your mind.';
    addMessage('ai', msg, 'SESSION_COMPLETE');
    await speak(msg);
  }

  // ──────────────────────────────────────────────────────────────
  // Frame capture for liveness
  // ──────────────────────────────────────────────────────────────

  const startFrameCapture = useCallback(() => {
    const interval = setInterval(async () => {
      if (!videoRef.current || !canvasRef.current) return;
      const video = videoRef.current;
      const canvas = canvasRef.current;
      canvas.width = 320; canvas.height = 240;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.drawImage(video, 0, 0, 320, 240);
      const dataUrl = canvas.toDataURL('image/jpeg', 0.7);
      const base64 = dataUrl.split(',')[1];
      if (!base64) return;
      try {
        const result = await api.analyzeVision(sessionId, base64, fields.age ? parseInt(fields.age.value) : undefined, frameCountRef.current++);
        setVision({ liveness: result.liveness_score, age: result.estimated_age, isLive: result.is_live });
      } catch { /* vision might not be ready */ }
    }, 4000);
    return () => clearInterval(interval);
  }, [sessionId, fields]);

  // ──────────────────────────────────────────────────────────────
  // Init
  // ──────────────────────────────────────────────────────────────

  useEffect(() => {
    if (isInitRef.current) return;
    isInitRef.current = true;

    // Load voices
    if ('speechSynthesis' in window) {
      window.speechSynthesis.getVoices();
      window.speechSynthesis.onvoiceschanged = () => { window.speechSynthesis.getVoices(); };
    }

    async function init() {
      try {
        setStatus('initializing');

        // Store device metadata
        await api.storeMetadata(sessionId, {
          device_fingerprint: getFingerprint(),
          user_agent: navigator.userAgent,
          screen_resolution: `${screen.width}x${screen.height}`,
          timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
          language: navigator.language,
          platform: navigator.platform,
          webrtc_supported: !!window.RTCPeerConnection,
        });

        await api.advancePipeline(sessionId);

        // Start video/audio
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
          streamRef.current = stream;
          if (videoRef.current) videoRef.current.srcObject = stream;
          // Start background video recording
          try {
            const mimeType = MediaRecorder.isTypeSupported('video/webm;codecs=vp9')
              ? 'video/webm;codecs=vp9' : 'video/webm';
            const recorder = new MediaRecorder(stream, { mimeType });
            recordedChunksRef.current = [];
            recorder.ondataavailable = (e) => {
              if (e.data.size > 0) recordedChunksRef.current.push(e.data);
            };
            recorder.start(1000);
            mediaRecorderRef.current = recorder;
          } catch { /* recording API not available */ }
        } catch {
          console.warn('Camera/mic access denied — running in text-only mode');
          setMicEnabled(false);
        }

        setStatus('active');
        statusRef.current = 'active';   // sync ref immediately — don't wait for re-render
        setCurrentStage('INTERVIEW_GREETING');

        // Get first interview question
        const firstQ = await api.interviewNext(sessionId);
        setInterviewStep(firstQ.step);
        setTotalSteps(firstQ.total_steps);
        setCurrentStage(firstQ.current_stage);
        currentStageRef.current = firstQ.current_stage;  // Sync ref immediately

        // Add AI question to transcript for LLM context
        try {
          await api.addTextTranscript(sessionId, `[AI Question: ${firstQ.question}]`);
        } catch { /* non-critical */ }

        addMessage('ai', firstQ.question, firstQ.current_stage);
        await speak(firstQ.question);

        // Start listening after greeting
        shouldListenRef.current = true;
        startListening();

        // Start frame capture
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
      if (recognitionRef.current) try { recognitionRef.current.stop(); } catch { /* ignore */ }
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // ──────────────────────────────────────────────────────────────
  // Text input handler
  // ──────────────────────────────────────────────────────────────

  function handleTextSubmit() {
    if (!textInput.trim() || isProcessing) return;
    handleUserSpeech(textInput.trim());
    setTextInput('');
  }

  // ──────────────────────────────────────────────────────────────
  // Render
  // ──────────────────────────────────────────────────────────────

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

  const modeLabel = mode === 'interview' ? 'Interview' : mode === 'negotiating' ? 'Negotiation' : mode === 'chatting' ? 'Chatting' : 'Complete';
  const modeClass = `mode-${mode === 'interview' ? 'interview' : mode === 'negotiating' ? 'negotiating' : mode === 'chatting' ? 'chatting' : 'complete'}`;
  const currentStageMeta = PIPELINE_STAGES.find((stage) => stage.key === currentStage);

  return (
    <main className="min-h-screen p-4 max-w-7xl mx-auto">
      <canvas ref={canvasRef} className="hidden" />

      {/* Header */}
      <header className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-bold bg-gradient-to-r from-indigo-400 to-violet-400 bg-clip-text text-transparent">
            AgentFinance AI
          </h1>
          <span className={`mode-indicator ${modeClass}`}>
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />
            {modeLabel}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-500 font-mono">{sessionId.slice(0, 8)}...</span>
        </div>
      </header>

      {/* Interview progress */}
      {mode === 'interview' && (
        <div className="mb-4">
          <div className="flex justify-between items-center mb-2">
            <span className="text-xs text-slate-400">Step {interviewStep} of {totalSteps}: {INTERVIEW_LABELS[currentStage] || currentStage}</span>
            <span className="text-xs text-slate-500">{Math.round(avgConfidence * 100)}% avg confidence</span>
          </div>
          <div className="interview-steps">
            {Array.from({ length: totalSteps }).map((_, i) => (
              <div key={i} className={`interview-step ${i < interviewStep - 1 ? 'interview-step-done' : i === interviewStep - 1 ? 'interview-step-active' : ''}`} />
            ))}
          </div>
        </div>
      )}

      {/* Guardrail banner */}
      {guardrail?.off_topic && (
        <div className="mb-4 flex items-start gap-3 px-4 py-3 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-300 text-sm animate-pulse">
          <span className="text-lg leading-none">⚠️</span>
          <span>{guardrail.redirect_msg || 'Please keep your response relevant to your loan application.'}</span>
          <button onClick={() => setGuardrail(null)} className="ml-auto text-amber-400/60 hover:text-amber-300">✕</button>
        </div>
      )}

      {/* Main layout */}
      <div className="grid lg:grid-cols-3 gap-4">
        {/* Left: Video + Voice + Chat */}
        <div className="lg:col-span-2 space-y-4">
          {/* Video + Voice orb */}
          <div className="grid grid-cols-3 gap-4">
            {/* Video */}
            <div className="col-span-2 video-container aspect-video relative">
              <video ref={videoRef} autoPlay muted playsInline className="w-full h-full object-cover" />
              {vision && (
                <div className="absolute top-3 left-3 glass-card px-3 py-1.5 text-xs">
                  <span className={vision.isLive ? 'text-emerald-400' : 'text-rose-400'}>
                    {vision.isLive ? '● LIVE' : '○ NOT LIVE'}
                  </span>
                  <span className="text-slate-400 ml-2">Score: {(vision.liveness * 100).toFixed(0)}%</span>
                  {vision.age && <span className="text-slate-400 ml-2">Age: ~{vision.age}</span>}
                </div>
              )}
              {fraud && (
                <div className="absolute top-3 right-3 glass-card px-3 py-1.5 text-xs">
                  <span className={`badge badge-${fraud.level}`}>Fraud: {fraud.score.toFixed(0)}</span>
                </div>
              )}
            </div>

            {/* Voice orb */}
            <div className="glass-card flex flex-col items-center justify-center p-4">
              <div className={`voice-orb ${
                voiceState === 'speaking' ? 'voice-orb-speaking' :
                voiceState === 'listening' ? 'voice-orb-listening' :
                voiceState === 'processing' ? 'voice-orb-processing' :
                'voice-orb-idle'
              }`}>
                {voiceState === 'speaking' ? '🔊' :
                 voiceState === 'listening' ? '🎤' :
                 voiceState === 'processing' ? '⚡' : '🤖'}
              </div>
              <p className="text-xs text-slate-400 mt-3 text-center font-medium">
                {voiceState === 'speaking' ? 'AI Speaking...' :
                 voiceState === 'listening' ? 'Listening...' :
                 voiceState === 'processing' ? 'Processing...' :
                 'Ready'}
              </p>
              {voiceState === 'listening' && (
                <div className="waveform mt-2">
                  {Array.from({ length: 7 }).map((_, i) => (
                    <div key={i} className="waveform-bar" />
                  ))}
                </div>
              )}
              {/* Mic toggle */}
              <button
                onClick={() => {
                  const next = !micEnabledRef.current;
                  micEnabledRef.current = next;   // sync ref immediately
                  setMicEnabled(next);
                  if (!next) {
                    // Muting
                    if (recognitionRef.current) {
                      try { recognitionRef.current.stop(); } catch { /* */ }
                    }
                    shouldListenRef.current = false;
                  } else {
                    // Unmuting
                    shouldListenRef.current = true;
                    startListening();
                  }
                }}
                className={`mic-button mt-3 ${micEnabled ? 'mic-button-active' : 'mic-button-muted'}`}
                title={micEnabled ? 'Mute microphone' : 'Unmute microphone'}
              >
                {micEnabled ? '🎤' : '🔇'}
              </button>
            </div>
          </div>

          {/* Chat conversation */}
          <div className="glass-card glow">
            <div className="chat-container" style={{ minHeight: '200px', maxHeight: '400px' }}>
              {messages.map((msg, i) => (
                <div key={i} className={`chat-bubble ${msg.role === 'ai' ? 'chat-bubble-ai' : 'chat-bubble-user'}`}>
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: msg.role === 'ai' ? '#6366f1' : '#94a3b8' }}>
                      {msg.role === 'ai' ? '🤖 AI Advisor' : '👤 You'}
                    </span>
                    <span className="text-[10px] text-slate-600">
                      {new Date(msg.timestamp).toLocaleTimeString()}
                    </span>
                  </div>
                  <p>{msg.text}</p>
                </div>
              ))}
              {isProcessing && (
                <div className="chat-bubble chat-bubble-ai">
                  <div className="flex items-center gap-2">
                    <span className="spinner !w-3 !h-3" /> <span className="text-xs text-slate-400">Thinking...</span>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          </div>

          {/* Text input fallback */}
          {status === 'active' && mode !== 'complete' && (
            <div className="flex gap-3">
              <input
                type="text"
                value={textInput}
                onChange={e => setTextInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleTextSubmit()}
                placeholder={micEnabled ? 'Or type your response here...' : 'Type your response here...'}
                className="flex-1 px-4 py-3 rounded-xl bg-white/5 border border-indigo-500/20 text-white placeholder-slate-500 outline-none focus:border-indigo-500/50"
                disabled={isProcessing}
              />
              <button onClick={handleTextSubmit} disabled={isProcessing || !textInput.trim()} className="btn-primary">
                Send
              </button>
            </div>
          )}

          {/* Offer card (during negotiation) */}
          {offer && mode === 'negotiating' && (
            <div className="glass-card p-6 glow slide-up">
              <h3 className="text-lg font-bold text-white mb-4">
                Your Personalised Loan Offer
                {(offer.negotiation_rounds as number) > 0 && (
                  <span className="text-xs ml-2 px-2 py-1 bg-violet-500/20 text-violet-300 rounded-full">
                    Round {offer.negotiation_rounds as number}
                  </span>
                )}
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                <div className="text-center p-3 rounded-xl bg-indigo-500/10">
                  <div className="text-xs text-slate-400">Amount</div>
                  <div className="text-xl font-bold text-indigo-400">₹{((offer.eligible_amount as number) / 100000).toFixed(1)}L</div>
                </div>
                <div className="text-center p-3 rounded-xl bg-violet-500/10">
                  <div className="text-xs text-slate-400">Interest</div>
                  <div className="text-xl font-bold text-violet-400">{offer.interest_rate as number}%</div>
                  {(offer.negotiation_rounds as number) > 0 && (
                    <div className="text-[10px] text-emerald-400 mt-1">✓ Negotiated</div>
                  )}
                </div>
                <div className="text-center p-3 rounded-xl bg-emerald-500/10">
                  <div className="text-xs text-slate-400">Tenure</div>
                  <div className="text-xl font-bold text-emerald-400">
                    {offer.default_tenure_months as number}mo
                  </div>
                  <div className="text-[10px] text-slate-500 mt-0.5">
                    {((offer.default_tenure_months as number) / 12).toFixed(1)} yrs
                  </div>
                </div>
                <div className="text-center p-3 rounded-xl bg-amber-500/10">
                  <div className="text-xs text-slate-400">EMI / month</div>
                  <div className="text-xl font-bold text-amber-400">₹{Math.round(offer.default_emi as number).toLocaleString()}</div>
                </div>
              </div>

              {/* EMI Table — all tenure options */}
              {(offer.emi_table as Array<{tenure_months: number; tenure_years?: number; emi: number; total_payment: number; total_interest: number}>)?.length > 0 && (
                <div className="mb-4 overflow-x-auto">
                  <table className="data-table text-xs">
                    <thead>
                      <tr>
                        <th>Tenure</th>
                        <th>Monthly EMI</th>
                        <th>Total Payment</th>
                        <th>Total Interest</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(offer.emi_table as Array<{tenure_months: number; tenure_years?: number; emi: number; total_payment: number; total_interest: number}>).map(row => {
                        const isCurrent = row.tenure_months === (offer.default_tenure_months as number);
                        const yrs = row.tenure_years ?? row.tenure_months / 12;
                        return (
                          <tr key={row.tenure_months} className={isCurrent ? 'bg-indigo-500/15 font-semibold' : ''}>
                            <td>
                              {row.tenure_months} mo
                              <span className="text-slate-500 ml-1">({yrs.toFixed(1)} yr)</span>
                              {isCurrent && <span className="ml-1 text-[9px] text-indigo-400 uppercase tracking-wide">current</span>}
                            </td>
                            <td className={isCurrent ? 'text-amber-400' : ''}>
                              ₹{Math.round(row.emi).toLocaleString()}
                            </td>
                            <td>₹{Math.round(row.total_payment).toLocaleString()}</td>
                            <td>₹{Math.round(row.total_interest).toLocaleString()}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  <p className="text-[10px] text-slate-600 mt-1">Max tenure: 84 months (7 years) · Rate floor: see advisor</p>
                </div>
              )}

              <p className="text-xs text-slate-500 mb-4 text-center">💬 Say &quot;extend to 5 years&quot;, &quot;lower the rate&quot;, or &quot;what about 72 months?&quot;</p>
              <div className="flex gap-3">
                <button onClick={handleAcceptOffer} disabled={isProcessing} className="btn-primary flex-1">
                  ✓ Accept Offer
                </button>
                <button onClick={handleDecline} className="btn-secondary flex-1 text-rose-400 hover:border-rose-500/40">
                  ✗ Decline
                </button>
              </div>
            </div>
          )}

          {/* Completed */}
          {mode === 'complete' && status === 'completed' && offer && (
            <div className="glass-card p-6 text-center slide-up">
              <div className="text-4xl mb-3">🎉</div>
              <h3 className="text-xl font-bold text-emerald-400 mb-2">Loan Approved!</h3>
              <p className="text-slate-400 mb-1">Amount: ₹{((offer.eligible_amount as number) / 100000).toFixed(1)} Lakhs at {offer.interest_rate as number}% p.a.</p>
              <p className="text-sm text-slate-500 mb-4">Reference: {(offer.offer_id as string)?.slice(0, 8)}</p>
              <div className="flex gap-3 justify-center flex-wrap">
                <button
                  onClick={() => api.exportTranscript(sessionId).catch(() => {})}
                  className="btn-secondary text-sm"
                >
                  ⬇ Download Transcript
                </button>
                <a href="/dashboard" className="btn-secondary text-sm">View in Dashboard →</a>
              </div>
            </div>
          )}
        </div>

        {/* Right sidebar */}
        <div className="space-y-4">
          {/* Extracted Fields */}
          {Object.keys(fields).length > 0 && (
            <div className="glass-card p-4 fade-in">
              <h3 className="text-sm font-semibold text-slate-300 mb-3">📋 Extracted Data</h3>
              <div className="space-y-2">
                {Object.entries(fields).map(([key, val]) => (
                  <div key={key}>
                    <div className="flex justify-between items-center text-xs mb-1">
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
                    <div className="confidence-bar">
                      <div
                        className="confidence-bar-fill"
                        style={{
                          width: `${(val?.confidence || 0) * 100}%`,
                          background: (val?.confidence || 0) >= 0.7 ? '#10b981' : (val?.confidence || 0) >= 0.4 ? '#f59e0b' : '#f43f5e',
                        }}
                      />
                    </div>
                  </div>
                ))}
              </div>

              {/* Average confidence */}
              <div className="mt-3 pt-3 border-t border-white/5">
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">Avg Confidence</span>
                  <span className={avgConfidence >= 0.8 ? 'text-emerald-400' : avgConfidence >= 0.5 ? 'text-amber-400' : 'text-rose-400'}>
                    {(avgConfidence * 100).toFixed(0)}%
                    {avgConfidence >= 0.9 && ' 🎁 -1% rate'}
                    {avgConfidence >= 0.8 && avgConfidence < 0.9 && ' 🎁 -0.5% rate'}
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Consent Status */}
          {consent && (
            <div className={`glass-card p-4 fade-in border ${consent.detected ? 'border-emerald-500/30' : 'border-rose-500/30'}`}>
              <h3 className="text-sm font-semibold text-slate-300 mb-2">✅ Consent</h3>
              <div className="flex items-center gap-2">
                <span className={consent.detected ? 'text-emerald-400' : 'text-rose-400'}>
                  {consent.detected ? '✓ Obtained' : '✗ Not yet'}
                </span>
                {consent.phrase && <span className="text-xs text-slate-500">&quot;{consent.phrase}&quot;</span>}
              </div>
            </div>
          )}

          {/* Voice status */}
          <div className="glass-card p-4">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">🎙️ Voice Status</h3>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">Microphone</span>
                <span className={micEnabled ? 'text-emerald-400' : 'text-rose-400'}>
                  {micEnabled ? '● Active' : '○ Muted'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Voice State</span>
                <span className="text-indigo-400 capitalize">{voiceState}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Mode</span>
                <span className={`mode-indicator ${modeClass}`}>{modeLabel}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Stage</span>
                <span className="text-slate-300 text-[10px] font-mono">
                  {currentStageMeta ? `${currentStageMeta.icon} ${currentStageMeta.label}` : currentStage}
                </span>
              </div>
            </div>
          </div>

          {/* Quick help */}
          <div className="glass-card p-4">
            <h3 className="text-sm font-semibold text-slate-300 mb-3">💡 Tips</h3>
            <ul className="space-y-1.5 text-xs text-slate-400">
              <li>• Speak naturally — the AI understands conversational English</li>
              <li>• Ask any question at any time — &quot;What&apos;s an EMI?&quot;</li>
              <li>• Say &quot;I agree&quot; to give consent</li>
              <li>• Say &quot;I accept&quot; to accept the offer</li>
              <li>• Negotiate freely — &quot;Can I get a lower rate?&quot;</li>
            </ul>
          </div>
        </div>
      </div>
    </main>
  );
}
