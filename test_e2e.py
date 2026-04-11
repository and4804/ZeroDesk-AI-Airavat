"""
AgentFinance AI -- End-to-End Test Suite
Tests all 10 tiers of the pipeline with the Priya Sharma (PASS) persona.
"""

import os
import sys
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

import requests
import json
import time

BASE = "http://localhost:8000"
BUREAU = "http://localhost:8001"

PASS_COUNT = 0
FAIL_COUNT = 0
RESULTS = []

def test(name, condition, detail=""):
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        RESULTS.append(("PASS", name))
        print(f"  ✅ {name}")
    else:
        FAIL_COUNT += 1
        RESULTS.append(("FAIL", name, detail))
        print(f"  ❌ {name} — {detail}")


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


# ================================================================
# TIER 1 — Session Management
# ================================================================
section("TIER 1 — Session Management")

# 1a. Create session
r = requests.post(f"{BASE}/api/sessions/create", json={
    "applicant_name": "Priya Sharma",
    "applicant_id": "PRIYA001"
})
test("T1: Create session returns 200", r.status_code == 200, f"Got {r.status_code}")
data = r.json()
SESSION_ID = data.get("session_id", "")
TOKEN = data.get("token", "")
test("T1: Session ID returned", bool(SESSION_ID), "No session_id")
test("T1: JWT token returned", bool(TOKEN), "No token")
test("T1: Join URL returned", "join_url" in data, "No join_url")
print(f"     Session ID: {SESSION_ID[:16]}...")

# 1b. Validate session
r = requests.get(f"{BASE}/api/sessions/{SESSION_ID}/validate?token={TOKEN}")
test("T1: Validate session token", r.status_code == 200, f"Got {r.status_code}")
test("T1: Token is valid", r.json().get("valid") == True)

# 1c. Store metadata (device fingerprint, IP, geolocation)
r = requests.post(f"{BASE}/api/sessions/{SESSION_ID}/metadata", json={
    "device_fingerprint": "test-fp-abc123xyz",
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "screen_resolution": "1920x1080",
    "timezone": "Asia/Kolkata",
    "language": "en-US",
    "platform": "Win32",
    "webrtc_supported": True
})
test("T1: Store metadata returns 200", r.status_code == 200, f"Got {r.status_code}")
meta = r.json()
test("T1: IP captured", "ip" in meta, "No IP in response")
test("T1: Geolocation captured", "geolocation" in meta, "No geolocation")

# 1d. Get session
r = requests.get(f"{BASE}/api/sessions/{SESSION_ID}")
test("T1: Get session returns 200", r.status_code == 200, f"Got {r.status_code}")
sess = r.json()
test("T1: Session status is active", sess.get("status") == "active", f"Status: {sess.get('status')}")

# 1e. List sessions
r = requests.get(f"{BASE}/api/sessions")
test("T1: List sessions returns 200", r.status_code == 200, f"Got {r.status_code}")
test("T1: At least 1 session", len(r.json()) >= 1)


# ================================================================
# TIER 2 — STT & Data Extraction
# ================================================================
section("TIER 2 — STT & Data Extraction")

# 2a. Add text transcript (simulating STT)
sample_transcript = "My name is Priya Sharma. I am 28 years old. I work as a software engineer at Infosys. My monthly salary is 85000 rupees. I want a home improvement loan of 12 lakh rupees. I live in Bangalore."
r = requests.post(f"{BASE}/api/stt/{SESSION_ID}/add-text?text={requests.utils.quote(sample_transcript)}")
test("T2: Add text transcript returns 200", r.status_code == 200, f"Got {r.status_code}: {r.text[:200]}")

# 2b. Get transcript
r = requests.get(f"{BASE}/api/stt/{SESSION_ID}/transcript")
test("T2: Get transcript returns 200", r.status_code == 200, f"Got {r.status_code}")
transcript = r.json()
test("T2: Transcript has segments", len(transcript.get("segments", [])) > 0)
test("T2: Full text is non-empty", bool(transcript.get("full_text")))

# 2c. Extract fields with LLM
r = requests.post(f"{BASE}/api/stt/{SESSION_ID}/extract")
test("T2: Extract fields returns 200", r.status_code == 200, f"Got {r.status_code}")
extraction = r.json()
fields = extraction.get("fields", {})
test("T2: Name field extracted", "name" in fields, f"Fields: {list(fields.keys())}")
test("T2: Fields have confidence scores", 
     any(isinstance(v, dict) and "confidence" in v for v in fields.values()),
     "No confidence scores found")
print(f"     Extracted fields: {list(fields.keys())}")


# ================================================================
# TIER 3 — Consent Capture
# ================================================================
section("TIER 3 — Consent Capture")

# 3a. Check consent (should detect "I agree")
consent_text = "Yes, I agree to proceed with the loan application and I consent to the terms."
r = requests.post(f"{BASE}/api/consent/{SESSION_ID}/check", json={
    "transcript_segment": consent_text
})
test("T3: Consent check returns 200", r.status_code == 200, f"Got {r.status_code}")
consent = r.json()
test("T3: Consent detected", consent.get("consent_detected") == True, f"Detected: {consent.get('consent_detected')}")
test("T3: Is positive consent", consent.get("is_consent") == True)
record = consent.get("record", {})
test("T3: Consent phrase captured", bool(record.get("phrase_detected")))
test("T3: SHA-256 hash generated", bool(record.get("segment_hash")) and len(record.get("segment_hash", "")) == 64)
test("T3: Timestamp recorded", bool(record.get("timestamp")))

# 3b. Get consent record
r = requests.get(f"{BASE}/api/consent/{SESSION_ID}")
test("T3: Get consent returns 200", r.status_code == 200, f"Got {r.status_code}")

# 3c. Export signed consent artifact
r = requests.get(f"{BASE}/api/consent/{SESSION_ID}/export")
test("T3: Export consent artifact returns 200", r.status_code == 200, f"Got {r.status_code}")
artifact = r.json()
test("T3: Artifact has HMAC signature", bool(artifact.get("hmac_signature")))
test("T3: Artifact has transcript hash", bool(artifact.get("transcript_segment_hash")))
test("T3: Artifact is tamper-evident", artifact.get("signature_algorithm") == "HMAC-SHA256")

# 3d. Test opt-out detection
r = requests.post(f"{BASE}/api/consent/{SESSION_ID}/check", json={
    "transcript_segment": "I do not consent to this."
})
test("T3: Opt-out detected", r.json().get("consent_detected") == True and r.json().get("is_consent") == False)


# ================================================================
# TIER 4 — Vision (Liveness & Age)
# ================================================================
section("TIER 4 — Vision (Liveness & Age)")

# 4a. Analyze frame (mock — will use mock handler if MediaPipe unavailable)
import base64
import numpy as np
import cv2

# Create a simple test image (300x300 black with white circle as face)
img = np.zeros((300, 300, 3), dtype=np.uint8)
cv2.circle(img, (150, 150), 80, (200, 200, 200), -1)  # Fake face
_, buffer = cv2.imencode('.jpg', img)
frame_b64 = base64.b64encode(buffer).decode('utf-8')

r = requests.post(f"{BASE}/api/vision/analyze", json={
    "session_id": SESSION_ID,
    "frame_data": frame_b64,
    "declared_age": 28,
    "frame_index": 0
})
test("T4: Vision analyze returns 200", r.status_code == 200, f"Got {r.status_code}")
vision = r.json()
test("T4: Face detection result present", "face_detected" in vision)
test("T4: Liveness score present", "liveness_score" in vision)
test("T4: Estimated age present", "estimated_age" in vision)
test("T4: Model used tracked", bool(vision.get("model_used")))
test("T4: Head pose returned", "head_pose" in vision)
test("T4: Blink detection returned", "blink_detected" in vision)
test("T4: Texture score returned", "texture_score" in vision)
print(f"     Liveness: {vision.get('liveness_score')}, Age: {vision.get('estimated_age')}")

# 4b. Add second frame for summary
r = requests.post(f"{BASE}/api/vision/analyze", json={
    "session_id": SESSION_ID,
    "frame_data": frame_b64,
    "declared_age": 28,
    "frame_index": 1
})
test("T4: Second frame analyze OK", r.status_code == 200)

# 4c. Vision summary
r = requests.get(f"{BASE}/api/vision/{SESSION_ID}/summary")
test("T4: Vision summary returns 200", r.status_code == 200, f"Got {r.status_code}")
summary = r.json()
test("T4: Frame count >= 2", summary.get("frame_count", 0) >= 2)
test("T4: Average liveness computed", "average_liveness" in summary)
test("T4: is_real flag present", "is_real" in summary)


# ================================================================
# TIER 5 — LLM Intelligence Layer
# ================================================================
section("TIER 5 — LLM Intelligence Layer")

# 5a. Run LLM analysis
r = requests.post(f"{BASE}/api/llm/{SESSION_ID}/analyze")
test("T5: LLM analyze returns 200", r.status_code == 200, f"Got {r.status_code}")
llm = r.json().get("assessment", {})
test("T5: Intent category present", bool(llm.get("intent_category")))
test("T5: Intent confidence present", llm.get("intent_confidence") is not None)
test("T5: Risk persona present", bool(llm.get("risk_persona")))
test("T5: Risk confidence present", llm.get("risk_confidence") is not None)
test("T5: Chain-of-thought reasoning trace", isinstance(llm.get("reasoning_trace"), list) and len(llm.get("reasoning_trace", [])) > 0,
     f"Got: {type(llm.get('reasoning_trace'))}")
test("T5: Contradictions field present", "contradictions" in llm)
print(f"     Intent: {llm.get('intent_category')}, Persona: {llm.get('risk_persona')}")

# 5b. Get clarification question
r = requests.post(f"{BASE}/api/llm/{SESSION_ID}/clarify")
test("T5: Clarification returns 200", r.status_code == 200, f"Got {r.status_code}")

# 5c. Get stored assessment
r = requests.get(f"{BASE}/api/llm/{SESSION_ID}/assessment")
test("T5: Get assessment returns 200", r.status_code == 200, f"Got {r.status_code}")


# ================================================================
# TIER 6 — Fraud Signal Detection
# ================================================================
section("TIER 6 — Fraud Signal Detection")

r = requests.post(f"{BASE}/api/fraud/{SESSION_ID}/score")
test("T6: Fraud score returns 200", r.status_code == 200, f"Got {r.status_code}")
fraud = r.json()
test("T6: Composite score 0-100", 0 <= fraud.get("composite_score", -1) <= 100)
test("T6: Risk level assigned", fraud.get("risk_level") in ("low", "medium", "high"))
signals = fraud.get("signals", {})
test("T6: Geo mismatch signal", "geo_mismatch" in signals)
test("T6: Device anomaly signal", "device_anomaly" in signals)
test("T6: Age inconsistency signal", "age_inconsistency" in signals)
test("T6: Transcript contradiction signal", "transcript_contradiction" in signals)
test("T6: Velocity check signal", "velocity_check" in signals)
test("T6: At least 5 signals", len(signals) >= 5, f"Got {len(signals)} signals")
test("T6: Each signal has score", all("score" in s for s in signals.values()))
test("T6: Each signal has detail", all("detail" in s for s in signals.values()))
test("T6: Weights summing to 1.0", abs(sum(fraud.get("weights", {}).values()) - 1.0) < 0.01)
print(f"     Fraud Score: {fraud.get('composite_score')}, Level: {fraud.get('risk_level')}")

# 6b. Get fraud report
r = requests.get(f"{BASE}/api/fraud/{SESSION_ID}")
test("T6: Get fraud report returns 200", r.status_code == 200, f"Got {r.status_code}")


# ================================================================
# TIER 7 — Bureau & Policy Engine
# ================================================================
section("TIER 7 — Bureau Mock & Policy Engine")

# 7a. Test bureau mock directly
r = requests.get(f"{BUREAU}/api/bureau/PRIYA001")
test("T7: Bureau mock PRIYA001 returns 200", r.status_code == 200, f"Got {r.status_code}")
priya = r.json()
test("T7: Priya credit score is 740", priya.get("credit_score") == 740)
test("T7: DPD history returned", isinstance(priya.get("dpd_history"), list))
test("T7: Written-off accounts returned", "written_off_accounts" in priya)
test("T7: Active loans returned", "active_loans" in priya)

r = requests.get(f"{BUREAU}/api/bureau/ROHIT001")
test("T7: Bureau mock ROHIT001", r.status_code == 200 and r.json().get("credit_score") == 420)

r = requests.get(f"{BUREAU}/api/bureau/MEERA001")
test("T7: Bureau mock MEERA001", r.status_code == 200 and r.json().get("credit_score") == 620)

# Name-based lookup
r = requests.get(f"{BUREAU}/api/bureau/priya")
test("T7: Bureau name-based lookup", r.status_code == 200 and r.json().get("credit_score") == 740)

# Unknown applicant (random generation)
r = requests.get(f"{BUREAU}/api/bureau/UNKNOWN999")
test("T7: Bureau unknown applicant generates random", r.status_code == 200 and "credit_score" in r.json())

# 7b. Bureau check through backend (with policy evaluation)
r = requests.post(f"{BASE}/api/bureau/{SESSION_ID}/check", json={
    "applicant_id": "PRIYA001"
})
test("T7: Bureau check returns 200", r.status_code == 200, f"Got {r.status_code}")
bureau = r.json()
test("T7: Bureau data returned", bool(bureau.get("bureau_data")))
test("T7: Policy evaluation returned", bool(bureau.get("policy")))
policy = bureau.get("policy", {})
test("T7: Policy decision present", policy.get("decision") in ("pass", "fail", "refer"), f"Decision: {policy.get('decision')}")
test("T7: Rule evaluations present", len(policy.get("evaluations", [])) > 0)
test("T7: Each rule has explanation", all("explanation" in e for e in policy.get("evaluations", [])))
test("T7: Priya should PASS", policy.get("decision") == "pass", f"Got: {policy.get('decision')}")
print(f"     Decision: {policy.get('decision')}, Rules: {policy.get('rules_passed')}/{policy.get('rules_evaluated')}")


# ================================================================
# TIER 8 — Offer Generation & Negotiation
# ================================================================
section("TIER 8 — Offer Generation & Negotiation")

# 8a. Generate offer
r = requests.post(f"{BASE}/api/offer/{SESSION_ID}/generate")
test("T8: Generate offer returns 200", r.status_code == 200, f"Got {r.status_code}")
offer = r.json()
test("T8: Offer ID generated", bool(offer.get("offer_id")))
test("T8: Eligible amount > 0", (offer.get("eligible_amount") or 0) > 0)
test("T8: Interest rate > 0", (offer.get("interest_rate") or 0) > 0)
test("T8: Default tenure set", (offer.get("default_tenure_months") or 0) > 0)
test("T8: Default EMI calculated", (offer.get("default_emi") or 0) > 0)
test("T8: EMI table with multiple tenures", len(offer.get("emi_table", [])) >= 3)
test("T8: Rate breakdown present", bool(offer.get("rate_breakdown")))
test("T8: EMI table entries have emi/total_payment/total_interest",
     all("emi" in e and "total_payment" in e and "total_interest" in e for e in offer.get("emi_table", [])))
print(f"     Amount: ₹{offer.get('eligible_amount'):,.0f}, Rate: {offer.get('interest_rate')}%, EMI: ₹{offer.get('default_emi'):,.0f}")

# 8b. Negotiate
r = requests.post(f"{BASE}/api/offer/{SESSION_ID}/negotiate", json={
    "objection": "Can I get a lower interest rate?"
})
test("T8: Negotiate returns 200", r.status_code == 200, f"Got {r.status_code}")
neg = r.json()
test("T8: Negotiation response text", bool(neg.get("response")))
test("T8: Round tracking", neg.get("round") == 1)
test("T8: Max rounds set", neg.get("max_rounds") == 3)

# 8c. Accept offer
r = requests.post(f"{BASE}/api/offer/{SESSION_ID}/accept")
test("T8: Accept offer returns 200", r.status_code == 200, f"Got {r.status_code}")
accepted = r.json()
test("T8: Offer status is accepted", accepted.get("status") == "accepted")
test("T8: Accepted timestamp", bool(accepted.get("accepted_at")))


# ================================================================
# TIER 9 — Orchestrator & FSM
# ================================================================
section("TIER 9 — Orchestrator & FSM")

# 9a. Get pipeline state
r = requests.get(f"{BASE}/api/orchestrator/{SESSION_ID}/state")
test("T9: Get pipeline state returns 200", r.status_code == 200, f"Got {r.status_code}")
state = r.json()
test("T9: Current stage present", bool(state.get("current_stage")))
test("T9: Stages completed list", isinstance(state.get("stages_completed"), list))
test("T9: Stages failed list", isinstance(state.get("stages_failed"), list))

# 9b. Get timeline
r = requests.get(f"{BASE}/api/orchestrator/{SESSION_ID}/timeline")
test("T9: Get timeline returns 200", r.status_code == 200, f"Got {r.status_code}")
timeline = r.json()
test("T9: Audit events in timeline", timeline.get("total_events", 0) > 0, f"Events: {timeline.get('total_events')}")

# 9c. List failure modes
r = requests.get(f"{BASE}/api/orchestrator/failure-modes")
test("T9: Failure modes returns 200", r.status_code == 200, f"Got {r.status_code}")
modes = r.json().get("failure_modes", {})
test("T9: At least 5 failure modes defined", len(modes) >= 5, f"Got {len(modes)}")
for fm_id, fm in modes.items():
    test(f"T9: {fm_id} has recovery_path", bool(fm.get("recovery_path")))
    test(f"T9: {fm_id} has escalation_rule", bool(fm.get("escalation_rule")))

# 9d. Test failure reporting
r = requests.post(f"{BASE}/api/orchestrator/{SESSION_ID}/failure", json={
    "failure_mode": "FM-03",
    "details": "Test bureau timeout"
})
test("T9: Failure report returns 200", r.status_code == 200, f"Got {r.status_code}")
test("T9: Recovery instructions returned", bool(r.json().get("recovery_instructions")))


# ================================================================
# TIER 10 — Compliance Dashboard & Audit
# ================================================================
section("TIER 10 — Compliance Dashboard & Audit Reports")

# 10a. List all sessions (compliance view)
r = requests.get(f"{BASE}/api/compliance/sessions")
test("T10: List sessions returns 200", r.status_code == 200, f"Got {r.status_code}")
comp = r.json()
test("T10: Sessions array returned", isinstance(comp.get("sessions"), list))
test("T10: At least 1 session", comp.get("total", 0) >= 1)

# 10b. Session detail (with all tier data)
r = requests.get(f"{BASE}/api/compliance/sessions/{SESSION_ID}")
test("T10: Session detail returns 200", r.status_code == 200, f"Got {r.status_code}")
detail = r.json()
test("T10: Session data present", bool(detail.get("session")))
test("T10: Transcript data present", bool(detail.get("transcript")))
test("T10: Consent data present", isinstance(detail.get("consent"), list))
test("T10: Vision data present", isinstance(detail.get("vision"), list))
test("T10: LLM assessment present", detail.get("llm_assessment") is not None)
test("T10: Fraud data present", detail.get("fraud") is not None)
test("T10: Bureau data present", detail.get("bureau") is not None)
test("T10: Offer data present", detail.get("offer") is not None)
test("T10: Audit events present", isinstance(detail.get("audit_events"), list))
test("T10: Event count > 0", detail.get("event_count", 0) > 0, f"Events: {detail.get('event_count')}")

# 10c. Generate audit report
r = requests.get(f"{BASE}/api/compliance/sessions/{SESSION_ID}/report")
test("T10: Audit report returns 200", r.status_code == 200, f"Got {r.status_code}")
report = r.json()
test("T10: Report type is regulatory_audit", report.get("report_type") == "regulatory_audit")
test("T10: Session reference present", bool(report.get("session_reference")))
test("T10: Transcript hash present", bool(report.get("transcript", {}).get("transcript_hash")))
test("T10: Consent trail present", "consent_trail" in report)
test("T10: Identity verification present", "identity_verification" in report)
test("T10: Risk assessment present", "risk_assessment" in report)
test("T10: Bureau decision trace present", "bureau_decision" in report)
test("T10: Offer terms present", "offer_terms" in report)
test("T10: Pipeline trace present", "pipeline_trace" in report)
test("T10: Audit events in report", len(report.get("audit_events", [])) > 0)
test("T10: Report hash (tamper check)", bool(report.get("report_hash")) and len(report.get("report_hash", "")) == 64)
print(f"     Report hash: {report.get('report_hash', '')[:32]}...")

# 10d. Analytics
r = requests.get(f"{BASE}/api/compliance/analytics")
test("T10: Analytics returns 200", r.status_code == 200, f"Got {r.status_code}")
analytics = r.json()
test("T10: Total sessions count", analytics.get("total_sessions", 0) >= 1)
test("T10: Completion rate present", "completion_rate" in analytics)
test("T10: Fraud distribution present", "fraud_distribution" in analytics)
test("T10: Offer stats present", "offer_stats" in analytics)
test("T10: Pipeline funnel present", "pipeline_funnel" in analytics)
test("T10: Consent stats present", "consent_stats" in analytics)


# ================================================================
# DATA FLOW VALIDATIONS
# ================================================================
section("DATA FLOW — Cross-Tier Validations")

test("FLOW: T1→T2 Session ID consistency", SESSION_ID in str(transcript))
test("FLOW: T2→T3 Transcript feeds consent check", consent.get("consent_detected"))
test("FLOW: T4→T6 Vision feeds fraud (age signal)", "age_inconsistency" in fraud.get("signals", {}))
test("FLOW: T5→T8 LLM feeds offer (risk persona)", bool(offer.get("risk_persona")))
test("FLOW: T6→T7 Fraud feeds bureau policy (fraud gate)", 
     any(e.get("rule") == "fraud_gate" for e in bureau.get("policy", {}).get("evaluations", [])))
test("FLOW: T7→T8 Bureau feeds offer (credit score)", offer.get("credit_score") is not None)
test("FLOW: T8→T10 Offer in compliance report", report.get("offer_terms", {}).get("eligible_amount") is not None)
test("FLOW: T9→T10 Audit events in report", len(report.get("audit_events", [])) > 0)
test("FLOW: T3→T10 Consent artifact in report", "consent_trail" in report)


# ================================================================
# SUMMARY
# ================================================================
section("TEST SUMMARY")
print(f"\n  TOTAL: {PASS_COUNT + FAIL_COUNT} tests")
print(f"  PASSED: {PASS_COUNT} ✅")
print(f"  FAILED: {FAIL_COUNT} ❌")
print(f"  PASS RATE: {PASS_COUNT/(PASS_COUNT+FAIL_COUNT)*100:.1f}%")

if FAIL_COUNT > 0:
    print(f"\n  Failed tests:")
    for r in RESULTS:
        if r[0] == "FAIL":
            print(f"    ❌ {r[1]}: {r[2]}")

print()
sys.exit(0 if FAIL_COUNT == 0 else 1)
