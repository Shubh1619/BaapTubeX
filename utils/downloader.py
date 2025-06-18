import os
import yt_dlp

def download_video(url: str, format_code: str = "best") -> str:
    download_dir = "downloads"
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    ydl_opts = {
        'format': format_code,
        'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
        'cookiefile': 'cookies.txt',
        'quiet': True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        return filename
