from fastapi import FastAPI, Form, Query, HTTPException, Request
from fastapi.responses import FileResponse
from typing import List, Dict, Optional, Any
import os
import time
from utils.downloader import (
    download_with_retry, 
    get_video_formats, 
    get_best_available_format,
    check_dependencies
)

app = FastAPI(title="YouTube Video Downloader API")

# Simple rate limiting
rate_limit_store = {}
RATE_LIMIT = 5  # requests
RATE_WINDOW = 60  # seconds

def check_rate_limit(client_ip: str) -> bool:
    """Check if the client has exceeded rate limits"""
    current_time = time.time()
    
    # Cleanup old entries
    for ip in list(rate_limit_store.keys()):
        if current_time - rate_limit_store[ip]["timestamp"] > RATE_WINDOW:
            del rate_limit_store[ip]
    
    # Check current IP
    if client_ip in rate_limit_store:
        entry = rate_limit_store[client_ip]
        if current_time - entry["timestamp"] <= RATE_WINDOW:
            if entry["count"] >= RATE_LIMIT:
                return False
            entry["count"] += 1
            return True
    else:
        rate_limit_store[client_ip] = {"count": 1, "timestamp": current_time}
        return True

@app.post("/download")
async def download_youtube_video(
    request: Request,
    url: str = Form(...), 
    format_code: str = Form("best")
):
    """Download a YouTube video with the specified format"""
    # Get client IP
    client_ip = request.client.host
    
    # Check rate limit
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")
    
    try:
        print(f"📥 Received URL: {url}, format: {format_code}")

        # Get available formats
        try:
            available_formats = get_video_formats(url)
            available_ids = [f["format_id"] for f in available_formats]
            print(f"🎞️ Available format IDs: {available_ids}")
        except Exception as e:
            print(f"⚠️ Warning: Could not get formats: {e}")
            available_ids = ["best"]  # Fallback

        # Validate format_code or find closest match
        if format_code not in available_ids:
            # Try to match resolution if format_code looks like a resolution (e.g., "720")
            if format_code.isdigit():
                format_code = get_best_available_format(url, int(format_code))
                print(f"🔄 Using closest available format: {format_code}")
            else:
                format_code = "best"  # Fallback to best

        # Use the retry mechanism with improved audio handling
        file_path = download_with_retry(url, format_code, max_retries=3)
        print(f"✅ File path received: {file_path}")

        if os.path.exists(file_path):
            return FileResponse(
                file_path,
                filename=os.path.basename(file_path),
                media_type="application/octet-stream"
            )

        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/formats", response_model=List[Dict[str, Any]])
async def list_formats(
    request: Request,
    url: str = Query(...)
):
    """Get available video formats for a YouTube URL"""
    # Get client IP
    client_ip = request.client.host
    
    # Check rate limit
    if not check_rate_limit(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please try again later.")
        
    try:
        return get_video_formats(url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/check-dependencies")
async def check_system_dependencies():
    """Check if required dependencies are installed"""
    return check_dependencies()

@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "ok", "version": "1.0.0"}
