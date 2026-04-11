import base64
import logging
import os
import random
import urllib.request
from collections import deque
from typing import Optional

import cv2
import mediapipe as mp
import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import onnxruntime as ort

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================= AGE MODEL (ONNX) =================
MODEL_URL = "https://github.com/onnx/models/raw/main/validated/vision/body_analysis/age_gender/models/age_googlenet.onnx"
MODEL_PATH = "age_model.onnx"

if not os.path.exists(MODEL_PATH):
    print("Downloading age model...")
    urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
    print("Download complete.")

age_session = ort.InferenceSession(MODEL_PATH)
print("Age model loaded:", MODEL_PATH)

# age_googlenet outputs 8 age-group probabilities
# groups: (0-2), (4-6), (8-12), (15-20), (25-32), (38-43), (48-53), (60-100)
AGE_GROUP_MIDPOINTS = np.array([1, 5, 10, 17, 28, 40, 50, 70], dtype=np.float32)

# ================= APP =================
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ================= MEDIAPIPE =================
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(
    static_image_mode=False,
    max_num_faces=1,
    refine_landmarks=True,
)

# ================= STATE =================
prev_frames = {}
prev_nose_positions = {}
liveness_history = {}
low_liveness_start = {}
frame_counters = {}
session_age = {}
blink_history = {}

LEFT_EYE = [362, 385, 387, 263, 373, 380]
RIGHT_EYE = [33, 160, 158, 133, 153, 144]
NOSE = 1

# ================= MODELS =================
class AnalyzeRequest(BaseModel):
    session_id: str
    frame_b64: str
    declared_age: float
    timestamp: float

# ================= UTILS =================
def decode_frame(frame_b64):
    if "," in frame_b64:
        frame_b64 = frame_b64.split(",")[1]
    img = base64.b64decode(frame_b64)
    arr = np.frombuffer(img, np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if frame is None:
        raise ValueError("Invalid image")
    return frame

def ear_calc(lm, idx, w, h):
    pts = [(int(lm[i].x*w), int(lm[i].y*h)) for i in idx]
    A = np.linalg.norm(np.array(pts[1]) - np.array(pts[5]))
    B = np.linalg.norm(np.array(pts[2]) - np.array(pts[4]))
    C = np.linalg.norm(np.array(pts[0]) - np.array(pts[3]))
    return (A+B)/(2*C) if C else 0

def preprocess_face(face):
    face = cv2.resize(face, (224, 224))
    face = face.astype("float32")
    # model requires BGR mean subtraction
    face[:, :, 0] -= 104.0
    face[:, :, 1] -= 117.0
    face[:, :, 2] -= 123.0
    face = face.transpose(2, 0, 1)  # HWC -> CHW
    face = np.expand_dims(face, axis=0)
    return face

# ================= ENDPOINTS =================
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/api/vision/analyze")
def analyze(req: AnalyzeRequest):
    frame = decode_frame(req.frame_b64)
    h, w = frame.shape[:2]

    sid = req.session_id

    frame_counters[sid] = frame_counters.get(sid, 0) + 1

    if sid not in liveness_history:
        liveness_history[sid] = deque(maxlen=5)

    motion = 0
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if sid in prev_frames:
        diff = cv2.absdiff(prev_frames[sid], gray)
        motion = np.mean(diff)/255.0 * 2.5
    prev_frames[sid] = gray

    texture = min(np.var(gray)/500.0, 1.0)

    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    res = face_mesh.process(rgb)

    blink = 0
    head = 0
    flags = []

    if res.multi_face_landmarks:
        lm = res.multi_face_landmarks[0].landmark

        ear = (ear_calc(lm, LEFT_EYE, w, h) +
               ear_calc(lm, RIGHT_EYE, w, h)) / 2

        blink_history[sid] = blink_history.get(sid, 0)
        if ear < 0.28:
            blink_history[sid] += 1
        else:
            blink_history[sid] = 0

        blink = 1 if blink_history[sid] >= 2 else 0

        nose_x = lm[NOSE].x
        if sid in prev_nose_positions:
            head = abs(nose_x - prev_nose_positions[sid]) * 20
        prev_nose_positions[sid] = nose_x

        head = min(head, 1.0)

        # ==== FACE CROP ====
        xs = [int(l.x*w) for l in lm]
        ys = [int(l.y*h) for l in lm]
        x1, x2 = max(min(xs)-10,0), min(max(xs)+10,w)
        y1, y2 = max(min(ys)-10,0), min(max(ys)+10,h)

        if x2 > x1 and y2 > y1:
            face = frame[y1:y2, x1:x2]
        else:
            face = frame

    else:
        flags.append("no_face")
        face = frame

    # ==== LIVENESS ====
    score = 0.4*motion + 0.2*blink + 0.2*head + 0.2*texture
    liveness_history[sid].append(score)
    avg = float(np.mean(liveness_history[sid]))

    if motion > 0.25 or blink == 1 or head > 0.25:
        liveness_history[sid] = deque([score], maxlen=5)
        avg = score

    if motion < 0.05: flags.append("low_motion")
    if blink == 0: flags.append("no_blink")
    if head < 0.05: flags.append("no_head_movement")

    # ==== AGE (ONNX) ====
    if sid not in session_age:
        session_age[sid] = None

    if frame_counters[sid] % 5 == 0:
        try:
            input_face = preprocess_face(face)

            input_name = age_session.get_inputs()[0].name
            outputs = age_session.run(None, {input_name: input_face})

            probs = np.array(outputs[0]).flatten()

            # softmax to get proper probabilities
            exp_probs = np.exp(probs - np.max(probs))
            probs = exp_probs / exp_probs.sum()

            # weighted sum of age group midpoints (NOT indices)
            raw_age = float(np.sum(probs * AGE_GROUP_MIDPOINTS))

            # smooth with previous prediction for stability
            prev_age = session_age.get(sid)
            if prev_age is not None:
                predicted = int(0.6 * prev_age + 0.4 * raw_age)
            else:
                predicted = int(raw_age)

            session_age[sid] = predicted
            print(f"Age estimation: probs={np.round(probs,3)} raw={raw_age:.1f} final={predicted}")

        except Exception as e:
            print("Age model failed:", e)

    age = session_age[sid] if session_age.get(sid) is not None else 22
    age_diff = abs(age - req.declared_age)

    # ==== FINAL (single normalized response) ====
    status = "LIVE" if avg > 0.45 else "SPOOF"

    response = {
        "liveness_score": float(round(score, 3)),
        "status": status,
        "flags": flags,
        "signals": {
            "motion": float(round(motion, 3)),
            "blink": int(blink),
            "head": float(round(head, 3)),
            "texture": float(round(texture, 3))
        },
        "predicted_age": int(age),
        "age_difference": float(age_diff),
        "frames": int(frame_counters.get(sid, 0))
    }

    return response