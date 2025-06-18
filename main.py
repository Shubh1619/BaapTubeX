from fastapi import FastAPI, Form, Query
from fastapi.responses import FileResponse
from utils.downloader import download_video, get_video_formats
import os

app = FastAPI()


@app.post("/download")
def download_youtube_video(url: str = Form(...), format_code: str = Form("best")):
    try:
        print(f"📥 Received URL: {url}, format: {format_code}")

        # Validate format_code
        available_formats = get_video_formats(url)
        available_ids = [f["format_id"] for f in available_formats]
        print(f"🎞️ Available format IDs: {available_ids}")

        if format_code not in available_ids:
            return {
                "error": f"Invalid format '{format_code}'. Available: {available_ids}"
            }

        file_path = download_video(url, format_code)
        print(f"✅ File path received: {file_path}")

        if os.path.exists(file_path):
            return FileResponse(
                file_path,
                filename=os.path.basename(file_path),
                media_type="application/octet-stream"
            )

        return {"error": "File not found"}
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return {"error": str(e)}


@app.get("/formats")
def list_formats(url: str = Query(...)):
    try:
        return get_video_formats(url)
    except Exception as e:
        return {"error": str(e)}
