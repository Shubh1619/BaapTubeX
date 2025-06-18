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

    label_map = {
        144: "144p",
        240: "240p",
        360: "360p",
        480: "480p",
        720: "720p",
        1080: "1080p"
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = info.get("formats", [])
        result = []

        for fmt in formats:
            height = fmt.get("height")
            fps = fmt.get("fps", 0)
            if fmt.get('vcodec') != 'none' and fmt.get('ext') == 'mp4' and height:
                label = f"{label_map.get(height, str(height)+'p')}"
                if fps >= 50:
                    label += "60"

                result.append({
                    "format_id": fmt.get("format_id"),
                    "label": label,
                    "ext": fmt.get("ext"),
                    "fps": fps,
                    "filesize_mb": round(fmt.get("filesize", 0) / (1024*1024), 2) if fmt.get("filesize") else None
                })

        # Auto option on top
        result.insert(0, { "format_id": "best", "label": "Auto" })
        return result
