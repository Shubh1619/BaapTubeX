from fastapi import FastAPI, Form
from fastapi.responses import FileResponse
from utils.downloader import download_video
import os

app = FastAPI()

@app.post("/download")
def download_youtube_video(url: str = Form(...), format_code: str = Form("best")):
    try:
        file_path = download_video(url, format_code)
        if os.path.exists(file_path):
            return FileResponse(file_path, filename=os.path.basename(file_path), media_type='application/octet-stream')
        return {"error": "File not found"}
    except Exception as e:
        return {"error": str(e)}
