import os
import yt_dlp
import re
import hashlib
import random
from datetime import datetime, timedelta
import time
import subprocess
import platform
import sys

# Simple in-memory cache
video_cache = {}

def check_ffmpeg():
    """Check if FFmpeg is properly installed and working"""
    try:
        # Try to execute FFmpeg
        result = subprocess.run(
            ['ffmpeg', '-version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False
        )
        
        if result.returncode == 0:
            version_info = result.stdout.decode('utf-8', errors='ignore').split('\n')[0]
            print(f"✅ FFmpeg is installed: {version_info}")
            return True, version_info
        else:
            print("❌ FFmpeg is installed but not working properly")
            print(f"Error: {result.stderr.decode('utf-8', errors='ignore')}")
            return False, None
            
    except FileNotFoundError:
        print("❌ FFmpeg executable not found in PATH")
        return False, None
    except Exception as e:
        print(f"❌ Error checking FFmpeg: {str(e)}")
        return False, None

def check_dependencies():
    """Check if required dependencies are installed and accessible"""
    dependencies = {
        "FFmpeg": {
            "installed": False,
            "version": None,
            "path": None
        },
        "aria2c": False,
        "yt-dlp": True  # Assuming you have yt-dlp installed as a Python package
    }
    
    # Check FFmpeg
    ffmpeg_installed, ffmpeg_version = check_ffmpeg()
    dependencies["FFmpeg"]["installed"] = ffmpeg_installed
    dependencies["FFmpeg"]["version"] = ffmpeg_version
    
    if ffmpeg_installed:
        try:
            # Try to get the full path to FFmpeg
            if platform.system() == "Windows":
                ffmpeg_path_cmd = ["where", "ffmpeg"]
            else:
                ffmpeg_path_cmd = ["which", "ffmpeg"]
                
            result = subprocess.run(
                ffmpeg_path_cmd, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE, 
                check=False
            )
            if result.returncode == 0:
                ffmpeg_path = result.stdout.decode('utf-8', errors='ignore').strip()
                dependencies["FFmpeg"]["path"] = ffmpeg_path
                print(f"✅ FFmpeg path: {ffmpeg_path}")
        except:
            pass
    
    # Check aria2c
    try:
        result = subprocess.run(['aria2c', '--version'], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE, 
                               check=False)
        if result.returncode == 0:
            dependencies["aria2c"] = True
            print("✅ aria2c is installed and accessible")
        else:
            print("❌ aria2c is installed but not accessible")
    except (FileNotFoundError, subprocess.SubprocessError):
        print("❌ aria2c is not installed or not accessible")
    
    # Check for cookies file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cookie_file = os.path.join(script_dir, "youtube_cookies.txt")
    if os.path.exists(cookie_file):
        print(f"✅ YouTube cookies file found: {cookie_file}")
    else:
        print(f"⚠️ YouTube cookies file not found. Some videos might not be accessible.")
    
    return dependencies

def get_cached_video(url: str, format_code: str):
    """Check if video is in cache and not expired"""
    cache_key = hashlib.md5(f"{url}_{format_code}".encode()).hexdigest()
    cache_entry = video_cache.get(cache_key)
    
    if cache_entry and os.path.exists(cache_entry["path"]):
        # Check if cache entry is still valid (24 hours)
        if datetime.now() - cache_entry["timestamp"] < timedelta(hours=24):
            return cache_entry["path"]
    
    return None

def cache_video(url: str, format_code: str, file_path: str):
    """Add video to cache"""
    cache_key = hashlib.md5(f"{url}_{format_code}".encode()).hexdigest()
    video_cache[cache_key] = {
        "path": file_path,
        "timestamp": datetime.now()
    }

def convert_to_nocookie_url(url: str) -> str:
    """Convert standard youtube.com URLs to youtube-nocookie.com URLs."""
    # Also handle youtu.be links
    url = re.sub(r'(?:https?://)?(?:www\.)?youtu\.be/', 'https://www.youtube-nocookie.com/watch?v=', url)
    return re.sub(r'(?:https?://)?(?:www\.)?youtube\.com', 'https://www.youtube-nocookie.com', url)

def get_random_user_agent():
    """Get a random user agent to avoid blocking"""
    user_agents = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
    ]
    return random.choice(user_agents)

def direct_youtube_download(url, output_dir="downloads", format_code="best"):
    """Download YouTube video using direct command-line execution"""
    # Create download directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    # Generate a temporary filename
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    timestamp = int(time.time())
    temp_filename = f"download_{url_hash}_{timestamp}.%(ext)s"
    output_template = os.path.join(output_dir, temp_filename)
    
    # Map format codes to yt-dlp format strings
    format_map = {
        'best': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        '1080': 'bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best[height<=1080]',
        '720': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best[height<=720]',
        '480': 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]',
        '360': 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best[height<=360]',
    }
    
    # Get the format string
    format_string = format_map.get(format_code, format_code)
    
    # Check for aria2c
    use_aria2c = False
    try:
        result = subprocess.run(['aria2c', '--version'], 
                              stdout=subprocess.PIPE, 
                              stderr=subprocess.PIPE, 
                              check=False)
        if result.returncode == 0:
            use_aria2c = True
            print("📥 Using aria2c as external downloader")
    except (FileNotFoundError, subprocess.SubprocessError):
        print("⚠️ aria2c not found, using default downloader")
        
    # Check for cookie file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cookie_file = os.path.join(script_dir, "youtube_cookies.txt")
    
    # Base command - FIXED: removed problematic --no-hls flag
    cmd = [
        sys.executable, '-m', 'yt_dlp',  # Use Python module to ensure correct version
        '--format', format_string,
        '--merge-output-format', 'mp4',
        '--no-check-certificate',
        '--geo-bypass',
        '--output', output_template,
        '--no-playlist',
        '--ignore-errors',
        '--no-warnings',
        '--hls-prefer-ffmpeg',  # Use FFmpeg for HLS instead of native
        '--user-agent', get_random_user_agent(),
        '--referer', 'https://www.youtube.com/',
    ]
    
    # Add external downloader if available
    if use_aria2c:
        cmd.extend([
            '--external-downloader', 'aria2c',
            '--external-downloader-args', 'aria2c:-x16 -s16 -k1M'
        ])
    
    # Add cookies if available
    if os.path.exists(cookie_file):
        cmd.extend(['--cookies', cookie_file])
        print(f"🍪 Using cookies from: {cookie_file}")
        
    # Add the URL
    cmd.append(url)
    
    print(f"Executing command: {' '.join(cmd)}")
    
    try:
        # Run the command
        process = subprocess.run(cmd, 
                               capture_output=True, 
                               text=True, 
                               check=False)
        
        # Check for errors
        if process.returncode != 0:
            print(f"❌ Command failed with code {process.returncode}")
            print(f"Error: {process.stderr}")
            # Try with a simpler format
            if format_code != "best":
                print("🔄 Trying again with 'best' format...")
                return direct_youtube_download(url, output_dir, "best")
            else:
                raise Exception(f"Failed to download video: {process.stderr}")
        
        # Get the downloaded filename from the output
        output = process.stdout
        download_lines = [line for line in output.splitlines() if "[download]" in line and "Destination:" in line]
        
        if download_lines:
            # Extract the filename from the last download line
            filename_match = re.search(r'Destination: (.*)', download_lines[-1])
            if filename_match:
                downloaded_file = filename_match.group(1)
                
                # Get the title to rename the file
                title_cmd = [
                    sys.executable, '-m', 'yt_dlp',
                    '--skip-download',
                    '--print', 'title',
                    '--no-warnings',
                    url
                ]
                
                try:
                    title_process = subprocess.run(title_cmd, 
                                                capture_output=True, 
                                                text=True, 
                                                check=False)
                    if title_process.returncode == 0:
                        title = title_process.stdout.strip()
                        # Clean title for filename
                        title = re.sub(r'[^\w\-_\. ]', '_', title)
                        title = title.strip()
                        
                        # Get extension
                        ext = os.path.splitext(downloaded_file)[1]
                        if not ext:
                            ext = '.mp4'
                            
                        final_path = os.path.join(output_dir, f"{title}{ext}")
                        
                        # Make sure the final path is unique
                        counter = 1
                        original_path = final_path
                        while os.path.exists(final_path):
                            name, ext = os.path.splitext(original_path)
                            final_path = f"{name}_{counter}{ext}"
                            counter += 1
                        
                        # Rename file
                        if os.path.exists(downloaded_file):
                            os.rename(downloaded_file, final_path)
                            return final_path
                        else:
                            print(f"❌ Downloaded file not found: {downloaded_file}")
                except Exception as rename_error:
                    print(f"⚠️ Error renaming file: {str(rename_error)}")
                    if os.path.exists(downloaded_file):
                        return downloaded_file
        
        # Search for any mp4 file created in the output directory during this run
        files_in_dir = os.listdir(output_dir)
        mp4_files = [f for f in files_in_dir if f.endswith('.mp4') and (
            f.startswith(f"download_{url_hash}_{timestamp}") or 
            f.startswith(f"download_{url_hash}")
        )]
        
        if mp4_files:
            return os.path.join(output_dir, mp4_files[0])
            
        raise Exception("Could not find downloaded file")
        
    except Exception as e:
        print(f"❌ Direct download failed: {str(e)}")
        raise e

def download_simple(url: str, format_code: str = "best") -> str:
    """Simple direct download without complex merging, as a last resort"""
    download_dir = "downloads"
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)
    
    # Generate a unique filename
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    timestamp = int(time.time())
    output_filename = f"simple_{url_hash}_{timestamp}.mp4"
    output_path = os.path.join(download_dir, output_filename)
    
    # For simple download, we use a direct mp4 format without separate audio
    # This avoids needing FFmpeg for merging
    format_map = {
        'best': 'best[ext=mp4]/best',
        '1080': 'best[height<=1080][ext=mp4]/best[height<=1080]/best',
        '720': 'best[height<=720][ext=mp4]/best[height<=720]/best',
        '480': 'best[height<=480][ext=mp4]/best[height<=480]/best',
        '360': 'best[height<=360][ext=mp4]/best[height<=360]/best',
    }
    
    format_string = format_map.get(format_code, "best[ext=mp4]/best")
    
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '--format', format_string,
        '--no-check-certificate',
        '--geo-bypass',
        '--output', output_path,
        '--no-playlist',
        '--no-warnings',
        url
    ]
    
    print(f"Executing simple download command: {' '.join(cmd)}")
    
    try:
        subprocess.run(cmd, check=True)
        
        if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
            return output_path
        
        raise Exception("Simple download failed - file not found or empty")
    except Exception as e:
        print(f"❌ Simple download failed: {str(e)}")
        raise

def download_video(url: str, format_code: str = "best") -> str:
    """Download a YouTube video with the specified format"""
    # Check cache first
    cached_path = get_cached_video(url, format_code)
    if cached_path:
        print(f"🔄 Using cached video: {cached_path}")
        return cached_path
        
    download_dir = "downloads"
    if not os.path.exists(download_dir):
        os.makedirs(download_dir)

    # Check for aria2c
    use_external_downloader = False
    try:
        result = subprocess.run(['aria2c', '--version'], 
                               stdout=subprocess.PIPE, 
                               stderr=subprocess.PIPE, 
                               check=False)
        if result.returncode == 0:
            use_external_downloader = True
            print("📥 Using aria2c as external downloader")
    except (FileNotFoundError, subprocess.SubprocessError):
        print("⚠️ aria2c not found, using default downloader")

    # Modified format selectors with more audio fallbacks
    format_selector = {
        'best': 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/best',
        '1080': '137+140/137+bestaudio/399+140/bestvideo[height<=1080]+bestaudio/best[height<=1080]',
        '720': '136+140/136+bestaudio/398+140/bestvideo[height<=720]+bestaudio/best[height<=720]',
        '480': '135+140/135+bestaudio/397+140/bestvideo[height<=480]+bestaudio/best[height<=480]',
        '360': '134+140/134+bestaudio/396+140/bestvideo[height<=360]+bestaudio/best[height<=360]',
        '240': '133+140/133+bestaudio/395+140/bestvideo[height<=240]+bestaudio/best[height<=240]',
        '144': '160+140/160+bestaudio/394+140/bestvideo[height<=144]+bestaudio/best[height<=144]'
    }
    
    # Base ydl options
    ydl_opts = {
        'format': format_selector.get(format_code, format_code),
        'outtmpl': os.path.join(download_dir, '%(title)s.%(ext)s'),
        'quiet': False,
        'verbose': True,
        'nocheckcertificate': True,
        'no_warnings': False,
        'prefer_ffmpeg': True,
        'merge_output_format': 'mp4',
        'socket_timeout': 60,  # Increased timeout
        'retries': 10,
        'fragment_retries': 10,
        'retry_sleep': 3,
        'ignoreerrors': True,
        'http_chunk_size': 10485760,  # 10MB chunks
        'concurrent_fragment_downloads': 5,
        'postprocessors': [{
            'key': 'FFmpegVideoConvertor',
            'preferedformat': 'mp4'
        }],
        'http_headers': {
            'User-Agent': get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-Dest': 'document',
            'Sec-Ch-Ua': '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Cache-Control': 'max-age=0',
            'Origin': 'https://www.youtube.com',
            'Referer': 'https://www.youtube.com/'
        },
        # FIXED: Using hls_prefer_ffmpeg instead of hls_prefer_native
        'hls_prefer_ffmpeg': True,
        # Add geo bypass
        'geo_bypass': True
    }
    
    # Add external downloader if available
    if use_external_downloader:
        ydl_opts.update({
            'external_downloader': 'aria2c',
            'external_downloader_args': [
                '--min-split-size=1M',
                '--max-connection-per-server=16',
                '--retry-wait=3',
                '--max-tries=5'
            ]
        })
    
    # Check for cookie file
    script_dir = os.path.dirname(os.path.abspath(__file__))
    cookie_file = os.path.join(script_dir, "youtube_cookies.txt")
    if os.path.exists(cookie_file):
        print(f"🍪 Using cookies from: {cookie_file}")
        ydl_opts['cookiefile'] = cookie_file

    try:
        converted_url = convert_to_nocookie_url(url)
        print(f"🔗 Using URL: {converted_url}")
        
        # First try with original format
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(converted_url, download=True)
                filename = ydl.prepare_filename(info)
                
                # Ensure file extension is .mp4
                if not filename.lower().endswith('.mp4'):
                    base_filename = os.path.splitext(filename)[0]
                    new_filename = f"{base_filename}.mp4"
                    # If file exists with mp4 extension, use that
                    if os.path.exists(new_filename):
                        filename = new_filename
                
                # Check if file exists and has size > 0
                if os.path.exists(filename) and os.path.getsize(filename) > 0:
                    cache_video(url, format_code, filename)
                    return filename
                else:
                    print("⚠️ File empty or not found, trying fallback...")
                    raise Exception("Empty file")
                    
        except Exception as first_error:
            print(f"⚠️ First attempt failed: {str(first_error)}, trying fallback...")
            
            # If first attempt fails, try with a simpler format
            ydl_opts['format'] = 'best[ext=mp4]/best'
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)  # Try original URL here
                filename = ydl.prepare_filename(info)
                
                # Ensure file extension is .mp4
                if not filename.lower().endswith('.mp4'):
                    base_filename = os.path.splitext(filename)[0]
                    filename = f"{base_filename}.mp4"
                
                if os.path.exists(filename) and os.path.getsize(filename) > 0:
                    cache_video(url, format_code, filename)
                    return filename
                else:
                    raise Exception(f"Failed to download video after multiple attempts. Original error: {first_error}")
                
    except Exception as e:
        print("❌ yt-dlp error:", str(e))
        raise e

def download_video_with_audio_fallback(url: str, format_code: str = "best") -> str:
    """Try multiple approaches to download video with audio"""
    try:
        # First try normal method
        return download_video(url, format_code)
    except Exception as e:
        print(f"⚠️ Standard download failed: {str(e)}")
        print("🔄 Trying separate audio/video download approach...")
        
        download_dir = "downloads"
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)
            
        # Generate a unique filename for this download
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        timestamp = int(time.time())
        temp_video_file = os.path.join(download_dir, f"video_{url_hash}_{timestamp}.mp4")
        temp_audio_file = os.path.join(download_dir, f"audio_{url_hash}_{timestamp}.m4a")
        output_file = os.path.join(download_dir, f"combined_{url_hash}_{timestamp}.mp4")
        
        # Step 1: Download video only
        video_opts = {
            'format': 'bestvideo[ext=mp4]/best[ext=mp4]/best',
            'outtmpl': temp_video_file,
            'quiet': False,
            'no_warnings': False,
            'nocheckcertificate': True,
            'retries': 5,
            'geo_bypass': True,
            'hls_prefer_ffmpeg': True  # FIXED: Using hls_prefer_ffmpeg instead of hls_prefer_native
        }
        
        # Step 2: Download audio only
        audio_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio',
            'outtmpl': temp_audio_file,
            'quiet': False,
            'no_warnings': False,
            'nocheckcertificate': True,
            'retries': 5,
            'geo_bypass': True,
            'hls_prefer_ffmpeg': True  # FIXED: Using hls_prefer_ffmpeg instead of hls_prefer_native
        }
        
        try:
            # Download video
            with yt_dlp.YoutubeDL(video_opts) as ydl:
                ydl.download([url])
                
            # Download audio
            with yt_dlp.YoutubeDL(audio_opts) as ydl:
                ydl.download([url])
                
            # Combine using FFmpeg
            if os.path.exists(temp_video_file) and os.path.exists(temp_audio_file):
                # Get title for better filename
                info_opts = {
                    'quiet': True,
                    'skip_download': True,
                    'geo_bypass': True
                }
                with yt_dlp.YoutubeDL(info_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    title = info.get('title', f"video_{url_hash}")
                    # Sanitize title for filename
                    title = re.sub(r'[^\w\-_\. ]', '_', title)
                    final_output = os.path.join(download_dir, f"{title}.mp4")
                
                # Merge files with enhanced error handling
                try:
                    print(f"📝 Merging video and audio using FFmpeg...")
                    # Try to get FFmpeg path
                    ffmpeg_path = "ffmpeg"
                    if platform.system() == "Windows":
                        try:
                            result = subprocess.run(["where", "ffmpeg"], 
                                                stdout=subprocess.PIPE, 
                                                stderr=subprocess.PIPE, 
                                                check=False,
                                                text=True)
                            if result.returncode == 0 and result.stdout.strip():
                                ffmpeg_path = result.stdout.strip().split('\n')[0]
                        except:
                            # Fall back to default "ffmpeg" command
                            pass
                    
                    ffmpeg_command = [
                        ffmpeg_path, '-y',
                        '-i', temp_video_file,
                        '-i', temp_audio_file,
                        '-c:v', 'copy',
                        '-c:a', 'aac', '-strict', 'experimental',
                        final_output
                    ]
                    
                    # Print the command for debugging
                    print(f"Executing: {' '.join(ffmpeg_command)}")
                    
                    # Run FFmpeg with detailed output
                    process = subprocess.run(
                        ffmpeg_command,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        check=False
                    )
                    
                    # Check if FFmpeg succeeded
                    if process.returncode != 0:
                        print(f"❌ FFmpeg error (code {process.returncode}):")
                        print(process.stderr)
                        # Fall back to simple copy if FFmpeg merging fails
                        print("🔄 FFmpeg merging failed, falling back to video-only file")
                        
                        # Just use the video file and rename it
                        os.rename(temp_video_file, final_output)
                        
                        # Remove the audio file
                        if os.path.exists(temp_audio_file):
                            os.remove(temp_audio_file)
                    else:
                        print("✅ FFmpeg merging completed successfully")
                        
                        # Clean up temp files
                        if os.path.exists(temp_video_file):
                            os.remove(temp_video_file)
                        if os.path.exists(temp_audio_file):
                            os.remove(temp_audio_file)
                    
                    if os.path.exists(final_output):
                        return final_output
                    else:
                        raise Exception("Final output file not found after processing")
                        
                except Exception as ffmpeg_error:
                    print(f"❌ FFmpeg error: {str(ffmpeg_error)}")
                    
                    # If FFmpeg fails completely, just use the video file
                    if os.path.exists(temp_video_file) and os.path.getsize(temp_video_file) > 0:
                        # Rename the video file as the final output
                        os.rename(temp_video_file, final_output)
                        
                        # Clean up audio file
                        if os.path.exists(temp_audio_file):
                            os.remove(temp_audio_file)
                            
                        return final_output
                    else:
                        raise Exception("Video file missing after download")
            else:
                if os.path.exists(temp_video_file) and os.path.getsize(temp_video_file) > 0:
                    # If we at least have the video file, use that
                    final_output = os.path.join(download_dir, f"{url_hash}.mp4")
                    os.rename(temp_video_file, final_output)
                    return final_output
                else:
                    raise Exception("Failed to download video and audio files")
                
        except Exception as e2:
            print(f"❌ Manual download approach failed: {str(e2)}")
            # Clean up any temp files
            for f in [temp_video_file, temp_audio_file, output_file]:
                if os.path.exists(f):
                    os.remove(f)
            raise e2

def download_audio_only(url: str, output_dir="downloads") -> str:
    """Download only the audio from a YouTube video"""
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    # Generate a unique filename
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    timestamp = int(time.time())
    temp_filename = f"audio_{url_hash}_{timestamp}.%(ext)s"
    output_template = os.path.join(output_dir, temp_filename)
    
    cmd = [
        sys.executable, '-m', 'yt_dlp',
        '-x',  # Extract audio
        '--audio-format', 'mp3',
        '--audio-quality', '0',
        '--no-check-certificate',
        '--geo-bypass',
        '--output', output_template,
        '--no-playlist',
        '--no-warnings',
        url
    ]
    
    print(f"Executing audio download command: {' '.join(cmd)}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        
        # Find the output file
        output_lines = result.stdout.splitlines()
        dest_lines = [line for line in output_lines if "Destination" in line]
        
        if dest_lines:
            dest_line = dest_lines[-1]
            match = re.search(r'Destination:\s*(.*)', dest_line)
            if match:
                audio_file = match.group(1)
                if os.path.exists(audio_file):
                    return audio_file
        
        # If we couldn't find the file from output, search the directory
        files = os.listdir(output_dir)
        audio_files = [
            os.path.join(output_dir, f) for f in files 
            if f.startswith(f"audio_{url_hash}") and f.endswith((".mp3", ".m4a"))
        ]
        
        if audio_files:
            return audio_files[0]
            
        raise Exception("Audio file not found after download")
        
    except Exception as e:
        print(f"❌ Audio download failed: {str(e)}")
        raise e

def download_video_improved(url: str, format_code: str = "best") -> str:
    """New improved download function with multiple fallbacks"""
    # Check cache first
    cached_path = get_cached_video(url, format_code)
    if cached_path:
        print(f"🔄 Using cached video: {cached_path}")
        return cached_path
        
    try:
        # First try with the regular method
        try:
            return download_video_with_audio_fallback(url, format_code)
        except Exception as e:
            if "FFmpeg" in str(e):
                print(f"⚠️ FFmpeg error detected: {str(e)}")
                print("🔄 Trying simple download method (no FFmpeg required)...")
                try:
                    # Try simple download as FFmpeg fallback
                    file_path = download_simple(url, format_code)
                    
                    # Cache the result if successful
                    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                        cache_video(url, format_code, file_path)
                        return file_path
                    else:
                        raise Exception("Downloaded file is empty or not found")
                except Exception as e2:
                    print(f"⚠️ Simple download failed: {str(e2)}")
            
            print(f"⚠️ Regular download methods failed: {str(e)}")
            print("🔄 Trying direct command-line approach...")
            
            # Try with direct command-line approach
            file_path = direct_youtube_download(url, "downloads", format_code)
            
            # Cache the result
            if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                cache_video(url, format_code, file_path)
                return file_path
            else:
                raise Exception("Downloaded file is empty or not found")
                
    except Exception as e:
        print(f"❌ All download methods failed: {str(e)}")
        raise e

def download_with_retry(url: str, format_code: str, max_retries: int = 3) -> str:
    """Try downloading with exponential backoff on failure"""
    retry_count = 0
    last_error = None
    
    while retry_count < max_retries:
        try:
            if retry_count > 0:
                print(f"🔄 Retry attempt {retry_count}/{max_retries}...")
            # Use the improved download method
            return download_video_improved(url, format_code)
        except Exception as e:
            last_error = e
            retry_count += 1
            wait_time = 2 ** retry_count  # Exponential backoff
            print(f"⚠️ Download attempt {retry_count} failed: {str(e)}. Waiting {wait_time} seconds before retry...")
            time.sleep(wait_time)
    
    # If we reach here, all retries failed
    print(f"❌ All {max_retries} download attempts failed.")
    raise last_error

def get_best_available_format(url: str, target_height: int) -> str:
    """Get the best available format ID for a given resolution target"""
    formats = get_video_formats(url)
    
    # Extract all format_ids that match mp4 and have height info
    valid_formats = []
    for fmt in formats:
        if fmt.get("label") and fmt.get("format_id") != "best":
            # Extract height from label (e.g., "720p" → 720)
            try:
                height = int(fmt["label"].replace("p", "").replace("60", ""))
                valid_formats.append((height, fmt["format_id"]))
            except ValueError:
                continue
    
    # Sort by height, with preference to formats closest to but not exceeding target
    valid_formats.sort(key=lambda x: (x[0] > target_height, abs(x[0] - target_height)))
    
    if valid_formats:
        return valid_formats[0][1]
    return "best"  # Fallback to best

def get_video_formats(url: str) -> list:
    """Get available video formats for a YouTube URL"""
    try:
        # Use yt-dlp command directly to get available formats
        cmd = [
            sys.executable, '-m', 'yt_dlp',
            '-F',
            '--no-check-certificate',
            '--geo-bypass',
            '--no-warnings',
            url
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode != 0:
            print(f"Format retrieval failed: {result.stderr}")
            return [{"format_id": "best", "label": "Auto"}]
        
        # Parse the output to extract formats
        formats = []
        lines = result.stdout.splitlines()
        
        for line in lines:
            if not line.strip() or line.startswith('['):
                continue
                
            parts = line.split()
            if len(parts) >= 3:
                format_id = parts[0]
                
                # Skip format table header
                if format_id == "format":
                    continue
                    
                # Extract resolution
            resolution = "unknown"
            for part in parts:
                if 'x' in part and part[0].isdigit():
                    width, height = part.split('x')
                    try:
                        height = int(height)
                        if height <= 144:
                            resolution = "144p"
                        elif height <= 240:
                            resolution = "240p"
                        elif height <= 360:
                            resolution = "360p"
                        elif height <= 480:
                            resolution = "480p"
                        elif height <= 720:
                            resolution = "720p"
                        elif height <= 1080:
                            resolution = "1080p"
                        elif height <= 1440:
                            resolution = "1440p"
                        elif height <= 2160:
                            resolution = "4K"
                        else:
                            resolution = f"{height}p"
                    except:
                        resolution = part
                    break
                
                            
                # Add format if it has video
                if 'video' in line.lower() and 'mp4' in line.lower():
                    formats.append({
                        "format_id": format_id,
                        "label": resolution,
                        "ext": "mp4"
                    })
        
        # Add standard format options if none found
        if not formats:
            formats = [
                {"format_id": "best", "label": "Auto"},
                {"format_id": "137+140", "label": "1080p"},
                {"format_id": "136+140", "label": "720p"},
                {"format_id": "135+140", "label": "480p"},
                {"format_id": "134+140", "label": "360p"}
            ]
        else:
            # Add auto option on top
            formats.insert(0, {"format_id": "best", "label": "Auto"})
            
        return formats
    except Exception as e:
        print(f"Error getting formats: {str(e)}")
        # Return basic formats
        return [
            {"format_id": "best", "label": "Auto"},
            {"format_id": "137+140", "label": "1080p"},
            {"format_id": "136+140", "label": "720p"},
            {"format_id": "135+140", "label": "480p"},
            {"format_id": "134+140", "label": "360p"}
        ]

# Check dependencies on module load
dependencies = check_dependencies()


