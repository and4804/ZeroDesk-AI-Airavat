const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8000';

export async function apiCall(path: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(error.detail || 'API Error');
  }
  return res.json();
}

export async function createSession(name?: string, applicantId?: string) {
  return apiCall('/api/sessions/create', {
    method: 'POST',
    body: JSON.stringify({ applicant_name: name, applicant_id: applicantId }),
  });
}

export async function getSession(id: string) {
  return apiCall(`/api/sessions/${id}`);
}

export async function storeMetadata(sessionId: string, metadata: Record<string, unknown>) {
  return apiCall(`/api/sessions/${sessionId}/metadata`, {
    method: 'POST',
    body: JSON.stringify(metadata),
  });
}

export async function getTranscript(sessionId: string) {
  return apiCall(`/api/stt/${sessionId}/transcript`);
}

export async function extractFields(sessionId: string) {
  return apiCall(`/api/stt/${sessionId}/extract`, { method: 'POST' });
}

export async function addTextTranscript(sessionId: string, text: string) {
  return apiCall(`/api/stt/${sessionId}/add-text?text=${encodeURIComponent(text)}`, { method: 'POST' });
}

export async function checkConsent(sessionId: string, segment?: string) {
  return apiCall(`/api/consent/${sessionId}/check`, {
    method: 'POST',
    body: JSON.stringify({ transcript_segment: segment }),
  });
}

export async function exportConsent(sessionId: string) {
  return apiCall(`/api/consent/${sessionId}/export`);
}

export async function analyzeVision(sessionId: string, frameData: string, declaredAge?: number, frameIndex?: number) {
  return apiCall('/api/vision/analyze', {
    method: 'POST',
    body: JSON.stringify({
      session_id: sessionId,
      frame_data: frameData,
      declared_age: declaredAge,
      frame_index: frameIndex,
    }),
  });
}

export async function getVisionSummary(sessionId: string) {
  return apiCall(`/api/vision/${sessionId}/summary`);
}

export async function analyzeLLM(sessionId: string) {
  return apiCall(`/api/llm/${sessionId}/analyze`, { method: 'POST' });
}

export async function getClarification(sessionId: string) {
  return apiCall(`/api/llm/${sessionId}/clarify`, { method: 'POST' });
}

export async function scoreFraud(sessionId: string) {
  return apiCall(`/api/fraud/${sessionId}/score`, { method: 'POST' });
}

export async function checkBureau(sessionId: string, applicantId?: string) {
  return apiCall(`/api/bureau/${sessionId}/check`, {
    method: 'POST',
    body: JSON.stringify({ applicant_id: applicantId }),
  });
}

export async function generateOffer(sessionId: string) {
  return apiCall(`/api/offer/${sessionId}/generate`, { method: 'POST' });
}

export async function negotiateOffer(sessionId: string, objection: string) {
  return apiCall(`/api/offer/${sessionId}/negotiate`, {
    method: 'POST',
    body: JSON.stringify({ objection }),
  });
}

export async function acceptOffer(sessionId: string) {
  return apiCall(`/api/offer/${sessionId}/accept`, { method: 'POST' });
}

export async function declineOffer(sessionId: string) {
  return apiCall(`/api/offer/${sessionId}/decline`, { method: 'POST' });
}

export async function advancePipeline(sessionId: string) {
  return apiCall(`/api/orchestrator/${sessionId}/advance`, { method: 'POST' });
}

export async function getPipelineState(sessionId: string) {
  return apiCall(`/api/orchestrator/${sessionId}/state`);
}

export async function getTimeline(sessionId: string) {
  return apiCall(`/api/orchestrator/${sessionId}/timeline`);
}

export async function endSession(sessionId: string) {
  return apiCall(`/api/sessions/${sessionId}/end`, { method: 'POST' });
}

// Dashboard / Compliance
export async function getComplianceSessions() {
  return apiCall('/api/compliance/sessions');
}

export async function getSessionDetail(sessionId: string) {
  return apiCall(`/api/compliance/sessions/${sessionId}`);
}

export async function getAuditReport(sessionId: string) {
  return apiCall(`/api/compliance/sessions/${sessionId}/report`);
}

export async function getAnalytics() {
  return apiCall('/api/compliance/analytics');
}

// STT WebSocket
export function createSTTWebSocket(sessionId: string): WebSocket {
  return new WebSocket(`${WS_BASE}/api/stt/ws/${sessionId}`);
}

export { API_BASE, WS_BASE };
