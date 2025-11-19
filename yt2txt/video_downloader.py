"""Download video file (not just audio) for slide extraction."""

import shutil
from pathlib import Path
from typing import Dict, Tuple
import yt_dlp
from yt2txt.config import Config
from yt2txt.downloader import extract_video_id, get_output_dir


def download_video(url: str, force: bool = False) -> Tuple[Path, Dict, str]:
    """
    Download video file (for slide extraction).
    
    Args:
        url: YouTube video URL
        force: If True, re-download even if cached
        
    Returns:
        Tuple of (video_path, metadata_dict, video_id)
    """
    video_id = extract_video_id(url)
    output_dir = get_output_dir(video_id, None)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    video_path = output_dir / "video.mp4"
    meta_path = output_dir / "meta.json"
    
    # Check cache - but verify resolution if cached
    if not force and video_path.exists():
        # Check if cached video is high quality
        try:
            import cv2
            cap = cv2.VideoCapture(str(video_path))
            if cap.isOpened():
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                cap.release()
                if width < 640 or height < 360:
                    print(f"⚠ Cached video is low quality ({width}x{height}). Re-downloading...")
                    video_path.unlink()  # Delete low quality cached video
                    if meta_path.exists():
                        meta_path.unlink()
                else:
                    print(f"✓ Using cached video for video {video_id} ({width}x{height})")
        except Exception:
            print(f"✓ Using cached video for video {video_id}")
        
        # If video still exists after quality check, use it
        if video_path.exists():
            # If video exists, we can use it even without metadata
            if meta_path.exists():
                import json
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                        if content:
                            metadata = json.loads(content)
                        else:
                            # Empty file, create basic metadata
                            metadata = {'url': url, 'video_id': video_id}
                except (json.JSONDecodeError, ValueError):
                    # Corrupted metadata file, create basic metadata
                    metadata = {'url': url, 'video_id': video_id}
            else:
                # No metadata file, create basic one
                metadata = {'url': url, 'video_id': video_id}
            
            return video_path, metadata, video_id
    
    # Configure yt-dlp for video download (lowest quality to save space)
    # Use same post-processing workaround as audio downloader
    import yt_dlp.postprocessor
    original_run = yt_dlp.postprocessor.PostProcessor.run
    
    def noop_run(self, information):
        """No-op post-processor that does nothing."""
        return [], information
    
    yt_dlp.postprocessor.PostProcessor.run = noop_run
    
    # Also patch FixupM4a specifically
    try:
        from yt_dlp.postprocessor import FixupM4a
        original_fixup_run = FixupM4a.run
        FixupM4a.run = noop_run
        fixup_patched = True
    except:
        fixup_patched = False
    
    # Track downloaded file via progress hook
    saved_video_path = None
    
    def progress_hook(d):
        """Hook to save video path when download completes."""
        nonlocal saved_video_path
        status = d.get('status')
        filename = d.get('filename')
        
        if status == 'finished':
            if filename:
                source_file = Path(filename)
                if source_file.exists():
                    saved_video_path = source_file
                    # Immediately copy to our target location to prevent deletion
                    try:
                        video_path.parent.mkdir(parents=True, exist_ok=True)
                        if not video_path.exists():
                            shutil.copy2(source_file, video_path)
                            print(f"✓ Video saved via progress hook: {video_path.name}")
                    except Exception as copy_error:
                        print(f"⚠ Error copying video: {copy_error}")
    
    # Use HIGHEST quality video for slide extraction (need readable text)
    # Format 160 = 256x144 (too low), we need at least 480p
    # Prefer combined formats (no merging needed) but exclude low quality
    ydl_opts = {
        'format': 'best[height>=720]/best[height>=480]/best[height>=360]/worst[height>=360]',
        'outtmpl': str(video_path.with_suffix('')),
        'quiet': False,  # Show output for debugging
        'no_warnings': False,
        'extract_flat': False,
        'postprocessors': [],
        'nopostoverwrites': True,
        'progress_hooks': [progress_hook],
        # Basic options - let yt-dlp handle bot detection with its defaults
    }
    
    metadata = {}
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl._postprocessors = []
            print("Downloading video (for slide extraction)...")
            print(f"   Output path: {video_path}")
            
            try:
                info = ydl.extract_info(url, download=True)
                print(f"   Download completed, checking for file...")
            except Exception as download_error:
                # Handle post-processing errors (same as audio downloader)
                error_str = str(download_error)
                print(f"   Download error: {error_str}")
                if "Postprocessing" in error_str or "postprocess" in error_str.lower() or "FixupM4a" in error_str or "Expecting value" in error_str:
                    # Post-processing error is expected - try to get info without downloading
                    print("⚠ Post-processing error (video may still be downloaded)...")
                    try:
                        # Use a fresh yt-dlp instance to get info
                        temp_ydl = yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True})
                        info = temp_ydl.extract_info(url, download=False)
                    except Exception as info_error:
                        print(f"⚠ Could not extract video info: {info_error}")
                        info = {}
                else:
                    raise
            
            print(f"   Progress hook saved file: {saved_video_path}")
            print(f"   Video path exists: {video_path.exists()}")
            
            # Extract metadata
            metadata = {
                'url': url,
                'video_id': video_id,
                'title': info.get('title') if info else None,
                'channel': (info.get('uploader') or info.get('channel')) if info else None,
                'duration': info.get('duration') if info else None,
                'upload_date': info.get('upload_date') if info else None,
            }
            
            # Ensure video file has correct extension
            downloaded_video = None
            
            # Check file saved via progress hook first
            if not video_path.exists() and saved_video_path and saved_video_path.exists():
                downloaded_video = saved_video_path
            
            if not video_path.exists() and not downloaded_video:
                # Look for downloaded file
                video_files = list(output_dir.glob("*.mp4"))
                if video_files:
                    downloaded_video = video_files[0]
                else:
                    # Check for file without extension
                    potential_file = output_dir / video_id
                    if potential_file.exists():
                        downloaded_video = potential_file
                    else:
                        # Check for any video-like file
                        all_files = [f for f in output_dir.iterdir() if f.is_file() and f.name != 'meta.json' and f.name != 'audio.m4a']
                        if all_files:
                            downloaded_video = all_files[0]
            
            if downloaded_video and downloaded_video != video_path:
                if not video_path.exists():
                    downloaded_video.rename(video_path)
                    print(f"✓ Renamed video file to: {video_path.name}")
                else:
                    # Both exist, keep the one from progress hook
                    if downloaded_video != video_path:
                        downloaded_video.unlink()  # Delete duplicate
            
            # Save metadata (even if basic)
            if not metadata:
                metadata = {'url': url, 'video_id': video_id}
            
            try:
                with open(meta_path, 'w', encoding='utf-8') as f:
                    import json
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
            except Exception as meta_error:
                print(f"⚠ Warning: Could not save metadata: {meta_error}")
            
            if video_path.exists():
                file_size = video_path.stat().st_size / (1024 * 1024)  # Size in MB
                # Check actual video resolution
                try:
                    import cv2
                    cap = cv2.VideoCapture(str(video_path))
                    if cap.isOpened():
                        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        cap.release()
                        print(f"✓ Video downloaded: {video_path.name} ({file_size:.1f} MB, {width}x{height})")
                        if width < 640 or height < 360:
                            print(f"  ⚠ WARNING: Video resolution is very low! This will produce poor quality slides.")
                            print(f"  ⚠ The video may only be available in low quality on YouTube.")
                    else:
                        print(f"✓ Video downloaded: {video_path.name} ({file_size:.1f} MB)")
                except Exception:
                    print(f"✓ Video downloaded: {video_path.name} ({file_size:.1f} MB)")
            else:
                # Debug: Check what files actually exist
                print(f"⚠ Video file not found at: {video_path}")
                print(f"   Checking output directory: {output_dir}")
                if output_dir.exists():
                    all_files = list(output_dir.iterdir())
                    print(f"   Files in directory: {[f.name for f in all_files]}")
                    # Check if saved_video_path exists
                    if saved_video_path and saved_video_path.exists():
                        print(f"   Found video via progress hook: {saved_video_path}")
                        try:
                            saved_video_path.rename(video_path)
                            print(f"✓ Renamed video file to: {video_path.name}")
                        except Exception as rename_error:
                            print(f"⚠ Error renaming: {rename_error}")
                            raise RuntimeError(f"Video file exists but could not be renamed: {saved_video_path}")
                    else:
                        raise RuntimeError("Video file was not downloaded successfully")
                else:
                    raise RuntimeError("Output directory does not exist")
            
    except Exception as e:
        # Check if video file exists despite the error
        if video_path.exists():
            print(f"⚠ Error occurred but video file exists: {video_path}")
            # Create basic metadata if we don't have it
            if not metadata:
                metadata = {'url': url, 'video_id': video_id}
            try:
                with open(meta_path, 'w', encoding='utf-8') as f:
                    import json
                    json.dump(metadata, f, indent=2, ensure_ascii=False)
            except:
                pass
        else:
            # Clean up any partial metadata file
            if meta_path.exists():
                try:
                    meta_path.unlink()
                except:
                    pass
            raise RuntimeError(f"Failed to download video: {str(e)}") from e
    finally:
        # Restore original post-processor run method
        yt_dlp.postprocessor.PostProcessor.run = original_run
        if fixup_patched:
            from yt_dlp.postprocessor import FixupM4a
            FixupM4a.run = original_fixup_run
    
    return video_path, metadata, video_id

