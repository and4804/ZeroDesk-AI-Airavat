export interface Session {
  id: string;
  token: string;
  status: string;
  created_at: string;
  applicant_name?: string;
  applicant_id?: string;
  device_fingerprint?: string;
  ip_address?: string;
  geolocation?: Record<string, unknown>;
}

export interface TranscriptSegment {
  index: number;
  text: string;
  confidence: number;
  timestamp: string;
}

export interface ExtractedField {
  value: string | null;
  confidence: number;
}

export interface ConsentRecord {
  consent_type: string;
  phrase_detected: string;
  segment_hash: string;
  is_consent: boolean;
  timestamp: string;
}

export interface VisionResult {
  face_detected: boolean;
  is_live: boolean;
  liveness_score: number;
  estimated_age: number | null;
  age_delta: number | null;
  blink_detected: boolean;
  head_pose: { yaw: number; pitch: number; roll: number };
  texture_score: number;
}

export interface LLMAssessment {
  intent_category: string;
  intent_confidence: number;
  risk_persona: string;
  risk_confidence: number;
  reasoning_trace: string[];
  contradictions: Array<{ field1: string; field2: string; description: string; severity: string }>;
  distress_signals: boolean;
  summary: string;
}

export interface FraudScore {
  composite_score: number;
  risk_level: string;
  signals: Record<string, { score: number; detail: string }>;
}

export interface BureauResult {
  credit_score: number;
  active_loans: number;
  dpd_history: number[];
  written_off_accounts: number;
  policy_decision: string;
  policy_explanation: string;
}

export interface LoanOffer {
  offer_id: string;
  eligible_amount: number;
  interest_rate: number;
  default_tenure_months: number;
  default_emi: number;
  emi_table: Array<{
    tenure_months: number;
    emi: number;
    total_payment: number;
    total_interest: number;
  }>;
  status: string;
  negotiation_rounds: number;
}

export interface PipelineState {
  current_stage: string;
  stages_completed: string[];
  stages_failed: string[];
  failure_mode: string | null;
}

export type PipelineStage =
  | 'SESSION_INIT'
  | 'METADATA_CAPTURE'
  | 'STT_ACTIVE'
  | 'FIELD_EXTRACTION'
  | 'CONSENT_CHECK'
  | 'LIVENESS_CHECK'
  | 'LLM_ANALYSIS'
  | 'FRAUD_SCORING'
  | 'BUREAU_CHECK'
  | 'OFFER_GENERATION'
  | 'NEGOTIATION'
  | 'SESSION_COMPLETE'
  | 'SESSION_FAILED';
