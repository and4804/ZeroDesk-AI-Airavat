import requests, json, traceback

BASE = "http://localhost:8000"

# Health check first
try:
    r = requests.get(f"{BASE}/health", timeout=3)
    print(f"Health: {r.status_code} {r.json()}")
except Exception as e:
    print(f"Health FAILED: {e}")

# Try the negotiate with a fresh inline approach
try:
    # Create session
    r = requests.post(f"{BASE}/api/sessions/create", json={"applicant_id": "dbg1", "persona": "priya_sharma"}, timeout=5)
    sid = r.json()["session_id"]
    print(f"Session: {sid}")
    
    # Add text
    r = requests.post(f"{BASE}/api/stt/{sid}/add-text", params={"text": "My name is Test age 30 salaried income 80000 home loan 500000"}, timeout=5)
    print(f"Add text: {r.status_code}")
    
    # Generate offer (skip llm/fraud/bureau for simplicity)
    r = requests.post(f"{BASE}/api/offer/{sid}/generate", timeout=15)
    print(f"Offer: {r.status_code}")
    if r.status_code == 200:
        offer = r.json()
        print(f"  rate={offer['interest_rate']}% amount={offer['eligible_amount']}")
    
    # Now negotiate
    print("\nNegotiating...")
    r = requests.post(f"{BASE}/api/offer/{sid}/negotiate", json={"objection": "lower rate"}, timeout=30)
    print(f"Negotiate status: {r.status_code}")
    print(f"Negotiate headers: {dict(r.headers)}")
    print(f"Negotiate body: {r.text[:500]}")
except Exception as e:
    print(f"ERROR: {e}")
    traceback.print_exc()
