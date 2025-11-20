"""OpenAI Whisper API integration for transcription."""

import json
import time
from pathlib import Path
from typing import Optional
from openai import OpenAI
from openai import APIError, RateLimitError, APIConnectionError

from yt2txt.config import Config
from yt2txt.models import Segment, Transcript


def _chunk_audio_file(audio_path: Path, max_chunk_duration_minutes: int = 10) -> list[Path]:
    """
    Split audio file into time-based chunks using ffmpeg directly.
    Creates valid audio files that OpenAI can process.
    
    Args:
        audio_path: Path to audio file
        max_chunk_duration_minutes: Maximum duration per chunk in minutes
        
    Returns:
        List of paths to chunk files
    """
    try:
        import subprocess
        import json
        
        print(f"  Analyzing audio file...")
        
        # Get audio duration using ffprobe
        probe_cmd = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            str(audio_path)
        ]
        
        result = subprocess.run(probe_cmd, capture_output=True, text=True, check=True)
        probe_data = json.loads(result.stdout)
        total_duration = float(probe_data['format']['duration'])
        
        # Calculate number of chunks needed
        chunk_duration_seconds = max_chunk_duration_minutes * 60
        num_chunks = int((total_duration + chunk_duration_seconds - 1) // chunk_duration_seconds)
        
        if num_chunks == 1:
            return [audio_path]
        
        print(f"  Splitting audio into {num_chunks} chunks ({max_chunk_duration_minutes} min each)...")
        
        chunk_paths = []
        for i in range(num_chunks):
            start_time = i * chunk_duration_seconds
            
            chunk_path = audio_path.parent / f"{audio_path.stem}_chunk{i+1}.m4a"
            
            # Use ffmpeg to extract chunk
            ffmpeg_cmd = [
                'ffmpeg',
                '-i', str(audio_path),
                '-ss', str(start_time),
                '-t', str(chunk_duration_seconds),
                '-c', 'copy',  # Copy codec (no re-encoding)
                '-y',  # Overwrite output file
                str(chunk_path)
            ]
            
            subprocess.run(ffmpeg_cmd, capture_output=True, check=True)
            
            chunk_size_mb = chunk_path.stat().st_size / (1024 * 1024)
            print(f"    Chunk {i+1}/{num_chunks}: {chunk_size_mb:.1f} MB")
            chunk_paths.append(chunk_path)
        
        return chunk_paths
        
    except subprocess.CalledProcessError as e:
        print(f"  ⚠ ffmpeg command failed: {e}")
        print(f"  stderr: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
        raise RuntimeError(
            f"Failed to chunk audio using ffmpeg: {str(e)}. "
            f"Make sure ffmpeg is installed on the system."
        ) from e
    except Exception as e:
        print(f"  ⚠ Audio chunking failed: {e}")
        raise RuntimeError(
            f"Failed to chunk audio file: {str(e)}. "
            f"Make sure ffmpeg is installed on the system."
        ) from e



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
    
    # STEP 1: Speed adjustment disabled due to format compatibility issues
    # The pydub speed adjustment creates files that OpenAI doesn't accept
    # SPEED_FACTOR = 1.25
    # print(f"Optimizing audio (1.25x speed for 20% cost savings)...")
    # audio_path = _speed_up_audio(audio_path, SPEED_FACTOR)
    SPEED_FACTOR = 1.0  # No speed adjustment
    
    # Check file size - OpenAI Whisper has a 25 MB limit
    file_size_bytes = audio_path.stat().st_size
    file_size_mb = file_size_bytes / (1024 * 1024)
    max_size_bytes = 25 * 1024 * 1024  # 25 MB in bytes
    
    # STEP 2: If file is too large, chunk it using pydub
    chunk_paths = [audio_path]
    if file_size_bytes > max_size_bytes:
        print(f"⚠ File size ({file_size_mb:.1f} MB) exceeds OpenAI's 25 MB limit.")
        print(f"  Splitting into chunks using pydub...")
        try:
            chunk_paths = _chunk_audio_file(audio_path, max_chunk_duration_minutes=10)
            print(f"  ✓ Split into {len(chunk_paths)} chunks")
        except Exception as e:
            raise RuntimeError(
                f"Failed to chunk audio file: {str(e)}. "
                f"The audio file is too large ({file_size_mb:.1f} MB) and chunking failed. "
                f"This may be due to missing ffmpeg on Streamlit Cloud."
            ) from e
    
    # Get file size for timeout estimation
    # Calculate timeout: base 5 minutes + 1 minute per 10MB
    timeout_seconds = 300.0 + (file_size_mb / 10) * 60.0
    timeout_seconds = min(timeout_seconds, 1800.0)  # Cap at 30 minutes
    
    # Initialize OpenAI client with dynamic timeout
    client = OpenAI(
        api_key=Config.OPENAI_API_KEY,
        timeout=timeout_seconds
    )
    
    # STEP 3: Transcribe each chunk
    all_segments = []
    detected_language = None
    
    for chunk_idx, chunk_path in enumerate(chunk_paths):
        chunk_num = chunk_idx + 1
        total_chunks = len(chunk_paths)
        
        if total_chunks > 1:
            print(f"Transcribing chunk {chunk_num}/{total_chunks}...")
        else:
            print("Transcribing audio...")
        
        # Transcribe with retries
        last_error = None
        for attempt in range(Config.MAX_RETRIES + 1):
            try:
                if attempt > 0:
                    print(f"  Attempt {attempt + 1}/{Config.MAX_RETRIES + 1}...")
                
                # Show file size info
                chunk_size_mb = chunk_path.stat().st_size / (1024 * 1024)
                print(f"  File size: {chunk_size_mb:.1f} MB")
                
                # Transcribe this chunk
                with open(chunk_path, 'rb') as audio_file:
                    response = client.audio.transcriptions.create(
                        model=Config.MODEL,
                        file=audio_file,
                        response_format="verbose_json",
                        language=None,  # Auto-detect
                    )
                
                # Parse response
                if hasattr(response, 'model_dump'):
                    response_dict = response.model_dump()
                elif hasattr(response, 'dict'):
                    response_dict = response.dict()
                elif isinstance(response, dict):
                    response_dict = response
                else:
                    response_dict = {
                        'text': getattr(response, 'text', ''),
                        'language': getattr(response, 'language', None),
                        'duration': getattr(response, 'duration', None),
                        'segments': getattr(response, 'segments', [])
                    }
                
                # Extract segments
                segments_data = response_dict.get('segments', [])
                if not detected_language:
                    detected_language = response_dict.get('language')
                
                # If no segments but we have text, create a single segment
                if not segments_data and response_dict.get('text'):
                    duration = response_dict.get('duration') or metadata.get('duration', 0)
                    segments_data = [{
                        'start': 0.0,
                        'end': float(duration) if duration else 0.0,
                        'text': response_dict.get('text', '')
                    }]
                
                # Add segments from this chunk
                for seg in segments_data:
                    all_segments.append(seg)
                
                print(f"  ✓ Chunk {chunk_num} complete: {len(segments_data)} segments")
                break  # Success, exit retry loop
                
            except RateLimitError as e:
                last_error = e
                if attempt < Config.MAX_RETRIES:
                    wait_time = 2 ** attempt
                    print(f"  Rate limit hit. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(
                        f"Rate limit exceeded after {Config.MAX_RETRIES + 1} attempts."
                    ) from e
                    
            except APIConnectionError as e:
                last_error = e
                if attempt < Config.MAX_RETRIES:
                    wait_time = 2 ** attempt
                    print(f"  Connection error. Waiting {wait_time} seconds...")
                    time.sleep(wait_time)
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

    
    # STEP 4: Process all segments (no timestamp correction needed since SPEED_FACTOR = 1.0)
    print(f"Processing {len(all_segments)} total segments...")
    segments = [
        Segment(
            start=float(seg.get('start', 0) if isinstance(seg, dict) else getattr(seg, 'start', 0)),
            end=float(seg.get('end', 0) if isinstance(seg, dict) else getattr(seg, 'end', 0)),
            text=(seg.get('text', '') if isinstance(seg, dict) else getattr(seg, 'text', '')).strip()
        )
        for seg in all_segments
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

