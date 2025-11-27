"""YouTube audio downloader using yt-dlp."""

import os
import re
import json
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple, List
import yt_dlp
from yt2txt.config import Config

# Check yt-dlp version for debugging
try:
    import yt_dlp.version
    YT_DLP_VERSION = yt_dlp.version.__version__
except:
    try:
        YT_DLP_VERSION = yt_dlp.__version__
    except:
        YT_DLP_VERSION = "unknown"


def extract_video_id(url: str) -> str:
    """Extract video ID from various YouTube URL formats."""
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/)([^&\n?#]+)',
        r'youtube\.com\/watch\?.*v=([^&\n?#]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    
    raise ValueError(f"Could not extract video ID from URL: {url}")


def slugify(text: str) -> str:
    """Convert text to a filesystem-safe slug, preserving important characters."""
    if not text:
        return ""
    
    # Try to extract company name if there's a pattern like "Company Inc. (SYMBOL)"
    # Look for patterns like "Company Name (TSX-V: SYMBOL" or stop at "Webcast" or "|"
    company_match = re.match(r'^([^|]+?)(?:\s+Webcast|\s*\|)', text)
    if company_match:
        text = company_match.group(1).strip()
    else:
        # Otherwise, take first part up to "|" or first 10 words, whichever comes first
        if '|' in text:
            text = text.split('|')[0].strip()
        else:
            words = text.split()[:10]
            text = ' '.join(words)
    
    # Remove only truly problematic Windows filesystem characters
    # Windows doesn't allow : in folder names, so replace with dash (make it readable)
    text = text.replace(': ', ' - ')  # Replace colon+space with dash+space for readability
    text = text.replace(':', '-')  # Replace any remaining colons
    text = re.sub(r'[<>"\\?*]', '', text)  # Remove other Windows-invalid characters
    # Replace multiple spaces with single space
    text = re.sub(r'\s+', ' ', text)
    # Trim to reasonable length (80 chars)
    text = text.strip()[:80]
    
    return text


def get_output_dir(video_id: str, title: Optional[str] = None) -> Path:
    """Get the output directory for a video, named after title with video ID as suffix."""
    if title:
        slug = slugify(title)
        if slug:
            # Use title first, then video ID as suffix for uniqueness
            folder_name = f"{slug} - {video_id}"
        else:
            folder_name = video_id
    else:
        folder_name = video_id
    return Config.OUT_DIR / folder_name


def download_audio(url: str, force: bool = False) -> Tuple[Path, Dict, str]:
    """
    Download audio from YouTube URL.
    
    Args:
        url: YouTube video URL
        force: If True, re-download even if cached
        
    Returns:
        Tuple of (audio_path, metadata_dict, video_id)
    """
    video_id = extract_video_id(url)
    
    # We'll get the title during the main download, so start with video_id only
    # The output_dir will be updated once we have the title
    output_dir = get_output_dir(video_id, None)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    audio_path = output_dir / "audio.mp3"
    meta_path = output_dir / "meta.json"
    
    # Check cache
    if not force and audio_path.exists() and meta_path.exists():
        print(f"✓ Using cached audio for video {video_id}")
        with open(meta_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        return audio_path, metadata, video_id
    
    # Configure yt-dlp for audio-only download
    # Keep it simple - let yt-dlp use its defaults which are most reliable
    ydl_opts = {
        # Download best audio format - simple format string that yt-dlp handles well
        'format': 'bestaudio/best',
        'outtmpl': str(audio_path.with_suffix('.%(ext)s')),  # Preserve original extension
        'quiet': True,  # Suppress output unless debugging
        'no_warnings': False,
        'extract_flat': False,
        'keepvideo': False,
        'noplaylist': True,
        'writethumbnail': False,
        'writeautomaticsub': False,
        # Retry options for better reliability
        'retries': 10,
        'fragment_retries': 10,
        'file_access_retries': 3,
    }
    
    # Add cookies if provided (for bypassing YouTube bot detection)
    # Priority order:
    # 1. YOUTUBE_COOKIES_CONTENT env var (for Replit Secrets - paste entire cookies.txt content)
    # 2. YOUTUBE_COOKIES_TXT env var (file path)
    # 3. youtube_cookies.txt in project root
    cookies_content = os.getenv("YOUTUBE_COOKIES_CONTENT", "")
    cookies_path = Config.YOUTUBE_COOKIES_TXT
    
    # Also check for cookies file in project root
    project_root = Path(__file__).parent.parent.resolve()
    default_cookies_path = project_root / "youtube_cookies.txt"
    
    # Track if we're using cookies
    using_cookies = False
    temp_cookies_file = None
    
    # Log yt-dlp version for debugging
    print(f"Using yt-dlp version: {YT_DLP_VERSION}")
    
    if cookies_content:
        # Write cookies content to temporary file
        # This is the recommended way for Streamlit Cloud: create a secret named "YOUTUBE_COOKIES_CONTENT"
        # and paste the entire contents of your cookies.txt file
        import tempfile
        # Strip whitespace and ensure proper formatting
        cookies_content = cookies_content.strip()
        if cookies_content:
            temp_cookies = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
            temp_cookies.write(cookies_content)
            temp_cookies.flush()
            temp_cookies.close()
            temp_cookies_file = temp_cookies.name
            ydl_opts['cookiefile'] = temp_cookies_file
            using_cookies = True
            # Verify file was created and has content
            cookie_file_size = Path(temp_cookies_file).stat().st_size if Path(temp_cookies_file).exists() else 0
            cookie_lines = len([line for line in cookies_content.split('\n') if line.strip() and not line.strip().startswith('#')])
            if cookie_file_size > 0:
                print(f"✓ Using YouTube cookies from YOUTUBE_COOKIES_CONTENT (file size: {cookie_file_size} bytes, {cookie_lines} cookie entries)")
            else:
                print(f"⚠ Warning: Cookies file was created but appears empty")
        else:
            print(f"⚠ Warning: YOUTUBE_COOKIES_CONTENT is set but empty")
    elif cookies_path and Path(cookies_path).exists():
        ydl_opts['cookiefile'] = cookies_path
        using_cookies = True
        print(f"Using YouTube cookies from: {cookies_path}")
    elif default_cookies_path.exists():
        ydl_opts['cookiefile'] = str(default_cookies_path)
        using_cookies = True
        print(f"Using YouTube cookies from: {default_cookies_path}")
    
    # With cookies, explicitly use web client first (most reliable with cookies)
    # If that fails, we'll try ios client as fallback
    if using_cookies:
        # Web client works best with cookies
        ydl_opts['extractor_args'] = {'youtube': {'player_client': 'web'}}
        print("Using web client with cookies")
    else:
        # Without cookies, use android client as it's more reliable for unauthenticated requests
        ydl_opts['extractor_args'] = {'youtube': {'player_client': 'android'}}
        print("No cookies file found - using Android client")
    
    # Minimal headers - yt-dlp handles most of this automatically
    # Only add what's necessary to avoid conflicts
    ydl_opts['referer'] = 'https://www.youtube.com/'
    
    # Add delays between requests to avoid rate limiting
    ydl_opts['sleep_interval'] = 1  # Sleep 1 second between requests
    ydl_opts['sleep_requests'] = 1  # Sleep 1 second between different requests
    
    metadata = {}
    
    # Track downloaded file via progress hook and immediately save it
    saved_file_path = None
    
    def progress_hook(d):
        """Hook to save file path when download completes and immediately backup."""
        nonlocal saved_file_path
        status = d.get('status')
        filename = d.get('filename')
        
        if status == 'finished':
            if filename:
                source_file = Path(filename)
                if source_file.exists():
                    saved_file_path = source_file
                    # Immediately copy to our target location to prevent deletion
                    try:
                        audio_path.parent.mkdir(parents=True, exist_ok=True)
                        # Always copy, even if target exists (in case of corruption)
                        shutil.copy2(source_file, audio_path)
                    except Exception:
                        # If copy fails, we'll try to rename later
                        pass
    
    ydl_opts['progress_hooks'] = [progress_hook]
    
    # Simple download - let yt-dlp handle retries and fallbacks
    # Only add fallback player clients if we get specific errors
    info = None
    download_success = False
    last_error = None
    
    # First attempt: use default yt-dlp behavior (works best with cookies)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print("Downloading audio...")
            try:
                info = ydl.extract_info(url, download=True)
                download_success = True
            except Exception as download_error:
                error_str = str(download_error)
                
                # If we get 403 or player response error and have cookies, try different clients
                if ("player response" in error_str.lower() or "403" in error_str or "Forbidden" in error_str) and using_cookies:
                    import time
                    print(f"⚠ Got 403/player response error with web client")
                    print(f"   Error details: {error_str[:300]}")
                    print(f"   Waiting 2 seconds before trying iOS client...")
                    time.sleep(2)  # Brief delay to avoid rate limiting
                    
                    # Try iOS client (often more reliable with cookies)
                    fallback_opts = ydl_opts.copy()
                    fallback_opts['extractor_args'] = {'youtube': {'player_client': 'ios'}}
                    
                    try:
                        with yt_dlp.YoutubeDL(fallback_opts) as ydl_fallback:
                            info = ydl_fallback.extract_info(url, download=True)
                            download_success = True
                            print("✓ iOS client succeeded!")
                    except Exception as ios_error:
                        ios_error_str = str(ios_error)
                        print(f"⚠ iOS client also failed: {ios_error_str[:300]}")
                        print(f"   Waiting 2 seconds before trying Android client...")
                        time.sleep(2)  # Brief delay
                        
                        # Try android client as last resort
                        print(f"⚠ Trying Android client as last resort...")
                        fallback_opts2 = ydl_opts.copy()
                        fallback_opts2['extractor_args'] = {'youtube': {'player_client': 'android'}}
                        
                        try:
                            with yt_dlp.YoutubeDL(fallback_opts2) as ydl_android:
                                info = ydl_android.extract_info(url, download=True)
                                download_success = True
                                print("✓ Android client succeeded!")
                        except Exception as android_error:
                            # If all fail, provide detailed error message
                            android_error_str = str(android_error)[:300]
                            print(f"✗ All player clients failed:")
                            print(f"   Web client: {error_str[:200]}")
                            print(f"   iOS client: {ios_error_str[:200]}")
                            print(f"   Android client: {android_error_str[:200]}")
                            
                            # Determine if this is likely IP blocking vs cookie issue
                            all_errors = error_str + ios_error_str + android_error_str
                            is_ip_block = "403" in all_errors or "Forbidden" in all_errors
                            
                            if is_ip_block:
                                # All download methods failed - this is IP blocking from Streamlit Cloud
                                raise RuntimeError(
                                    f"All download methods failed with 403/Forbidden errors.\n\n"
                                    f"This is likely because YouTube is blocking requests from Streamlit Cloud's IP addresses, "
                                    f"not because your cookies are expired (you just updated them).\n\n"
                                    f"Your cookies are probably fine - the issue is YouTube's anti-bot measures blocking cloud hosting IPs.\n\n"
                                    f"Possible solutions:\n"
                                    f"1. Wait a few minutes and try again (rate limiting)\n"
                                    f"2. Try a different video URL\n"
                                    f"3. Run the app locally where it works (your local IP isn't blocked)\n"
                                    f"4. Consider self-hosting on a VPS with a residential IP\n"
                                ) from download_error
                            else:
                                raise RuntimeError(
                                    f"All download methods failed. Error details:\n"
                                    f"Web: {error_str[:150]}\n"
                                    f"iOS: {ios_error_str[:150]}\n"
                                    f"Android: {android_error_str[:150]}\n\n"
                                    f"If you just updated cookies, this might be temporary. Try again in a few minutes."
                                ) from download_error
                else:
                    # For other errors, raise immediately
                    raise
    except Exception as e:
        last_error = e
        if not download_success:
            raise RuntimeError(f"Failed to download audio: {str(e)}") from e
    
    # Extract metadata and get title for folder renaming
    metadata = {
        'url': url,
        'video_id': video_id,
        'title': info.get('title') if info else None,
        'channel': (info.get('uploader') or info.get('channel')) if info else None,
        'duration': info.get('duration') if info else None,
        'upload_date': info.get('upload_date') if info else None,
    }
    
    # Rename folder to include title if we have it
    if metadata.get('title'):
        new_output_dir = get_output_dir(video_id, metadata['title'])
        if new_output_dir != output_dir and not new_output_dir.exists():
            try:
                output_dir.rename(new_output_dir)
                output_dir = new_output_dir
                # Update paths
                audio_path = output_dir / "audio.m4a"
                meta_path = output_dir / "meta.json"
            except Exception:
                # If rename fails, continue with original directory
                pass
    
    # Ensure audio file has correct extension
    # yt-dlp downloads without extension, so we need to find and rename it
    downloaded_file = None  # Will be set from saved_file_path or found files
    
    # Also check the file saved via progress hook
    if not downloaded_file and saved_file_path and saved_file_path.exists():
        downloaded_file = saved_file_path
    
    if not downloaded_file:
        # Check for file without extension (yt-dlp default behavior)
        potential_file = output_dir / video_id
        if potential_file.exists():
            downloaded_file = potential_file
        else:
            # Look for any audio file in the directory
            audio_files = list(output_dir.glob("*.m4a")) + list(output_dir.glob("*.mp4")) + list(output_dir.glob("*.webm")) + list(output_dir.glob("*.m4v"))
            if audio_files:
                downloaded_file = audio_files[0]
            else:
                # Last resort: find any file that's not meta.json
                all_files = [f for f in output_dir.iterdir() if f.is_file() and f.name != 'meta.json'] if output_dir.exists() else []
                if all_files:
                    downloaded_file = all_files[0]
    
    if downloaded_file and downloaded_file != audio_path:
        # Make sure the target directory exists
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Detect actual file extension
        actual_extension = downloaded_file.suffix if downloaded_file.suffix else ''
        
        # If no extension, try to detect from file content
        if not actual_extension:
            import mimetypes
            mime_type, _ = mimetypes.guess_type(str(downloaded_file))
            if mime_type:
                ext_map = {
                    'audio/mp4': '.m4a',
                    'video/mp4': '.mp4',
                    'audio/webm': '.webm',
                    'video/webm': '.webm',
                }
                actual_extension = ext_map.get(mime_type, '.m4a')
            else:
                actual_extension = '.m4a'  # Default fallback
        
        # Ensure extension is OpenAI-compatible
        if actual_extension not in ['.m4a', '.mp4', '.webm', '.mp3', '.wav', '.flac', '.ogg']:
            actual_extension = '.m4a'  # Force to m4a if unsupported
        
        final_audio_path = audio_path.parent / f"audio{actual_extension}"
        
        downloaded_file.rename(final_audio_path)
        audio_path = final_audio_path  # Update audio_path to reflect actual file
        print(f"✓ Audio file saved as: {audio_path.name}")
    elif not audio_path.exists():
        # Check if file exists with different extension
        for ext in ['.m4a', '.mp4', '.webm', '.mp3']:
            potential_path = audio_path.parent / f"audio{ext}"
            if potential_path.exists():
                audio_path = potential_path
                print(f"✓ Found audio file: {audio_path.name}")
                break
        else:
            # If we still don't have the file, that's a real problem
            raise RuntimeError("Audio file was not downloaded successfully")
    
    # Save metadata
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    
    print(f"✓ Audio downloaded: {audio_path}")
    
    # Clean up temp cookies file if we created one
    if temp_cookies_file and Path(temp_cookies_file).exists():
        try:
            os.unlink(temp_cookies_file)
        except:
            pass  # Ignore cleanup errors
    
    return audio_path, metadata, video_id


