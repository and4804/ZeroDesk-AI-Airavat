"""
M04 — Liveness Detection & Age Estimation
Uses MediaPipe Face Mesh for liveness (temporal: motion, blink, head tracking)
and ONNX age_googlenet for age estimation.
"""

import base64
import json
import os
import numpy as np
import cv2
from collections import deque
from datetime import datetime
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from config import settings
from database import get_db
from session_store import store
from events import audit

router = APIRouter(prefix="/api/vision", tags=["M04 - Vision"])

# ──────────────────────────────────────────────────────────────────
# Lazy-loaded models
# ──────────────────────────────────────────────────────────────────
_face_mesh = None
_age_session = None

# Eye landmark indices (MediaPipe 468-point mesh)
LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
NOSE = 1

# age_googlenet outputs 8 age-group probabilities
AGE_GROUP_MIDPOINTS = np.array([1, 5, 10, 17, 28, 40, 50, 70], dtype=np.float32)

# ──────────────────────────────────────────────────────────────────
# Per-session temporal state (for motion/blink/head tracking)
# ──────────────────────────────────────────────────────────────────
_prev_frames = {}
_prev_nose_positions = {}
_liveness_history = {}
_frame_counters = {}
_session_age = {}
_blink_history = {}


def _get_face_mesh():
    global _face_mesh
    if _face_mesh is None:
        try:
            import mediapipe as mp
            _face_mesh = mp.solutions.face_mesh.FaceMesh(
                static_image_mode=False,  # Temporal mode for better tracking
                max_num_faces=1,
                refine_landmarks=True,
            )
            print("[OK] MediaPipe Face Mesh loaded (temporal mode)")
        except Exception as e:
            print(f"[WARN] MediaPipe load failed: {e}")
            _face_mesh = "mock"
    return _face_mesh


def _get_age_session():
    """Load the ONNX age estimation model (age_googlenet)."""
    global _age_session
    if _age_session is None:
        try:
            import onnxruntime as ort
            model_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "age_model.onnx")
            if not os.path.exists(model_path):
                print(f"[WARN] ONNX age model not found at {model_path}")
                _age_session = "mock"
                return _age_session
            _age_session = ort.InferenceSession(model_path)
            print(f"[OK] ONNX age model loaded: {model_path}")
        except Exception as e:
            print(f"[WARN] ONNX age model load failed: {e}")
            _age_session = "mock"
    return _age_session


# ──────────────────────────────────────────────────────────────────
# Utility functions
# ──────────────────────────────────────────────────────────────────

def _ear_calc(landmarks, eye_indices, w, h):
    """Compute Eye Aspect Ratio (EAR) for blink detection."""
    try:
        pts = [(int(landmarks[i].x * w), int(landmarks[i].y * h)) for i in eye_indices]
        A = np.linalg.norm(np.array(pts[1]) - np.array(pts[5]))
        B = np.linalg.norm(np.array(pts[2]) - np.array(pts[4]))
        C = np.linalg.norm(np.array(pts[0]) - np.array(pts[3]))
        return (A + B) / (2 * C) if C else 0
    except Exception:
        return 0.3  # Default


def _preprocess_face_for_age(face_crop):
    """Preprocess a face crop for the age_googlenet ONNX model."""
    face = cv2.resize(face_crop, (224, 224))
    face = face.astype("float32")
    # Model requires BGR mean subtraction
    face[:, :, 0] -= 104.0
    face[:, :, 1] -= 117.0
    face[:, :, 2] -= 123.0
    face = face.transpose(2, 0, 1)  # HWC -> CHW
    face = np.expand_dims(face, axis=0)
    return face


def _estimate_age_onnx(face_crop, sid):
    """Estimate age from a face crop using the ONNX model."""
    age_sess = _get_age_session()
    if age_sess == "mock":
        return None

    try:
        input_face = _preprocess_face_for_age(face_crop)
        input_name = age_sess.get_inputs()[0].name
        outputs = age_sess.run(None, {input_name: input_face})

        probs = np.array(outputs[0]).flatten()
        # Softmax for proper probabilities
        exp_probs = np.exp(probs - np.max(probs))
        probs = exp_probs / exp_probs.sum()

        # Weighted sum of age group midpoints
        raw_age = float(np.sum(probs * AGE_GROUP_MIDPOINTS))

        # Smooth with previous prediction for stability
        prev_age = _session_age.get(sid)
        if prev_age is not None:
            predicted = int(0.6 * prev_age + 0.4 * raw_age)
        else:
            predicted = int(raw_age)

        _session_age[sid] = predicted
        return predicted
    except Exception as e:
        print(f"[WARN] ONNX age estimation failed: {e}")
        return None


# ──────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────

class VisionAnalyzeRequest(BaseModel):
    session_id: str
    frame_data: Optional[str] = None  # base64 JPEG (current frontend sends this)
    frame_b64: Optional[str] = None   # base64 JPEG (mod04 standalone sends this)
    declared_age: Optional[float] = None
    frame_index: Optional[int] = 0
    timestamp: Optional[float] = None


# ──────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze_frame(req: VisionAnalyzeRequest):
    """
    Analyze a video frame for:
    - Face detection
    - Temporal liveness (motion diff, blink tracking, head movement, texture)
    - Age estimation (ONNX age_googlenet)
    """
    sid = req.session_id
    session = store.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Accept either frame_data or frame_b64
    raw_b64 = req.frame_data or req.frame_b64
    if not raw_b64:
        raise HTTPException(status_code=400, detail="No frame data provided")

    # Decode frame
    try:
        # Strip data URL prefix if present
        if "," in raw_b64:
            raw_b64 = raw_b64.split(",")[1]
        img_bytes = base64.b64decode(raw_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            raise ValueError("Failed to decode image")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid frame data: {e}")

    h, w = img.shape[:2]

    # Increment frame counter
    _frame_counters[sid] = _frame_counters.get(sid, 0) + 1
    if sid not in _liveness_history:
        _liveness_history[sid] = deque(maxlen=5)

    # ── TEMPORAL LIVENESS SIGNALS ──

    # 1. Motion detection (frame differencing)
    motion = 0.0
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if sid in _prev_frames:
        diff = cv2.absdiff(_prev_frames[sid], gray)
        motion = float(np.mean(diff) / 255.0 * 2.5)
    _prev_frames[sid] = gray

    # 2. Texture variance (anti-spoofing)
    texture = min(float(np.var(gray) / 500.0), 1.0)

    # 3. Face mesh analysis
    blink = 0
    head = 0.0
    flags = []
    face_detected = False
    face_crop = img  # Fallback
    head_pose = {"yaw": 0, "pitch": 0, "roll": 0}

    face_mesh = _get_face_mesh()

    if face_mesh != "mock":
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        results = face_mesh.process(rgb)

        if results.multi_face_landmarks:
            lm = results.multi_face_landmarks[0].landmark
            face_detected = True

            # EAR blink detection
            ear = (_ear_calc(lm, LEFT_EYE, w, h) + _ear_calc(lm, RIGHT_EYE, w, h)) / 2
            _blink_history[sid] = _blink_history.get(sid, 0)
            if ear < 0.28:
                _blink_history[sid] += 1
            else:
                _blink_history[sid] = 0
            blink = 1 if _blink_history[sid] >= 2 else 0

            # Head movement (nose tracking)
            nose_x = lm[NOSE].x
            if sid in _prev_nose_positions:
                head = abs(nose_x - _prev_nose_positions[sid]) * 20
            _prev_nose_positions[sid] = nose_x
            head = min(head, 1.0)

            # Head pose estimation
            nose = lm[1]
            left_eye = lm[33]
            right_eye = lm[263]
            yaw = (nose.x - 0.5) * 60
            pitch = (nose.y - 0.5) * 60
            roll = float(np.degrees(np.arctan2(
                right_eye.y - left_eye.y,
                right_eye.x - left_eye.x,
            )))
            head_pose = {"yaw": round(yaw, 2), "pitch": round(pitch, 2), "roll": round(roll, 2)}

            # Face crop for age estimation
            xs = [int(l.x * w) for l in lm]
            ys = [int(l.y * h) for l in lm]
            x1, x2 = max(min(xs) - 10, 0), min(max(xs) + 10, w)
            y1, y2 = max(min(ys) - 10, 0), min(max(ys) + 10, h)
            if x2 > x1 and y2 > y1:
                face_crop = img[y1:y2, x1:x2]
        else:
            flags.append("no_face")
    else:
        # Mock mode — simulate signals
        face_detected = True
        motion = 0.3
        texture = 0.5
        blink = 1
        head = 0.2

    # ── LIVENESS SCORE ──
    score = 0.4 * motion + 0.2 * blink + 0.2 * head + 0.2 * texture
    _liveness_history[sid].append(score)
    avg_score = float(np.mean(_liveness_history[sid]))

    # Boost on significant activity (prevents slow decay)
    if motion > 0.25 or blink == 1 or head > 0.25:
        _liveness_history[sid] = deque([score], maxlen=5)
        avg_score = score

    # Flags
    if motion < 0.05:
        flags.append("low_motion")
    if blink == 0:
        flags.append("no_blink")
    if head < 0.05:
        flags.append("no_head_movement")

    is_live = avg_score > 0.45
    status = "LIVE" if is_live else "SPOOF"

    # ── AGE ESTIMATION (ONNX, every 5th frame) ──
    estimated_age = _session_age.get(sid)
    if _frame_counters[sid] % 5 == 0:
        age_result = _estimate_age_onnx(face_crop, sid)
        if age_result is not None:
            estimated_age = age_result

    if estimated_age is None:
        estimated_age = int(req.declared_age) if req.declared_age else None

    # Age delta
    age_delta = None
    if estimated_age is not None and req.declared_age is not None:
        age_delta = abs(estimated_age - req.declared_age)

    # ── BUILD RESULT ──
    result = {
        "session_id": sid,
        "frame_index": req.frame_index or 0,
        "face_detected": face_detected,
        "is_live": is_live,
        "liveness_score": round(avg_score, 3),
        "status": status,
        "estimated_age": estimated_age,
        "predicted_age": estimated_age,  # mod04 compat
        "age_delta": round(age_delta, 1) if age_delta is not None else None,
        "age_difference": round(age_delta, 1) if age_delta is not None else None,  # mod04 compat
        "blink_detected": blink == 1,
        "head_pose": head_pose,
        "texture_score": round(texture * 500, 1),  # Scale back for compat
        "signals": {
            "motion": round(motion, 3),
            "blink": int(blink),
            "head": round(head, 3),
            "texture": round(texture, 3),
        },
        "flags": flags,
        "frames": int(_frame_counters.get(sid, 0)),
        "model_used": ["mediapipe_face_mesh", "onnx_age_googlenet"] if face_mesh != "mock" else ["mock"],
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Store result in session
    store.append_vision(sid, result)

    # Persist to DB
    try:
        db = await get_db()
        try:
            await db.execute(
                """INSERT INTO vision_results
                   (session_id, frame_index, is_live, liveness_score, estimated_age,
                    face_detected, blink_detected, head_pose, texture_score, model_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sid,
                    req.frame_index or 0,
                    1 if is_live else 0,
                    result["liveness_score"],
                    estimated_age,
                    1 if face_detected else 0,
                    1 if blink == 1 else 0,
                    json.dumps(head_pose),
                    result["texture_score"],
                    json.dumps(result["model_used"]),
                ),
            )
            await db.commit()
        finally:
            await db.close()
    except Exception:
        pass

    # Audit
    await audit.emit(sid, "VISION_ANALYZED", "VISION", {
        "frame_index": req.frame_index,
        "face_detected": face_detected,
        "is_live": is_live,
        "liveness_score": result["liveness_score"],
        "estimated_age": estimated_age,
        "status": status,
    })

    return result


@router.get("/{session_id}/summary")
async def get_vision_summary(session_id: str):
    """Get rolling liveness average and all vision results for a session."""
    session = store.get(session_id)
    vision_results = session.get("vision_results", []) if session else []

    if not vision_results:
        db = await get_db()
        try:
            cursor = await db.execute(
                "SELECT * FROM vision_results WHERE session_id = ? ORDER BY frame_index",
                (session_id,),
            )
            rows = await cursor.fetchall()
            vision_results = [dict(row) for row in rows]
        finally:
            await db.close()

    if not vision_results:
        return {"session_id": session_id, "frame_count": 0, "average_liveness": 0}

    scores = [r.get("liveness_score", 0) for r in vision_results]
    live_count = sum(1 for r in vision_results if r.get("is_live"))
    ages = [r.get("estimated_age") for r in vision_results if r.get("estimated_age") is not None]

    return {
        "session_id": session_id,
        "frame_count": len(vision_results),
        "average_liveness": round(sum(scores) / len(scores), 3) if scores else 0,
        "live_frame_ratio": round(live_count / len(vision_results), 3) if vision_results else 0,
        "average_estimated_age": round(sum(ages) / len(ages), 1) if ages else None,
        "is_real": (live_count / len(vision_results)) >= 0.5 if vision_results else False,
        "latest": vision_results[-1] if vision_results else None,
    }
