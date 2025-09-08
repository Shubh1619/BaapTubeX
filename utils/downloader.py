import os
import re
import sys
import time
import random
import hashlib
import platform
import subprocess
import uuid
import requests
import asyncio
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

# Browser rotation options
MOBILE_USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPad; CPU OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 13; SM-S908B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Mobile Safari/537.36",
    "Mozilla/5.0 (Android 13; Mobile; rv:109.0) Gecko/114.0 Firefox/114.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) CriOS/114.0.5735.99 Mobile/15E148 Safari/604.1",
]

DESKTOP_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/114.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36 Edg/114.0.1823.51",
]

# Browser fingerprints for consistency
BROWSER_FINGERPRINTS = [
    {"name": "chrome", "version": "114.0.5735.134", "platform": "Windows"},
    {"name": "chrome", "version": "114.0.5735.133", "platform": "macOS"},
    {"name": "firefox", "version": "114.0.2", "platform": "Windows"},
    {"name": "firefox", "version": "114.0.1", "platform": "macOS"},
    {"name": "safari", "version": "16.5", "platform": "macOS"},
    {"name": "edge", "version": "114.0.1823.51", "platform": "Windows"},
]

# -----------------------------
# Utilities
# -----------------------------
def _hc(s: str) -> str:
    return hashlib.md5(s.encode("utf-8", errors="ignore")).hexdigest()

def _now() -> datetime:
    return datetime.now()

def _is_render_environment() -> bool:
    """Detect if running on Render"""
    return "RENDER" in os.environ or os.path.exists("/opt/render")

def get_random_fingerprint() -> Dict[str, str]:
    """Get a consistent browser fingerprint for better disguising"""
    return random.choice(BROWSER_FINGERPRINTS)

def get_random_user_agent(fingerprint: Optional[Dict[str, str]] = None) -> str:
    """Get a random but realistic user agent string, optionally matching a fingerprint"""
    if fingerprint:
        browser = fingerprint["name"]
        if browser == "chrome":
            if fingerprint["platform"] == "Windows":
                return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{fingerprint['version']} Safari/537.36"
            else:
                return f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{fingerprint['version']} Safari/537.36"
        elif browser == "firefox":
            if fingerprint["platform"] == "Windows":
                return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{fingerprint['version'].split('.')[0]}.0) Gecko/20100101 Firefox/{fingerprint['version']}"
            else:
                return f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:{fingerprint['version'].split('.')[0]}.0) Gecko/20100101 Firefox/{fingerprint['version']}"
        elif browser == "safari":
            return f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/{fingerprint['version']} Safari/605.1.15"
        elif browser == "edge":
            return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{fingerprint['version'].split('.')[0]}.0.0.0 Safari/537.36 Edg/{fingerprint['version']}"
    
    # If no fingerprint or not matched, return random
    is_mobile = random.random() < 0.4  # 40% chance of mobile
    if is_mobile:
        return random.choice(MOBILE_USER_AGENTS)
    else:
        return random.choice(DESKTOP_USER_AGENTS)

def generate_minimal_cookies() -> str:
    """Generate minimal cookies file with just enough to avoid bot detection"""
    cookies_path = os.path.join(DOWNLOAD_DIR, f"temp_cookies_{uuid.uuid4().hex[:8]}.txt")
    
    # These are placeholder values to make YouTube think we're a normal user
    minimal_cookies = [
        "# Netscape HTTP Cookie File",
        "# This is a generated file. Do not edit.",
        "",
        f".youtube.com\tTRUE\t/\tFALSE\t{int(time.time()) + 3600*24*365*2}\tPREF\tf6=40000000&tz=Asia.Tokyo",
        f".youtube.com\tTRUE\t/\tFALSE\t{int(time.time()) + 3600*24*365*2}\tCONSENT\tYES+cb.20210328-17-p0.en+FX+{random.randint(100, 999)}",
        f".youtube.com\tTRUE\t/\tFALSE\t{int(time.time()) + 3600*24*365*2}\tVISITOR_INFO1_LIVE\t{random.randint(1000000, 9999999)}.{int(time.time())}.{random.randint(1000000, 9999999)}",
        f".youtube.com\tTRUE\t/\tFALSE\t{int(time.time()) + 3600*24*365*2}\tYSC\t{hashlib.md5(str(time.time()).encode()).hexdigest()[:16]}",
    ]
    
    with open(cookies_path, "w") as f:
        f.write("\n".join(minimal_cookies))
    
    return cookies_path

def _get_proxy() -> Optional[str]:
    """Get a proxy server if available"""
    # Check environment variable first
    proxy = os.environ.get("HTTP_PROXY") or os.environ.get("HTTPS_PROXY")
    if proxy:
        return proxy
        
    # You could implement rotation from a list or proxy service
    return None

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

def _get_cache_path(url: str, fmt: str) -> Optional[str]:
    key = _hc(f"{url}::{fmt}")
    entry = _video_cache.get(key)
    if entry and os.path.exists(entry["path"]) and (_now() - entry["ts"] < timedelta(hours=24)):
        return entry["path"]
    return None

def _set_cache(url: str, fmt: str, path: str) -> None:
    key = _hc(f"{url}::{fmt}")
    _video_cache[key] = {"path": path, "ts": _now()}

def _get_player_tokens() -> Dict[str, str]:
    """Generate tokens that look like YouTube player tokens"""
    current_time = int(time.time())
    web_token = f"web+{hashlib.md5(str(current_time).encode()).hexdigest()[:10]}"
    android_token = f"android+{hashlib.md5(str(current_time + 1).encode()).hexdigest()[:10]}"
    ios_token = f"ios+{hashlib.md5(str(current_time + 2).encode()).hexdigest()[:10]}"
    
    return {
        "web": web_token,
        "android": android_token,
        "ios": ios_token
    }

def _create_realistic_session(url: str) -> None:
    """Create a more realistic browsing session before downloading"""
    try:
        # This simulates a user browsing pattern
        fingerprint = get_random_fingerprint()
        session = requests.Session()
        ua = get_random_user_agent(fingerprint)
        
        headers = {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }
        session.headers.update(headers)
        
        # First visit YouTube homepage
        session.get("https://www.youtube.com/")
        time.sleep(random.uniform(0.5, 1.5))
        
        # Then visit the video page (but don't download)
        session.get(url)
        time.sleep(random.uniform(0.8, 2.0))
        
        # Maybe visit another related page
        session.get("https://www.youtube.com/feed/trending")
        
    except Exception as e:
        print(f"Session prep failed (non-critical): {e}")

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
        return
        
    # If no cookies and on Render, generate minimal cookies
    if _is_render_environment() or random.random() < 0.7:  # 70% chance to use minimal cookies anyway
        minimal_cookies = generate_minimal_cookies()
        ydl_opts["cookiefile"] = minimal_cookies
        print(f"🍪 Using generated minimal cookies: {minimal_cookies}")
        return
        
    print("⚠️ No cookies configured. Protected videos may require authentication.")

def _apply_render_specific_settings(opts: Dict[str, Any]) -> None:
    """Apply Render-specific optimizations"""
    if _is_render_environment():
        print("🖥️ Detected Render environment, applying optimizations")
        # Render seems to struggle with the default settings
        opts["socket_timeout"] = 60  # Longer timeout
        
        # These options help with avoiding the bot detection
        opts["sleep_interval"] = 1  # Add delay between requests
        opts["max_sleep_interval"] = 5
        
        # Try to avoid predictable patterns
        mobile_first = random.choice([True, False])
        if mobile_first:
            # Mobile clients first
            opts["extractor_args"]["youtube"]["player_client"] = ["ios", "android", "web", "mweb", "tv", "web_embedded"]
        else:
            # Desktop clients first
            opts["extractor_args"]["youtube"]["player_client"] = ["web", "web_embedded", "tv", "ios", "android", "mweb"]
            
        # Add some player tokens
        tokens = _get_player_tokens()
        if "po_token" not in opts["extractor_args"]["youtube"]:
            opts["extractor_args"]["youtube"]["po_token"] = []
        opts["extractor_args"]["youtube"]["po_token"].extend([tokens["web"], tokens["android"], tokens["ios"]])

def _build_common_opts() -> Dict[str, Any]:
    ff_ok, _, ff_path = check_ffmpeg()

    # Get consistent browser fingerprint for this request
    fingerprint = get_random_fingerprint()
    user_agent = get_random_user_agent(fingerprint)
    
    # More realistic headers with browser consistency
    headers = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": random.choice(["none", "same-origin"]),
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-User": "?1",
        "Sec-Ch-Ua": f'"{fingerprint["name"]}"',
        "Sec-Ch-Ua-Mobile": "?0" if fingerprint["name"] in ["chrome", "firefox", "edge"] else "?1",
        "Sec-Ch-Ua-Platform": f'"{fingerprint["platform"]}"',
        "Referer": "https://www.youtube.com/",
        "Origin": "https://www.youtube.com",
        "Dnt": "1",
        "Upgrade-Insecure-Requests": "1",
    }

    # Get player tokens for anti-bot measures
    tokens = _get_player_tokens()
    
    # Check for forced client preference from environment
    forced_client = os.environ.get("YTDLP_OVERRIDE_CLIENT", "").strip().lower()
    player_clients = []
    if forced_client in ["ios", "android", "web", "mweb", "tv"]:
        # Put the forced client first, then others
        player_clients = [forced_client] + [c for c in ["web", "android", "ios", "mweb", "tv", "web_embedded"] if c != forced_client]
    else:
        # Default client order with slight randomization
        all_clients = ["web", "android", "ios", "mweb", "tv", "web_embedded"]
        random.shuffle(all_clients)
        player_clients = all_clients

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
                "player_client": player_clients,
                "po_token": [tokens["web"], tokens["android"], tokens["ios"]],
            }
        },

        "http_headers": headers,

        "prefer_ffmpeg": ff_ok,
        "merge_output_format": "mp4",
    }

    # Add proxy if available
    proxy = _get_proxy()
    if proxy:
        opts["proxy"] = proxy
        print(f"🔄 Using proxy: {proxy}")

    if ff_ok and ff_path:
        opts["ffmpeg_location"] = os.path.dirname(ff_path)

    # Configure cookies
    _choose_cookies(opts)
    
    # Apply Render-specific settings
    _apply_render_specific_settings(opts)
    
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
    else:
        cookies = "generated_minimal"
    return {
        "ffmpeg": {"installed": ff_ok, "version": ff_ver, "path": ff_path},
        "aria2c": aria,
        "cookies": cookies,
        "yt_dlp": yt_dlp.version.__version__,
        "downloads_dir": DOWNLOAD_DIR,
        "environment": "render" if _is_render_environment() else "standard",
    }

def get_video_formats(url: str) -> List[Dict[str, Any]]:
    url = normalize_youtube_url(url)
    
    # Create a realistic browser session first
    _create_realistic_session(url)
    
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
    
    # Create a realistic browser session first
    _create_realistic_session(url)
    
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

    # Check cache first
    cached = _get_cache_path(url, format_code)
    if cached:
        print(f"🔄 Using cached file: {cached}")
        return cached
        
    # Create a realistic browser session first
    _create_realistic_session(url)

    # Map simple resolution tokens to robust selectors
    selector_map = {
        "best": "bestvideo[ext=mp4]+bestaudio/best",
        "1080": "bestvideo[height<=1080][ext=mp4]+bestaudio/best/best[height<=1080][ext=mp4]/best",
        "720":  "bestvideo[height<=720][ext=mp4]+bestaudio/best/best[height<=720][ext=mp4]/best",
        "480":  "bestvideo[height<=480][ext=mp4]+bestaudio/best/best[height<=480][ext=mp4]/best",
        "360":  "bestvideo[height<=360][ext=mp4]+bestaudio/best/best[height<=360][ext=mp4]/best",
    }
    selector = selector_map.get(format_code, format_code)

    # Add small random delay to look more human
    time.sleep(random.uniform(0.5, 1.5))

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
                # Add variable delays that look more human
                sleep_time = 2 ** i + random.uniform(0.5, 2.5)
                print(f"🔄 Retry {i}/{max_retries} - waiting {sleep_time:.2f}s")
                time.sleep(sleep_time)
                
                # Vary the approach on retries
                if i == 1:
                    # On first retry, try a different format selector
                    if format_code == "best":
                        alternate_format = "bestvideo[ext=mp4]+bestaudio/best"
                    else:
                        alternate_format = "best"
                    print(f"🔄 Trying alternate format: {alternate_format}")
                    return download_video(url, alternate_format)
                elif i == 2:
                    # On second retry, try with mobile client
                    print("🔄 Trying with mobile client")
                    os.environ["YTDLP_OVERRIDE_CLIENT"] = "ios"
                    try:
                        result = download_video(url, format_code)
                        return result
                    finally:
                        os.environ.pop("YTDLP_OVERRIDE_CLIENT", None)
            
            return download_video(url, format_code)
        except Exception as e:
            last = e
            if i < max_retries - 1:
                # Human-like variable retry delay (don't sleep after the last attempt)
                sleep = 2 ** (i + 1) + random.uniform(0.1, 1.0)
                print(f"⚠️ Attempt {i+1} failed: {e}. Sleeping {sleep:.2f}s")
                time.sleep(sleep)
    raise last or RuntimeError("Unknown error")
