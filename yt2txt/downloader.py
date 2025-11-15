"""YouTube audio downloader using yt-dlp."""

import re
import json
import shutil
from pathlib import Path
from typing import Dict, Optional, Tuple
import yt_dlp
from yt2txt.config import Config


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
    
    audio_path = output_dir / "audio.m4a"
    meta_path = output_dir / "meta.json"
    
    # Check cache
    if not force and audio_path.exists() and meta_path.exists():
        print(f"✓ Using cached audio for video {video_id}")
        with open(meta_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        return audio_path, metadata, video_id
    
    # Configure yt-dlp for audio-only m4a download (no ffmpeg required)
    # We need to completely disable post-processing to avoid ffmpeg dependency
    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/best[ext=m4a]/best',
        'outtmpl': str(audio_path.with_suffix('')),
        'quiet': True,  # Suppress yt-dlp output
        'no_warnings': False,  # Keep warnings but they'll be quieter
        'extract_flat': False,
        'postprocessors': [],  # Disable all post-processing (no ffmpeg needed)
        'nopostoverwrites': True,
        'postprocessor_args': {},  # No post-processor arguments
        'keepvideo': False,
        'noplaylist': True,
        # Disable automatic post-processor selection
        'prefer_insecure': False,
        # Try to prevent FixupM4a from running
        'writethumbnail': False,
        'writesubtitles': False,
        'writeautomaticsub': False,
    }
    
    # Monkey-patch to prevent post-processors from running
    # This is a workaround for yt-dlp trying to run FixupM4a even with empty postprocessors
    import yt_dlp.postprocessor
    original_run = yt_dlp.postprocessor.PostProcessor.run
    
    def noop_run(self, information):
        """No-op post-processor that does nothing."""
        return [], information
    
    # Temporarily replace the run method
    yt_dlp.postprocessor.PostProcessor.run = noop_run
    
    # Also patch FixupM4a specifically
    try:
        from yt_dlp.postprocessor import FixupM4a
        original_fixup_run = FixupM4a.run
        FixupM4a.run = noop_run
        fixup_patched = True
    except:
        fixup_patched = False
    
    metadata = {}
    postprocessor_patched = True
    
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
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Also disable post-processors on the instance
            ydl._postprocessors = []
            print("Downloading audio...")
            
            # Monitor for file creation during download
            downloaded_file_path = None
            
            try:
                info = ydl.extract_info(url, download=True)
            except Exception as download_error:
                # Even if post-processing fails, the file might be downloaded
                error_str = str(download_error)
                
                if "Postprocessing" in error_str or "postprocess" in error_str.lower() or "FixupM4a" in error_str:
                    # Post-processing error is expected - we handle it silently
                    # Try to extract info without downloading again
                    try:
                        info = ydl.extract_info(url, download=False)
                    except:
                        # If that fails, we'll try to find the downloaded file anyway
                        info = {}
                    # Check if file exists despite error
                    potential_file = output_dir / video_id
                    if potential_file.exists():
                        downloaded_file_path = potential_file
                else:
                    # Re-raise if it's a different error
                    raise
            
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
            downloaded_file = downloaded_file_path  # Use file found during error handling if available
            
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
                    audio_files = list(output_dir.glob("*.m4a")) + list(output_dir.glob("*.m4v"))
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
                downloaded_file.rename(audio_path)
                print(f"✓ Renamed audio file to: {audio_path.name}")
            elif not audio_path.exists():
                # If we still don't have the file, that's a real problem
                raise RuntimeError("Audio file was not downloaded successfully")
            
            # Save metadata
            with open(meta_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            
            print(f"✓ Audio downloaded: {audio_path}")
            
    except Exception as e:
        # Check if file exists despite the error
        if audio_path.exists():
            # File was saved successfully, just need metadata
            if not metadata.get('title'):
                try:
                    with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'extract_flat': False}) as ydl:
                        info = ydl.extract_info(url, download=False)
                        metadata = {
                            'url': url,
                            'video_id': video_id,
                            'title': info.get('title'),
                            'channel': info.get('uploader') or info.get('channel'),
                            'duration': info.get('duration'),
                            'upload_date': info.get('upload_date'),
                        }
                        with open(meta_path, 'w', encoding='utf-8') as f:
                            json.dump(metadata, f, indent=2, ensure_ascii=False)
                except:
                    pass
        else:
            raise RuntimeError(f"Failed to download audio: {str(e)}") from e
    finally:
        # Restore original post-processor run method
        if postprocessor_patched:
            yt_dlp.postprocessor.PostProcessor.run = original_run
        if fixup_patched:
            from yt_dlp.postprocessor import FixupM4a
            FixupM4a.run = original_fixup_run
    
    return audio_path, metadata, video_id

