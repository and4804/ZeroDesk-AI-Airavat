import asyncio
from modules.m04_vision import VisionAnalyzeRequest, analyze_frame
import base64
import os
from database import init_db
from session_store import store

async def main():
    await init_db()
    
    # create a mock session
    sid = "test_vision_123"
    store.create(sid, {"status": "TEST"})
    
    # read test frame
    img_path = "mod04/mod04/small.jpg"
    with open(img_path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
        
    req = VisionAnalyzeRequest(
        session_id=sid,
        frame_data=img_b64,
        declared_age=30.0,
        frame_index=1
    )
    
    print("Testing analyze_frame...")
    try:
        res = await analyze_frame(req)
        print("Result:", res)
        print("SUCCESS")
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
