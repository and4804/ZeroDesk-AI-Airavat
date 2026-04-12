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

// Interview Flow
export async function interviewNext(sessionId: string) {
  return apiCall(`/api/orchestrator/${sessionId}/interview-next`, { method: 'POST' });
}

export async function interviewStatus(sessionId: string) {
  return apiCall(`/api/orchestrator/${sessionId}/interview-status`);
}

// Free-Form Chat
export async function chatWithAI(sessionId: string, message: string, currentStage?: string) {
  return apiCall(`/api/llm/${sessionId}/chat`, {
    method: 'POST',
    body: JSON.stringify({ message, current_stage: currentStage }),
  });
}

// Guardrail relevance check
export async function checkGuardrail(text: string, nextMissingField?: string): Promise<{
  is_relevant: boolean;
  similarity: number;
  matched_kw: string | null;
  redirect_msg: string | null;
}> {
  return apiCall('/api/guardrails/check', {
    method: 'POST',
    body: JSON.stringify({ text, next_missing_field: nextMissingField }),
  });
}

// Transcript export (triggers browser file download)
export async function exportTranscript(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/stt/${sessionId}/export`);
  if (!res.ok) throw new Error('Export failed');
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `transcript_${sessionId.slice(0, 8)}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

// Video upload (sends raw Blob/File)
export async function uploadVideo(sessionId: string, videoBlob: Blob): Promise<unknown> {
  const form = new FormData();
  form.append('file', videoBlob, 'recording.webm');
  const res = await fetch(`${API_BASE}/api/video/${sessionId}/upload`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Video upload failed');
  }
  return res.json();
}

// Trigger keyword-based clip extraction
export async function extractVideoClips(sessionId: string): Promise<unknown> {
  return apiCall(`/api/video/${sessionId}/extract`, { method: 'POST' });
}

// Audit PDF download (triggers browser download)
export async function downloadAuditPdf(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/compliance/sessions/${sessionId}/report?format=pdf`);
  if (!res.ok) throw new Error('PDF generation failed');
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `audit_report_${sessionId.slice(0, 8)}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

// SSE audit replay — returns EventSource (caller must close it)
export function createReplayEventSource(sessionId: string, delayMs = 600): EventSource {
  return new EventSource(
    `${API_BASE}/api/compliance/sessions/${sessionId}/replay?delay_ms=${delayMs}`,
  );
}

// STT WebSocket
export function createSTTWebSocket(sessionId: string): WebSocket {
  return new WebSocket(`${WS_BASE}/api/stt/ws/${sessionId}`);
}

export { API_BASE, WS_BASE };

