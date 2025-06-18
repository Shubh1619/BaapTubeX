from fastapi import FastAPI, Form
from fastapi.responses import FileResponse
from utils.downloader import download_video
import os

app = FastAPI()

@app.post("/download")
def download_youtube_video(url: str = Form(...), format_code: str = Form("best")):
    try:
        print(f"📥 Received URL: {url}, format: {format_code}")  # 👉 Debug input
        file_path = download_video(url, format_code)
        print(f"✅ File path received from yt-dlp: {file_path}")  # 👉 Confirm download
        if os.path.exists(file_path):
            return FileResponse(file_path, filename=os.path.basename(file_path), media_type='application/octet-stream')
        print("❌ File not found after download")
        return {"error": "File not found"}
    except Exception as e:
        print(f"❌ Exception in download route: {str(e)}")  # 👉 Error log
        return {"error": str(e)}
