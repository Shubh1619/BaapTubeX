from fastapi import FastAPI, Form, Query
from fastapi.responses import FileResponse
from utils.downloader import download_video, get_video_formats
import os

app = FastAPI()

@app.post("/download")
def download_youtube_video(url: str = Form(...), format_code: str = Form("best")):
    try:
        print(f"📥 Received URL: {url}, format: {format_code}")
        file_path = download_video(url, format_code)
        print(f"✅ File path received from yt-dlp: {file_path}")
        if os.path.exists(file_path):
            return FileResponse(file_path, filename=os.path.basename(file_path), media_type='application/octet-stream')
        print("❌ File not found after download")
        return {"error": "File not found"}
    except Exception as e:
        print(f"❌ Exception in download route: {str(e)}")
        return {"error": str(e)}

# ✅ NEW: /formats route
@app.get("/formats")
def list_formats(url: str = Query(...)):
    try:
        formats = get_video_formats(url)
        return formats
    except Exception as e:
        return {"error": str(e)}
