import os
import re
import sys
import time
import random
import hashlib
import platform
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

import yt_dlp

# -----------------------------
# Configuration
# -----------------------------
# Downloads directory (under current working directory)
DOWNLOAD_DIR = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Simple in-memory cache
_video_cache: Dict[str, Dict[str, Any]] = {}

# Optional cookies file (fallback when --cookies-from-browser is not used)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
COOKIES_TXT = os.path.join(os.path.dirname(SCRIPT_DIR), "youtube_cookies.txt")

# Networking / retry tuning
RATE_LIMIT_BPS = 6_000_000         # 6 MB/s
HTTP_CHUNK_SIZE = 4 * 1024 * 1024  # 4MB
RETRIES = 15
FRAG_RETRIES = 15
RETRY_SLEEP = "exponential:1.5"
SOCKET_TIMEOUT = 30

# -----------------------------
# Utilities
# -----------------------------
def _hc(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()

def _now() -> datetime:
    return datetime.now()

def normalize_youtube_url(url: str) -> str:
    """
    Normalize to canonical https://www.youtube.com/watch?v=<11-char-id>
    Supports youtu.be, shorts, embed, etc. Do NOT convert to youtube-nocookie.
    """
    url = url.strip()

    # youtu.be/<id>
    m = re.match(r"^https?://(?:www\.)?youtu\.be/([A-Za-z0-9_-]{11})(?:[?&].*)?$", url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"

    # youtube.com/shorts/<id>
    m = re.match(r"^https?://(?:www\.)?youtube\.com/shorts/([A-Za-z0-9_-]{11})(?:[?&].*)?$", url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"

    # youtube.com/embed/<id>
    m = re.match(r"^https?://(?:www\.)?youtube\.com/embed/([A-Za-z0-9_-]{11})(?:[?&].*)?$", url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"

    # youtube.com/watch?v=<id>
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})", url)
    if m:
        return f"https://www.youtube.com/watch?v={m.group(1)}"

    return url

def check_ffmpeg() -> Tuple[bool, Optional[str], Optional[str]]:
    try:
        p = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if p.returncode == 0:
            version = p.stdout.splitlines()[0].strip()
            ffmpeg_path = None
            if platform.system() == "Windows":
                w = subprocess.run(["where", "ffmpeg"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
                if w.returncode == 0 and w.stdout.strip():
                    ffmpeg_path = w.stdout.splitlines()[0].strip()
            else:
                w = subprocess.run(["which", "ffmpeg"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
                if w.returncode == 0 and w.stdout.strip():
                    ffmpeg_path = w.stdout.strip()
            print(f"✅ FFmpeg: {version} ({ffmpeg_path or 'in PATH'})")
            return True, version, ffmpeg_path
        print("❌ FFmpeg reported non-zero exit")
    except Exception as e:
        print(f"❌ FFmpeg check error: {e}")
    return False, None, None

def check_aria2c() -> bool:
    try:
        p = subprocess.run(["aria2c", "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        ok = p.returncode == 0
        print("✅ aria2c available" if ok else "❌ aria2c not available")
        return ok
    except Exception:
        print("❌ aria2c not available")
        return False

def get_random_user_agent() -> str:
    uas = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    ]
    return random.choice(uas)

def _get_cache_path(url: str, fmt: str) -> Optional[str]:
    key = _hc(f"{url}::{fmt}")
    entry = _video_cache.get(key)
    if entry and os.path.exists(entry["path"]) and (_now() - entry["ts"] < timedelta(hours=24)):
        return entry["path"]
    return None

def _set_cache(url: str, fmt: str, path: str) -> None:
    key = _hc(f"{url}::{fmt}")
    _video_cache[key] = {"path": path, "ts": _now()}

def _choose_cookies(ydl_opts: Dict[str, Any]) -> None:
    """
    Choose cookies: prefer env-configured --cookies-from-browser, else youtube_cookies.txt if present.
    To use browser cookies, set env: YTDLP_COOKIES_FROM_BROWSER="chrome" or "chrome:Profile 1"
    """
    env_val = os.environ.get("YTDLP_COOKIES_FROM_BROWSER", "").strip()
    if env_val:
        # Supports "browser" or "browser:profile"
        parts = env_val.split(":", 1)
        browser = parts[0].strip().lower()
        profile = parts[1].strip() if len(parts) > 1 else None
        ydl_opts["cookiesfrombrowser"] = (browser, profile, None, None)
        print(f"🍪 Using cookies-from-browser: {browser}{(':'+profile) if profile else ''}")
        return
    if os.path.exists(COOKIES_TXT):
        ydl_opts["cookiefile"] = COOKIES_TXT
        print(f"🍪 Using cookies file: {COOKIES_TXT}")
    else:
        print("⚠️ No cookies configured. Protected videos may require authentication.")

def _build_common_opts() -> Dict[str, Any]:
    ff_ok, _, ff_path = check_ffmpeg()

    headers = {
        "User-Agent": get_random_user_agent(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-Dest": "document",
        "Referer": "https://www.youtube.com/",
        "Origin": "https://www.youtube.com",
    }

    opts: Dict[str, Any] = {
        "outtmpl": os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s"),
        "noplaylist": True,
        "quiet": False,
        "verbose": True,
        "no_warnings": False,
        "nocheckcertificate": True,

        "socket_timeout": SOCKET_TIMEOUT,
        "retries": RETRIES,
        "fragment_retries": FRAG_RETRIES,
        "retry_sleep": RETRY_SLEEP,

        "ratelimit": RATE_LIMIT_BPS,
        "http_chunk_size": HTTP_CHUNK_SIZE,
        "concurrent_fragment_downloads": 1,

        "hls_prefer_ffmpeg": True,
        "hls_use_mpegts": False,

        "geo_bypass": True,

        "extractor_args": {
            "youtube": {
                "player_client": ["web", "android", "ios", "mweb", "tv", "web_embedded", "android_embedded"],
            }
        },

        "http_headers": headers,

        "prefer_ffmpeg": ff_ok,
        "merge_output_format": "mp4",
    }

    if ff_ok and ff_path:
        opts["ffmpeg_location"] = os.path.dirname(ff_path)

    _choose_cookies(opts)
    return opts

def _extract_info_guard(ydl: yt_dlp.YoutubeDL, url: str, download: bool) -> Dict[str, Any]:
    info = ydl.extract_info(url, download=download)
    if info is None:
        raise yt_dlp.utils.DownloadError("extract_info returned None (likely blocked/auth required).")
    if "entries" in info and isinstance(info["entries"], list) and info["entries"]:
        info = info["entries"][0]
    return info

# -----------------------------
# Public API
# -----------------------------
def check_dependencies() -> Dict[str, Any]:
    ff_ok, ff_ver, ff_path = check_ffmpeg()
    aria = check_aria2c()
    cookies = None
    if os.path.exists(COOKIES_TXT):
        cookies = COOKIES_TXT
    elif os.environ.get("YTDLP_COOKIES_FROM_BROWSER"):
        cookies = f"browser:{os.environ['YTDLP_COOKIES_FROM_BROWSER']}"
    return {
        "ffmpeg": {"installed": ff_ok, "version": ff_ver, "path": ff_path},
        "aria2c": aria,
        "cookies": cookies,
        "yt_dlp": yt_dlp.version.__version__,
        "downloads_dir": DOWNLOAD_DIR,
    }

def get_video_formats(url: str) -> List[Dict[str, Any]]:
    url = normalize_youtube_url(url)
    ydl_opts = _build_common_opts()
    ydl_opts.update({
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        "verbose": False,
    })

    out: List[Dict[str, Any]] = []
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = _extract_info_guard(ydl, url, download=False)
            for f in info.get("formats", []):
                if f.get("vcodec") != "none" and f.get("ext") == "mp4":
                    h = f.get("height")
                    if not h:
                        continue
                    fps = f.get("fps") or 0
                    label = f"{h}p" + ("60" if fps >= 50 else "")
                    out.append({
                        "format_id": f.get("format_id"),
                        "label": label,
                        "ext": "mp4",
                        "fps": fps,
                        "filesize_mb": round((f.get("filesize") or 0) / (1024 * 1024), 2) if f.get("filesize") else None
                    })
    except Exception as e:
        print(f"⚠️ Format listing failed: {e}")

    if not out:
        # Provide at least "Auto"
        return [{"format_id": "best", "label": "Auto"}]

    # Add a generic "Auto" on top to map to a robust selector
    out.insert(0, {"format_id": "best", "label": "Auto"})
    return out

def get_best_available_format(url: str, target_height: int) -> str:
    fmts = get_video_formats(url)
    pairs: List[Tuple[int, str]] = []
    for f in fmts:
        if f.get("format_id") and f["format_id"] != "best":
            try:
                # Extract int height from label (e.g. "1080p60" -> 1080)
                h = int(re.sub(r"[^\d]", "", f.get("label", "")))
                pairs.append((h, f["format_id"]))
            except Exception:
                pass
    if not pairs:
        return "best"
    pairs.sort(key=lambda x: (x[0] > target_height, abs(x[0] - target_height)))
    return pairs[0][1]

def download_audio_only(url: str, audio_format: str = "mp3") -> str:
    url = normalize_youtube_url(url)
    ydl_opts = _build_common_opts()
    ydl_opts.update({
        "format": "bestaudio/best",
        "postprocessors": [
            {"key": "FFmpegExtractAudio", "preferredcodec": audio_format, "preferredquality": "0"},
            {"key": "FFmpegMetadata"},
        ],
        "keepvideo": False,
    })

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = _extract_info_guard(ydl, url, download=True)
        out = ydl.prepare_filename(info)
        base, _ = os.path.splitext(out)
        candidate = f"{base}.{audio_format}"
        return candidate if os.path.exists(candidate) else out

def download_video(url: str, format_code: str = "best") -> str:
    url = normalize_youtube_url(url)

    cached = _get_cache_path(url, format_code)
    if cached:
        print(f"🔄 Using cached file: {cached}")
        return cached

    # Map simple resolution tokens to robust selectors
    selector_map = {
        "best": "bestvideo[ext=mp4]+bestaudio/best",
        "1080": "bestvideo[height<=1080][ext=mp4]+bestaudio/best/best[height<=1080][ext=mp4]/best",
        "720":  "bestvideo[height<=720][ext=mp4]+bestaudio/best/best[height<=720][ext=mp4]/best",
        "480":  "bestvideo[height<=480][ext=mp4]+bestaudio/best/best[height<=480][ext=mp4]/best",
        "360":  "bestvideo[height<=360][ext=mp4]+bestaudio/best/best[height<=360][ext=mp4]/best",
    }
    selector = selector_map.get(format_code, format_code)

    ydl_opts = _build_common_opts()
    ydl_opts.update({
        "format": selector,
        "ignoreerrors": False,
    })

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = _extract_info_guard(ydl, url, download=True)
        out = ydl.prepare_filename(info)
        if not out.lower().endswith(".mp4"):
            base, _ = os.path.splitext(out)
            mp4 = base + ".mp4"
            if os.path.exists(mp4):
                out = mp4
        if not os.path.exists(out) or os.path.getsize(out) <= 0:
            raise yt_dlp.utils.DownloadError("File missing or empty after download")
        _set_cache(url, format_code, out)
        return out

def download_with_retry(url: str, format_code: str, max_retries: int = 3) -> str:
    last = None
    for i in range(max_retries):
        try:
            if i > 0:
                print(f"🔄 Retry {i}/{max_retries}")
            return download_video(url, format_code)
        except Exception as e:
            last = e
            sleep = 2 ** (i + 1)
            print(f"⚠️ Attempt {i+1} failed: {e}. Sleeping {sleep}s")
            time.sleep(sleep)
    raise last or RuntimeError("Unknown error")
