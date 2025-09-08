from fastapi import FastAPI, Form, Query, HTTPException, Request, Response, Depends
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Dict, Optional, Any
import os
import time
import uuid
import random
import asyncio
from datetime import datetime
from utils.downloader import (
    download_with_retry, 
    get_video_formats, 
    get_best_available_format,
    check_dependencies,
    normalize_youtube_url
)

app = FastAPI(title="YouTube Video Downloader API")

# CORS middleware to allow requests from browsers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create downloads directory if it doesn't exist
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Mount static files directory if it exists
STATIC_DIR = os.path.join(os.getcwd(), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Simple rate limiting
rate_limit_store = {}
RATE_LIMIT = 5  # requests
RATE_WINDOW = 60  # seconds

# Track suspicious activity
suspicious_ips = {}

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
                # Mark as suspicious if hitting rate limit frequently
                if client_ip not in suspicious_ips:
                    suspicious_ips[client_ip] = 0
                suspicious_ips[client_ip] += 1
                return False
            entry["count"] += 1
            return True
    else:
        rate_limit_store[client_ip] = {"count": 1, "timestamp": current_time}
        return True

def get_client_fingerprint(request: Request) -> str:
    """Generate a client fingerprint to help identify automated requests"""
    headers = request.headers
    ua = headers.get("user-agent", "")
    accept = headers.get("accept", "")
    lang = headers.get("accept-language", "")
    encoding = headers.get("accept-encoding", "")
    return f"{ua}|{accept}|{lang}|{encoding}"

def is_suspicious_client(request: Request) -> bool:
    """Check if client appears to be using automation"""
    client_ip = request.client.host
    
    # Check if IP has hit rate limits before
    if client_ip in suspicious_ips and suspicious_ips[client_ip] > 2:
        return True
        
    # Check for missing or unusual headers
    headers = request.headers
    ua = headers.get("user-agent", "")
    if not ua or len(ua) < 20:
        return True
        
    # Check for common bot fingerprints
    fp = get_client_fingerprint(request)
    suspicious_patterns = ["python", "bot", "curl", "wget", "http-client"]
    return any(pattern in fp.lower() for pattern in suspicious_patterns)

@app.middleware("http")
async def add_request_middleware(request: Request, call_next):
    """Add request tracking and anti-bot measures"""
    request_id = str(uuid.uuid4())
    start_time = time.time()
    
    # Apply small random delay for suspicious clients
    if is_suspicious_client(request):
        delay = random.uniform(1.0, 3.0)
        await asyncio.sleep(delay)
    
    # Process the request
    response = await call_next(request)
    
    # Add timing information
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    response.headers["X-Request-ID"] = request_id
    
    # Add cache control headers to prevent caching
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    
    return response
@app.get("/", response_class=HTMLResponse)
async def root():
    """Simple HTML frontend if no static files are available"""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>YouTube Downloader</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
                line-height: 1.6;
            }
            .container {
                background-color: #f9f9f9;
                border-radius: 10px;
                padding: 20px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }
            input, button, select {
                padding: 10px;
                margin: 10px 0;
                width: 100%;
                box-sizing: border-box;
            }
            button {
                background-color: #ff0000;
                color: white;
                border: none;
                border-radius: 5px;
                cursor: pointer;
                font-weight: bold;
            }
            button:hover {
                background-color: #cc0000;
            }
            #resultArea {
                margin-top: 20px;
                display: none;
            }
            #loadingSpinner {
                display: none;
                text-align: center;
            }
            .error {
                color: #d32f2f;
                background-color: #ffebee;
                padding: 10px;
                border-radius: 5px;
                margin: 10px 0;
                display: none;
            }
            .success {
                color: #388e3c;
                background-color: #e8f5e9;
                padding: 10px;
                border-radius: 5px;
                margin: 10px 0;
            }
            .download-btn {
                background-color: #4caf50;
                color: white;
                text-decoration: none;
                padding: 10px 15px;
                border-radius: 5px;
                display: inline-block;
                text-align: center;
                margin-top: 10px;
            }
            .download-btn:hover {
                background-color: #388e3c;
            }
            .loader {
                border: 5px solid #f3f3f3;
                border-radius: 50%;
                border-top: 5px solid #ff0000;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 20px auto;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>YouTube Downloader</h1>
            <form id="downloadForm">
                <input type="text" id="videoUrl" placeholder="YouTube URL (e.g., https://www.youtube.com/watch?v=...)">
                
                <select id="formatSelect">
                    <option value="best">Best Quality</option>
                    <option value="1080">1080p</option>
                    <option value="720">720p</option>
                    <option value="480">480p</option>
                    <option value="360">360p</option>
                </select>
                
                <button type="submit" id="downloadBtn">Download Video</button>
            </form>
            
            <div id="errorMessage" class="error"></div>
            
            <div id="loadingSpinner">
                <div class="loader"></div>
                <p>Downloading your video... This may take a minute.</p>
            </div>
            
            <div id="resultArea">
                <div class="success">
                    <h3>Download Complete!</h3>
                    <p id="videoTitle"></p>
                    <a id="downloadLink" href="#" class="download-btn">Download Video</a>
                </div>
            </div>
        </div>
        
        <script>
            document.addEventListener('DOMContentLoaded', function() {
                const form = document.getElementById('downloadForm');
                const urlInput = document.getElementById('videoUrl');
                const formatSelect = document.getElementById('formatSelect');
                const loadingSpinner = document.getElementById('loadingSpinner');
                const resultArea = document.getElementById('resultArea');
                const errorMessage = document.getElementById('errorMessage');
                const downloadLink = document.getElementById('downloadLink');
                const videoTitle = document.getElementById('videoTitle');
                
                form.addEventListener('submit', async function(e) {
                    e.preventDefault();
                    
                    // Reset UI
                    errorMessage.style.display = 'none';
                    resultArea.style.display = 'none';
                    
                    const url = urlInput.value.trim();
                    const format = formatSelect.value;
                    
                    if (!url) {
                        showError('Please enter a YouTube URL');
                        return;
                    }
                    
                    if (!isValidYouTubeUrl(url)) {
                        showError('Please enter a valid YouTube URL');
                        return;
                    }
                    
                    // Show loading spinner
                    loadingSpinner.style.display = 'block';
                    
                    try {
                        // Create form data
                        const formData = new FormData();
                        formData.append('url', url);
                        formData.append('format_code', format);
                        
                        // Send request
                        const response = await fetch('/download', {
                            method: 'POST',
                            body: formData
                        });
                        
                        if (!response.ok) {
                            const errorData = await response.text();
                            throw new Error(errorData || 'Failed to download video');
                        }
                        
                        // Get the blob data
                        const blob = await response.blob();
                        
                        // Create a download link
                        const filename = getFilenameFromResponse(response) || 'youtube_video.mp4';
                        const downloadUrl = URL.createObjectURL(blob);
                        
                        // Update UI
                        downloadLink.href = downloadUrl;
                        downloadLink.download = filename;
                        videoTitle.textContent = filename;
                        
                        // Hide loading, show result
                        loadingSpinner.style.display = 'none';
                        resultArea.style.display = 'block';
                        
                    } catch (error) {
                        loadingSpinner.style.display = 'none';
                        showError(error.message || 'An error occurred during download');
                    }
                });
                
                function showError(message) {
                    errorMessage.textContent = message;
                    errorMessage.style.display = 'block';
                }
                
                function isValidYouTubeUrl(url) {
                    // Basic YouTube URL validation
                    return url.match(/^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be)\/.+/);
                }
                
                function getFilenameFromResponse(response) {
                    // Try to get filename from Content-Disposition header
                    const contentDisposition = response.headers.get('Content-Disposition');
                    if (contentDisposition) {
                        const match = contentDisposition.match(/filename="?([^"]+)"?/);
                        if (match && match[1]) {
                            return match[1];
                        }
                    }
                    // Try to get from content type
                    const contentType = response.headers.get('Content-Type');
                    if (contentType && contentType.includes('video/')) {
                        return 'youtube_video.mp4';
                    }
                    return null;
                }
            });
        </script>
    </body>
    </html>
    """
    return html_content

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
        # Normalize and validate URL
        url = normalize_youtube_url(url)
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

# Cleanup task to remove old downloads
@app.on_event("startup")
async def setup_periodic_cleanup():
    """Set up a task to clean up old downloads periodically"""
    async def cleanup_old_files():
        while True:
            try:
                # Delete files older than 2 hours
                now = time.time()
                count = 0
                for filename in os.listdir(DOWNLOAD_DIR):
                    file_path = os.path.join(DOWNLOAD_DIR, filename)
                    if os.path.isfile(file_path) and now - os.path.getmtime(file_path) > 7200:  # 2 hours
                        os.remove(file_path)
                        count += 1
                if count > 0:
                    print(f"🧹 Cleaned up {count} old files")
            except Exception as e:
                print(f"⚠️ Cleanup error: {e}")
                
            # Sleep for 30 minutes
            await asyncio.sleep(1800)
    
    # Start the cleanup task
    asyncio.create_task(cleanup_old_files())

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
