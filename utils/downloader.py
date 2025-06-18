import os
import yt_dlp

def download_video(url: str, format_code: str = "best") -> str:
    download_dir = "downloads"
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    cookies_path = os.path.abspath("cookies.txt")
    print("👉 Using cookie file:", cookies_path)

    if not os.path.exists(cookies_path):
        print("🚨 cookies.txt NOT FOUND at:", cookies_path)
    else:
        print("✅ cookies.txt FOUND. Size:", os.path.getsize(cookies_path), "bytes")

    ydl_opts = {
        'format': format_code,
        'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
        'cookiefile': cookies_path,
        'quiet': False,
        'verbose': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept-Language': 'en-US,en;q=0.9'
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return filename
    except Exception as e:
        print("❌ yt-dlp error:", str(e))
        raise e


# ✅ NEW: List formats
def get_video_formats(url: str) -> list:
    cookies_path = os.path.abspath("cookies.txt")
    ydl_opts = {
        'quiet': True,
        'cookiefile': cookies_path,
        'skip_download': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept-Language': 'en-US,en;q=0.9'
        }
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = info.get("formats", [])
        result = []
        for fmt in formats:
            if fmt.get('vcodec') != 'none' and fmt.get('ext') == 'mp4':
                result.append({
                    "format_id": fmt.get("format_id"),
                    "quality": f"{fmt.get('height', 'unknown')}p",
                    "fps": fmt.get("fps"),
                    "ext": fmt.get("ext"),
                    "filesize_mb": round(fmt.get("filesize", 0) / (1024*1024), 2) if fmt.get("filesize") else None
                })
        return result
