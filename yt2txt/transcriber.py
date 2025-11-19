"""OpenAI Whisper API integration for transcription."""

import json
import time
from pathlib import Path
from typing import Optional
from openai import OpenAI
from openai import APIError, RateLimitError, APIConnectionError

from yt2txt.config import Config
from yt2txt.models import Segment, Transcript


def _compress_audio(audio_path: Path, max_size_bytes: int) -> Path:
    """
    Compress audio file to fit within size limit.
    Tries multiple methods: pydub, then falls back to re-downloading lower quality.
    """
    original_size = audio_path.stat().st_size
    
    # Try pydub compression first (requires ffmpeg)
    try:
        from pydub import AudioSegment
        
        # Check if ffmpeg is available (pydub needs it)
        try:
            AudioSegment.converter = "ffmpeg"  # This will fail if ffmpeg not found
            # Test if we can actually use it
            test_audio = AudioSegment.silent(duration=100)  # Quick test
        except Exception as ffmpeg_error:
            raise ImportError(f"ffmpeg not available: {ffmpeg_error}. Compression requires ffmpeg.")
        
        # Load audio
        audio = AudioSegment.from_file(str(audio_path))
        
        # Calculate target bitrate to get under limit (with safety margin)
        duration_seconds = len(audio) / 1000.0
        # Calculate bitrate needed: (size_bytes * 8 bits) / (duration_seconds * 1000) = kbps
        target_bitrate_kbps = int((max_size_bytes * 8) / (duration_seconds * 1000)) - 20  # 20 kbps safety margin
        
        # Don't go below 24 kbps (minimum for speech), but be aggressive to fit under limit
        target_bitrate_kbps = max(24, min(target_bitrate_kbps, 48))  # More aggressive - cap at 48 kbps
        
        # Export as compressed m4a
        compressed_path = audio_path.parent / f"{audio_path.stem}_compressed.m4a"
        print(f"  Attempting compression to {target_bitrate_kbps} kbps...")
        
        audio.export(
            str(compressed_path),
            format="m4a",
            bitrate=f"{target_bitrate_kbps}k",
            codec="aac"
        )
        
        compressed_size = compressed_path.stat().st_size
        print(f"  Compressed: {original_size / (1024*1024):.1f} MB -> {compressed_size / (1024*1024):.1f} MB")
        
        # If still too large, try even lower bitrate (more aggressive)
        if compressed_size > max_size_bytes:
            target_bitrate_kbps = int((max_size_bytes * 8) / (duration_seconds * 1000)) - 40
            target_bitrate_kbps = max(24, target_bitrate_kbps)  # Go as low as 24 kbps if needed
            print(f"  Still too large, trying {target_bitrate_kbps} kbps...")
            audio.export(
                str(compressed_path),
                format="m4a",
                bitrate=f"{target_bitrate_kbps}k",
                codec="aac"
            )
            compressed_size = compressed_path.stat().st_size
            print(f"  Final size: {compressed_size / (1024*1024):.1f} MB")
        
        final_size = compressed_path.stat().st_size
        if final_size <= max_size_bytes:
            print(f"  ✓ Successfully compressed to {final_size / (1024*1024):.2f} MB")
            return compressed_path
        else:
            print(f"  ⚠ Compression still resulted in file over limit: {final_size / (1024*1024):.2f} MB")
            # Try one more time with absolute minimum bitrate
            target_bitrate_kbps = max(24, int((max_size_bytes * 8) / (duration_seconds * 1000)) - 50)
            print(f"  Trying absolute minimum bitrate: {target_bitrate_kbps} kbps...")
            audio.export(
                str(compressed_path),
                format="m4a",
                bitrate=f"{target_bitrate_kbps}k",
                codec="aac"
            )
            final_size = compressed_path.stat().st_size
            if final_size <= max_size_bytes:
                print(f"  ✓ Successfully compressed to {final_size / (1024*1024):.2f} MB")
                return compressed_path
            else:
                compressed_path.unlink()  # Delete failed compression
                raise ValueError(f"Compression failed: file still {final_size / (1024*1024):.2f} MB (limit: 25 MB)")
        
    except ImportError:
        print("⚠ pydub not available. ffmpeg may be required for compression.")
        raise
    except Exception as e:
        print(f"⚠ Compression failed: {e}")
        # Clean up if compressed file exists but is invalid
        compressed_path = audio_path.parent / f"{audio_path.stem}_compressed.m4a"
        if compressed_path.exists():
            try:
                compressed_path.unlink()
            except:
                pass
        raise


def transcribe_audio(
    audio_path: Path,
    video_id: str,
    url: str,
    metadata: dict,
    force: bool = False
) -> Transcript:
    """
    Transcribe audio using OpenAI Whisper API.
    
    Args:
        audio_path: Path to audio file
        video_id: YouTube video ID
        url: YouTube video URL
        metadata: Video metadata dictionary
        force: If True, re-transcribe even if cached
        
    Returns:
        Transcript object with segments
    """
    output_dir = audio_path.parent
    transcript_path = output_dir / "transcript.json"
    
    # Check cache
    if not force and transcript_path.exists():
        print(f"✓ Using cached transcript for video {video_id}")
        with open(transcript_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        segments = [
            Segment(start=s['start'], end=s['end'], text=s['text'])
            for s in data.get('segments', [])
        ]
        
        return Transcript(
            video_id=data.get('video_id', video_id),
            url=data.get('url', url),
            title=data.get('title'),
            channel=data.get('channel'),
            duration=data.get('duration'),
            language=data.get('language'),
            segments=segments
        )
    
    # Validate API key
    Config.validate()
    
    # Check file size - OpenAI Whisper has a 25 MB limit
    file_size_bytes = audio_path.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
    max_size_bytes = 25 * 1024 * 1024  # 25 MB in bytes
    
    # If file is too large, we need to compress it
    if file_size_bytes > max_size_bytes:
        print(f"⚠ File size ({file_size_mb:.1f} MB) exceeds OpenAI's 25 MB limit. Attempting compression...")
        try:
            audio_path = _compress_audio(audio_path, max_size_bytes)
            file_size_mb = audio_path.stat().st_size / (1024 * 1024)
            if audio_path.stat().st_size > max_size_bytes:
                raise ValueError(f"Compressed file still too large: {file_size_mb:.1f} MB")
            print(f"✓ Compressed to {file_size_mb:.1f} MB")
        except Exception as e:
            # Check if it's an ffmpeg issue
            error_str = str(e).lower()
            if 'ffmpeg' in error_str or 'not found' in error_str:
                error_msg = (
                    f"File too large ({file_size_mb:.1f} MB) and compression requires ffmpeg, "
                    f"which is not available on this system. "
                    f"Please try a shorter video (under ~20 minutes) or contact support."
                )
            else:
                error_msg = (
                    f"File too large ({file_size_mb:.1f} MB) and compression failed: {str(e)}. "
                    f"Please try a shorter video (under ~20 minutes)."
                )
            raise RuntimeError(error_msg) from e
    
    # Get file size for timeout estimation
    # Calculate timeout: base 5 minutes + 1 minute per 10MB
    timeout_seconds = 300.0 + (file_size_mb / 10) * 60.0
    timeout_seconds = min(timeout_seconds, 1800.0)  # Cap at 30 minutes
    
    # Initialize OpenAI client with dynamic timeout
    client = OpenAI(
        api_key=Config.OPENAI_API_KEY,
        timeout=timeout_seconds
    )
    
    # Transcribe with retries
    last_error = None
    for attempt in range(Config.MAX_RETRIES + 1):
        try:
            if attempt > 0:
                print(f"Transcribing audio (attempt {attempt + 1}/{Config.MAX_RETRIES + 1})...")
            else:
                print("Transcribing audio...")
            
            # Show file size info
            file_size_mb = audio_path.stat().st_size / (1024 * 1024)
            print(f"  File size: {file_size_mb:.1f} MB")
            if file_size_mb > 20:
                print(f"  Note: Large file - upload and processing may take several minutes...")
            
            # Use a simpler progress indicator that doesn't fake progress
            print("  Uploading and processing (this may take a while for large files)...")
            
            # Reopen file for each attempt to ensure it's fresh
            with open(audio_path, 'rb') as audio_file:
                response = client.audio.transcriptions.create(
                    model=Config.MODEL,
                    file=audio_file,
                    response_format="verbose_json",
                    language=None,  # Auto-detect
                )
            
            # Parse response - verbose_json returns a dict, but SDK might wrap it
            # Convert to dict if it's a model object
            if hasattr(response, 'model_dump'):
                response_dict = response.model_dump()
            elif hasattr(response, 'dict'):
                response_dict = response.dict()
            elif isinstance(response, dict):
                response_dict = response
            else:
                # Try to access as attributes
                response_dict = {
                    'text': getattr(response, 'text', ''),
                    'language': getattr(response, 'language', None),
                    'duration': getattr(response, 'duration', None),
                    'segments': getattr(response, 'segments', [])
                }
            
            # Extract segments and language
            segments_data = response_dict.get('segments', [])
            detected_language = response_dict.get('language')
            
            # If no segments but we have text, create a single segment
            if not segments_data and response_dict.get('text'):
                # Create a single segment with the full text
                duration = response_dict.get('duration') or metadata.get('duration', 0)
                segments_data = [{
                    'start': 0.0,
                    'end': float(duration) if duration else 0.0,
                    'text': response_dict.get('text', '')
                }]
            
            segments = [
                Segment(
                    start=float(seg.get('start', 0) if isinstance(seg, dict) else getattr(seg, 'start', 0)),
                    end=float(seg.get('end', 0) if isinstance(seg, dict) else getattr(seg, 'end', 0)),
                    text=(seg.get('text', '') if isinstance(seg, dict) else getattr(seg, 'text', '')).strip()
                )
                for seg in segments_data
            ]
            
            transcript = Transcript(
                video_id=video_id,
                url=url,
                title=metadata.get('title'),
                channel=metadata.get('channel'),
                duration=metadata.get('duration'),
                language=detected_language,
                segments=segments
            )
            
            print(f"✓ Transcription complete: {len(segments)} segments")
            return transcript
            
        except RateLimitError as e:
            last_error = e
            if attempt < Config.MAX_RETRIES:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"Rate limit hit. Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                # Continue to next iteration to retry
                continue
            else:
                raise RuntimeError(
                    f"Rate limit exceeded after {Config.MAX_RETRIES + 1} attempts. "
                    f"Please try again later."
                ) from e
                
        except APIConnectionError as e:
            last_error = e
            if attempt < Config.MAX_RETRIES:
                wait_time = 2 ** attempt
                print(f"Connection error. Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                # Continue to next iteration to retry
                continue
            else:
                raise RuntimeError(
                    f"Connection error after {Config.MAX_RETRIES + 1} attempts: {str(e)}"
                ) from e
                
        except APIError as e:
            error_msg = str(e)
            
            # Check if it's an HTML response (502/503 gateway errors)
            is_html_error = "<!DOCTYPE html>" in error_msg or "<html" in error_msg.lower()
            is_5xx_error = hasattr(e, 'status_code') and e.status_code and 500 <= e.status_code < 600
            
            # Retry on 5xx server errors (including 502 Bad Gateway)
            if (is_html_error or is_5xx_error) and attempt < Config.MAX_RETRIES:
                last_error = e
                wait_time = 2 ** attempt
                if is_html_error:
                    print(f"Server error (502 Bad Gateway). Waiting {wait_time} seconds before retry...")
                else:
                    print(f"Server error ({getattr(e, 'status_code', '5xx')}). Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                continue
            
            # Non-retryable API errors
            if "quota" in error_msg.lower() or "billing" in error_msg.lower():
                raise RuntimeError(
                    f"OpenAI API quota/billing error: {error_msg}. "
                    f"Please check your OpenAI account."
                ) from e
            
            # Clean up HTML error messages
            if is_html_error:
                raise RuntimeError(
                    "OpenAI API server error (502 Bad Gateway). "
                    "This is a temporary issue on OpenAI's servers. Please try again in a few minutes."
                ) from e
            
            raise RuntimeError(f"OpenAI API error: {error_msg}") from e
            
        except Exception as e:
            raise RuntimeError(f"Unexpected error during transcription: {str(e)}") from e
    
    # Should not reach here, but just in case
    raise RuntimeError(f"Failed to transcribe after {Config.MAX_RETRIES + 1} attempts") from last_error

