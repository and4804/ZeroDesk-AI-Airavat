#!/bin/bash
echo -e "\033[1;36m========================================\033[0m"
echo -e "\033[1;36m Starting AgentFinance Fraud Module Test\033[0m"
echo -e "\033[1;36m========================================\033[0m"

# Move to the backend folder so imports work correctly
cd backend || { echo "[-] Could not find the backend directory. Are you at the project root?"; exit 1; }

echo "[*] Ensuring dependencies (including geopy) are installed..."
pip install -r requirements.txt -q

echo ""
echo "[*] Executing test logic..."

# Run the test using inline python script
python3 -c "
import sys
import os
import uuid

# Ensure backend folder is in Python path for FastAPI
sys.path.insert(0, os.path.dirname(os.path.abspath('.')))

from fastapi.testclient import TestClient
from main import app
from session_store import store

def run_test():
    # Context manager triggers backend lifecycle events (DB init, etc)
    with TestClient(app) as client:
        session_id = str(uuid.uuid4())
        print(f'[*] Initialized mock session_id: {session_id}')
        
        # Programmatically forge all transient backend states that Fraud module requires
        store.create(session_id, {
            'geolocation': {
                'lat': 12.9716,     # Bangalore Latitude
                'lon': 77.5946,     # Bangalore Longitude
                'city': 'Bangalore',
                'is_proxy': False,
                'is_hosting': False
            },
            'extracted_fields': {
                'city': {'value': 'Delhi'}, # Mismatch distance logic (Haversine > 200km)
                'income': {'value': '50000'}, # Contradiction base
                'age': {'value': 45}        # Age mismatch base
            },
            'transcript': [
                {'text': 'I earn 50 thousand and I want a loan of 50 lakhs'} # Regex target contradiction
            ],
            'vision_results': [
                {'estimated_age': 20} # Mismatches the declared age 45
            ],
            'device_fingerprint': 'shortfp1', 
            'webrtc_supported': False,
            'user_agent': 'headless python testing crawler' # Bot detection trigger
        })

        # Test the module
        print('[*] Making API request to /api/fraud/{session_id}/score...')
        response = client.post(f'/api/fraud/{session_id}/score')
        
        if response.status_code == 200:
            data = response.json()
            print('\n' + '='*65)
            print('                 FRAUD SCORE VERIFICATION RESULT                 ')
            print('='*65)
            print(f\" Composite Score : {data.get('composite_score')}\")
            print(f\" Risk Level      : {str(data.get('risk_level')).upper()}\")
            print('\n --- Signals Breakdown ---')
            
            for key, sig in data.get('signals', {}).items():
                print(f\" [{sig.get('score', 0):>3} pts] {key:<28}: {sig.get('detail', '')}\")
            print('='*65 + '\n')
            
        else:
            print(f'[-] API Error: {response.text}')

run_test()
"

cd ..
echo -e "\033[1;32mDone.\033[0m"
