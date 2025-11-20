"""Streamlit web application for YouTube video transcription and analysis."""

import streamlit as st
import sys
import os
from pathlib import Path
import shutil
import time
import threading

# Add the project root to the path so we can import yt2txt modules
# Try to handle path issues more safely
try:
    project_root = Path(__file__).parent.resolve()
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
except Exception:
    # If path setup fails, continue anyway
    pass

# Import modules - if any fail, the app will show an error
from yt2txt.config import Config
from yt2txt.downloader import download_audio
from yt2txt.video_downloader import download_video
from yt2txt.transcriber import transcribe_audio
from yt2txt.analyzer import analyze_transcript
from yt2txt.writers.txt_writer import write_txt
from yt2txt.writers.json_writer import write_json
from yt2txt.writers.srt_writer import write_srt
from yt2txt.writers.analysis_writer import write_analysis
from yt2txt.formatter import format_transcript
from yt2txt.models import Transcript, Segment
import json
import re


# Page configuration
st.set_page_config(
    page_title="YouTube Video Transcriber",
    page_icon="🎥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load secrets from Streamlit Cloud and update Config
# This happens AFTER page config when st.secrets is safe to access
def load_streamlit_secrets():
    """Load secrets from Streamlit Cloud into Config."""
    try:
        if not hasattr(st, 'secrets'):
            return
        if not st.secrets:
            return
        if 'OPENAI_API_KEY' in st.secrets:
            Config.OPENAI_API_KEY = st.secrets['OPENAI_API_KEY']
        if 'MODEL' in st.secrets:
            Config.MODEL = st.secrets['MODEL']
        if 'ANALYSIS_MODEL' in st.secrets:
            Config.ANALYSIS_MODEL = st.secrets['ANALYSIS_MODEL']
        if 'OUT_DIR' in st.secrets:
            Config.OUT_DIR = Path(st.secrets['OUT_DIR']).resolve()
        if 'MAX_RETRIES' in st.secrets:
            Config.MAX_RETRIES = int(st.secrets['MAX_RETRIES'])
    except (AttributeError, TypeError, KeyError, ValueError):
        # Silently fail - will use .env file values
        pass

load_streamlit_secrets()

# Custom CSS for better styling
st.markdown("""
    <style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stButton>button {
        width: 100%;
    }
    /* Prevent numbers from breaking across lines in chat messages */
    .stChatMessage {
        word-break: break-word;
    }
    .stChatMessage p, .stChatMessage div {
        white-space: pre-wrap;
        word-break: break-word;
    }
    /* Keep numbers together - prevent breaking within number sequences */
    .stChatMessage * {
        font-variant-numeric: tabular-nums;
    }
    /* Improved text formatting - clean black on white with darker font */
    .stMarkdown, .stText, .stTextArea {
        color: #1a1a1a !important;
        font-weight: 500 !important;
    }
    .transcript-text {
        color: #000000 !important;
        font-weight: 600 !important;
        font-size: 1.05em !important;
        line-height: 1.8 !important;
        background-color: #ffffff !important;
        padding: 1rem !important;
    }
    .analysis-text {
        color: #1a1a1a !important;
        font-weight: 500 !important;
        font-size: 1em !important;
        line-height: 1.7 !important;
        background-color: #ffffff !important;
        padding: 1rem !important;
    }
    /* Make text areas more readable */
    .stTextArea textarea {
        color: #000000 !important;
        font-weight: 500 !important;
        background-color: #ffffff !important;
    }
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if 'transcript' not in st.session_state:
    st.session_state.transcript = None
if 'analysis_text' not in st.session_state:
    st.session_state.analysis_text = None
if 'formatted_transcript' not in st.session_state:
    st.session_state.formatted_transcript = None
if 'output_dir' not in st.session_state:
    st.session_state.output_dir = None
if 'chat_messages' not in st.session_state:
    st.session_state.chat_messages = []
if 'processing' not in st.session_state:
    st.session_state.processing = False
if 'transcript_history' not in st.session_state:
    st.session_state.transcript_history = []  # List of (video_id, title, url, transcript_path)
if 'current_video_url' not in st.session_state:
    st.session_state.current_video_url = None


def transcribe_with_progress(audio_path: Path, video_id: str, url: str, metadata: dict, force: bool = False):
    """
    Transcribe audio with a progress bar showing estimated progress.
    Since OpenAI API doesn't provide real-time progress, we estimate based on:
    - File upload time (estimated from file size)
    - Processing time (estimated from audio duration)
    """
    from yt2txt.transcriber import transcribe_audio
    
    # Get file size and duration for estimation
    file_size_mb = audio_path.stat().st_size / (1024 * 1024)
    audio_duration = metadata.get('duration', 0)  # in seconds
    
    # Estimate times (conservative estimates)
    # Upload: assume ~0.5 MB/s (conservative for large files)
    upload_time_estimate = max(10, file_size_mb / 0.5)  # at least 10 seconds
    
    # Processing: assume ~0.5x real-time (conservative - API is usually faster)
    processing_time_estimate = max(30, audio_duration * 0.5)  # at least 30 seconds
    
    total_time_estimate = upload_time_estimate + processing_time_estimate
    
    # Create progress bar and status container
    # Note: Since Streamlit blocks during API calls, we show initial status and completion
    progress_bar = st.progress(0)
    status_container = st.empty()
    
    # Show initial status with estimates
    status_container.markdown(f"""
    **📤 Uploading & Processing Audio**
    
    - 📁 File size: **{file_size_mb:.1f} MB**  
    - ⏱️ Audio duration: **{int(audio_duration)}s**  
    - ⏳ Estimated time: **~{int(total_time_estimate)}s**
    
    *This may take a few minutes for large files. Please wait...*
    """)
    progress_bar.progress(0.1)  # Show we've started (10%)
    
    start_time = time.time()
    
    try:
        # Call transcribe_audio - this will block, so UI won't update during
        result = transcribe_audio(audio_path, video_id, url, metadata, force=force)
        
        # Update to show completion
        elapsed = time.time() - start_time
        progress_bar.progress(1.0)
        status_container.markdown(f"""
        **✓ Transcription Complete!**
        
        - ⏱️ Actual time: **{int(elapsed)}s**  
        - 📊 Estimated time: **~{int(total_time_estimate)}s**
        - ✅ Status: **Success**
        """)
        time.sleep(1.5)  # Show completion message briefly
        
        return result
    except Exception as e:
        # Show error
        progress_bar.progress(0)
        status_container.error(f"❌ **Error during transcription:** {str(e)}")
        raise e


def fix_number_formatting(text: str) -> str:
    """
    Wrap numbers in spans to prevent them from breaking across lines.
    This fixes the issue where numbers like '100 million' break into '1 0 0 m i l l i o n'.
    
    Uses a simple approach that avoids complex lookbehinds which can cause regex errors.
    """
    # Strategy: Process text in chunks, avoiding HTML tags
    # Split by HTML tags to process text content separately from tags
    
    # First, handle number ranges (most specific pattern)
    text = re.sub(
        r'(\d+)\s+to\s+(\d+)\s*(million|billion|trillion|thousand|hundred|per\s+\w+)?',
        r'<span style="white-space: nowrap;">\1 to \2\3</span>',
        text,
        flags=re.IGNORECASE
    )
    
    # Then handle number + scale word combinations
    text = re.sub(
        r'(\$|€|£)?\s*(\d+[\d,\s.]*)\s+(million|billion|trillion|thousand|hundred)',
        r'<span style="white-space: nowrap;">\1\2 \3</span>',
        text,
        flags=re.IGNORECASE
    )
    
    # For standalone numbers, use a simpler approach:
    # Process the text by splitting on HTML tags, then processing text parts only
    parts = []
    last_end = 0
    
    # Find all HTML tags (including our newly added spans)
    for match in re.finditer(r'<[^>]+>', text):
        # Process text before the tag
        before_text = text[last_end:match.start()]
        if before_text:
            # Wrap standalone numbers in the text (not in tags)
            before_text = re.sub(
                r'\b(\d{2,}[\d,.]*)\b',
                r'<span style="white-space: nowrap;">\1</span>',
                before_text
            )
            parts.append(before_text)
        
        # Add the tag itself unchanged
        parts.append(match.group(0))
        last_end = match.end()
    
    # Process remaining text after last tag
    remaining_text = text[last_end:]
    if remaining_text:
        remaining_text = re.sub(
            r'\b(\d{2,}[\d,.]*)\b',
            r'<span style="white-space: nowrap;">\1</span>',
            remaining_text
        )
        parts.append(remaining_text)
    
    # If no HTML tags found, process entire text
    if not parts:
        text = re.sub(
            r'\b(\d{2,}[\d,.]*)\b',
            r'<span style="white-space: nowrap;">\1</span>',
            text
        )
        return text
    
    return ''.join(parts)


def transcribe_with_progress(audio_path: Path, video_id: str, url: str, metadata: dict, force: bool = False):
    """
    Transcribe audio with a progress bar showing estimated progress.
    Since OpenAI API doesn't provide real-time progress, we estimate based on:
    - File upload time (estimated from file size)
    - Processing time (estimated from audio duration)
    """
    from yt2txt.transcriber import transcribe_audio
    
    # Get file size and duration for estimation
    file_size_mb = audio_path.stat().st_size / (1024 * 1024)
    audio_duration = metadata.get('duration', 0)  # in seconds
    
    # Estimate times (conservative estimates)
    # Upload: assume ~0.5 MB/s (conservative for large files)
    upload_time_estimate = max(10, file_size_mb / 0.5)  # at least 10 seconds
    
    # Processing: assume ~0.5x real-time (conservative - API is usually faster)
    processing_time_estimate = max(30, audio_duration * 0.5)  # at least 30 seconds
    
    total_time_estimate = upload_time_estimate + processing_time_estimate
    
    # Create progress bar and status container
    # Note: Since Streamlit blocks during API calls, we show initial status and completion
    progress_bar = st.progress(0)
    status_container = st.empty()
    
    # Show initial status with estimates
    status_container.markdown(f"""
    **📤 Uploading & Processing Audio**
    
    - 📁 File size: **{file_size_mb:.1f} MB**  
    - ⏱️ Audio duration: **{int(audio_duration)}s**  
    - ⏳ Estimated time: **~{int(total_time_estimate)}s**
    
    *This may take a few minutes for large files. Please wait...*
    """)
    progress_bar.progress(0.1)  # Show we've started (10%)
    
    start_time = time.time()
    
    try:
        # Call transcribe_audio - this will block, so UI won't update during
        result = transcribe_audio(audio_path, video_id, url, metadata, force=force)
        
        # Update to show completion
        elapsed = time.time() - start_time
        progress_bar.progress(1.0)
        status_container.markdown(f"""
        **✓ Transcription Complete!**
        
        - ⏱️ Actual time: **{int(elapsed)}s**  
        - 📊 Estimated time: **~{int(total_time_estimate)}s**
        - ✅ Status: **Success**
        """)
        time.sleep(1.5)  # Show completion message briefly
        
        return result
    except Exception as e:
        # Show error
        progress_bar.progress(0)
        status_container.error(f"❌ **Error during transcription:** {str(e)}")
        raise e


def process_video_streamlit(url: str, analyze: bool):
    """Process video with Streamlit progress indicators."""
    try:
        # Validate configuration first
        with st.spinner("Validating configuration..."):
            Config.validate()
            st.success("✓ Configuration validated")
        
        # Use persistent output directory for caching (not temp - cache needs to persist!)
        # This allows transcripts to be cached across runs, saving API costs
        persistent_out_dir = Config.OUT_DIR.resolve()
        persistent_out_dir.mkdir(parents=True, exist_ok=True)
        original_out_dir = Config.OUT_DIR
        Config.OUT_DIR = persistent_out_dir
        
        try:
            # Download audio
            with st.spinner("Downloading audio from YouTube..."):
                audio_path, metadata, video_id = download_audio(url, force=False)
                output_dir = audio_path.parent
                st.session_state.output_dir = output_dir
                
                # Check if using cached audio
                audio_cached = audio_path.exists()
                if audio_cached:
                    st.info("ℹ️ Using cached audio file - video was previously downloaded")
            
            # Check if transcript is already cached before transcribing
            # Use the same path that transcribe_audio() uses (audio_path.parent)
            transcript_path = output_dir / "transcript.json"  # output_dir = audio_path.parent
            transcript_cached = transcript_path.exists()
            
            # If not found at expected path, search by video_id in case folder name changed
            if not transcript_cached and persistent_out_dir.exists():
                # Search for transcript.json files that contain this video_id
                for transcript_file in persistent_out_dir.rglob("transcript.json"):
                    try:
                        with open(transcript_file, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if data.get('video_id') == video_id:
                                # Found transcript with matching video_id!
                                transcript_path = transcript_file
                                output_dir = transcript_file.parent  # Update output_dir to match found location
                                st.session_state.output_dir = output_dir
                                transcript_cached = True
                                st.info(f"ℹ️ Found cached transcript (folder name may have changed): {transcript_path}")
                                break
                    except (json.JSONDecodeError, IOError):
                        continue
            
            # Debug: Show cache status and path
            if transcript_cached:
                if not st.session_state.get('_cache_found_shown'):
                    st.info(f"ℹ️ Found cached transcript at: {transcript_path}")
                    st.session_state['_cache_found_shown'] = True
            else:
                if not transcript_path.exists():
                    st.info(f"ℹ️ No cached transcript found at: {transcript_path}")
            
            if transcript_cached:
                # Load cached transcript (NO API CALL - saves money!)
                try:
                    st.info("ℹ️ Using cached transcript - loading from previous run (no API call)")
                    with open(transcript_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    segments = [
                        Segment(start=s['start'], end=s['end'], text=s['text'])
                        for s in data.get('segments', [])
                    ]
                    
                    transcript = Transcript(
                        video_id=data.get('video_id', video_id),
                        url=data.get('url', url),
                        title=data.get('title'),
                        channel=data.get('channel'),
                        duration=data.get('duration'),
                        language=data.get('language'),
                        segments=segments
                    )
                    st.session_state.transcript = transcript
                    st.success("✓ Cached transcript loaded (no cost)")
                except Exception as e:
                    st.warning(f"⚠️ Failed to load cached transcript: {e}. Will re-transcribe.")
                    # Fall through to transcribe if cache load fails
                    transcript_cached = False
            
            if not transcript_cached:
                # Transcribe (not cached or cache load failed)
                # transcribe_audio() also checks for cache internally, so it won't re-transcribe if cached
                # Use progress bar wrapper for better user feedback
                transcript = transcribe_with_progress(audio_path, video_id, url, metadata, force=False)
                st.session_state.transcript = transcript
                st.success("✓ Transcript ready")
            
            # Write transcript files
            with st.spinner("Saving transcript files..."):
                write_json(transcript, output_dir / "transcript.json")
                write_txt(transcript, output_dir / "transcript_with_timestamps.txt")
                write_srt(transcript, output_dir / "transcript.srt")
            
            # Analyze transcript if requested
            if analyze:
                analysis_path = output_dir / "equity_analysis.txt"
                if analysis_path.exists():
                    st.info("ℹ️ Using cached analysis - loading from previous run")
                    with open(analysis_path, 'r', encoding='utf-8') as f:
                        analysis_text = f.read()
                    st.session_state.analysis_text = analysis_text
                    st.success("✓ Analysis loaded from cache!")
                else:
                    with st.spinner("Analyzing transcript with GPT (this may take a minute)..."):
                        try:
                            analysis_text = analyze_transcript(transcript, output_dir, force=False)
                            write_analysis(analysis_text, output_dir / "equity_analysis.txt")
                            st.session_state.analysis_text = analysis_text
                            st.success("✓ Analysis complete!")
                        except Exception as e:
                            st.error(f"⚠ Error analyzing transcript: {str(e)}")
            
            # Check for cached formatted transcript
            formatted_path = output_dir / "formatted_transcript.txt"
            if formatted_path.exists():
                with open(formatted_path, 'r', encoding='utf-8') as f:
                    st.session_state.formatted_transcript = f.read()
            else:
                st.session_state.formatted_transcript = None
            
            return True, output_dir
            
        finally:
            # Restore original output directory
            Config.OUT_DIR = original_out_dir
            
    except Exception as e:
        st.error(f"✗ Error processing video: {str(e)}")
        return False, None


def main():
    """Main Streamlit application."""
    
    # Header
    st.markdown('<div class="main-header">🎥 YouTube Video Transcriber</div>', unsafe_allow_html=True)
    
    # Sidebar for settings
    with st.sidebar:
        st.header("⚙️ Settings")
        st.info("This app uses the server's OpenAI API key. No API key needed from you!")
        
        # Show current status
        st.subheader("📊 Current Status")
        if st.session_state.transcript:
            if hasattr(st.session_state.transcript, 'title') and st.session_state.transcript.title:
                st.caption(f"**Video:** {st.session_state.transcript.title}")
            st.success(f"✓ Transcript ready ({len(st.session_state.transcript.segments)} segments)")
            if st.session_state.analysis_text:
                st.success("✓ Analysis ready")
            else:
                st.info("ℹ️ No analysis yet")
        else:
            st.info("No video processed yet")
        
        st.divider()
        
        st.subheader("Options")
        analyze = st.checkbox("Run equity analysis", value=True)
        
        # Prior Transcript History
        st.divider()
        st.subheader("📚 Prior Transcripts")
        if st.session_state.transcript_history:
            for i, (video_id, title, url, transcript_path) in enumerate(st.session_state.transcript_history[:10]):  # Show last 10
                # Check if this is the current transcript
                is_current = (st.session_state.transcript and 
                            hasattr(st.session_state.transcript, 'video_id') and 
                            st.session_state.transcript.video_id == video_id)
                
                if is_current:
                    st.markdown(f"**{title}** (Current)")
                else:
                    # Button to load this transcript
                    if st.button(f"📹 {title[:50]}..." if len(title) > 50 else f"📹 {title}", 
                               key=f"load_transcript_{i}", use_container_width=True):
                        # Load transcript from file
                        try:
                            transcript_path_obj = Path(transcript_path)
                            if transcript_path_obj.exists():
                                with open(transcript_path_obj, 'r', encoding='utf-8') as f:
                                    data = json.load(f)
                                
                                segments = [
                                    Segment(start=s['start'], end=s['end'], text=s['text'])
                                    for s in data.get('segments', [])
                                ]
                                
                                transcript = Transcript(
                                    video_id=data.get('video_id', video_id),
                                    url=data.get('url', url),
                                    title=data.get('title', title),
                                    channel=data.get('channel'),
                                    duration=data.get('duration'),
                                    language=data.get('language'),
                                    segments=segments
                                )
                                
                                st.session_state.transcript = transcript
                                st.session_state.current_video_url = url
                                
                                # Try to load analysis if it exists
                                analysis_path = transcript_path_obj.parent / "equity_analysis.txt"
                                if analysis_path.exists():
                                    with open(analysis_path, 'r', encoding='utf-8') as f:
                                        st.session_state.analysis_text = f.read()
                                else:
                                    st.session_state.analysis_text = None
                                
                                # Try to load formatted transcript if it exists
                                formatted_path = transcript_path_obj.parent / "formatted_transcript.txt"
                                if formatted_path.exists():
                                    with open(formatted_path, 'r', encoding='utf-8') as f:
                                        st.session_state.formatted_transcript = f.read()
                                else:
                                    st.session_state.formatted_transcript = None
                                
                                # Set output dir
                                st.session_state.output_dir = transcript_path_obj.parent
                                
                                # Clear chat messages when switching transcripts
                                st.session_state.chat_messages = []
                                
                                st.rerun()
                        except Exception as e:
                            st.error(f"Error loading transcript: {e}")
        else:
            st.caption("No prior transcripts yet")
    
    # Main content area
    tab1, tab2, tab3, tab4 = st.tabs(["📥 Transcribe", "📝 Transcript", "💬 Chat", "📊 Analysis"])
    
    # Tab 1: Transcription
    with tab1:
        st.header("Transcribe YouTube Video")
        
        url = st.text_input(
            "YouTube Video URL",
            placeholder="https://www.youtube.com/watch?v=...",
            help="Paste the full YouTube video URL here"
        )
        
        col1, col2 = st.columns([1, 4])
        with col1:
            process_button = st.button("🚀 Process Video", type="primary", use_container_width=True)
        
        if process_button:
            if not url:
                st.error("Please enter a YouTube URL")
            else:
                # Show immediate feedback
                status_container = st.container()
                with status_container:
                    st.info("🔄 Starting video processing... Please wait.")
                
                st.session_state.processing = True
                try:
                    success, output_dir = process_video_streamlit(url, analyze)
                    st.session_state.processing = False
                    
                    if success:
                        st.success("✅ Video processed successfully!")
                        
                        # Store current video URL
                        st.session_state.current_video_url = url
                        
                        # Add to transcript history if not already there
                        if st.session_state.transcript:
                            video_id = st.session_state.transcript.video_id
                            title = getattr(st.session_state.transcript, 'title', 'Unknown')
                            url_for_history = st.session_state.transcript.url or url
                            
                            # Check if already in history
                            if not any(h[0] == video_id for h in st.session_state.transcript_history):
                                st.session_state.transcript_history.insert(0, (video_id, title, url_for_history, str(output_dir / "transcript.json")))
                            
                            # Check if already in history
                            if not any(h[0] == video_id for h in st.session_state.transcript_history):
                                st.session_state.transcript_history.insert(0, (video_id, title, url_for_history, str(output_dir / "transcript.json")))
                except Exception as e:
                    st.session_state.processing = False
                    st.error(f"❌ Error: {str(e)}")
                    st.exception(e)  # Show full error traceback for debugging
        
        # Show current transcript if available (even when navigating back)
        if st.session_state.transcript:
            st.divider()
            st.subheader("📝 Current Transcript")
            if hasattr(st.session_state.transcript, 'title') and st.session_state.transcript.title:
                st.caption(f"**Video:** {st.session_state.transcript.title}")
            if hasattr(st.session_state.transcript, 'channel') and st.session_state.transcript.channel:
                st.caption(f"**Channel:** {st.session_state.transcript.channel}")
            
            # Show download options
            if st.session_state.output_dir and (st.session_state.output_dir / "transcript_with_timestamps.txt").exists():
                st.subheader("📥 Download Files")
                # Use tighter columns to bring buttons closer
                col1, col2, col3 = st.columns([1, 1, 4])
                
                with col1:
                    with open(st.session_state.output_dir / "transcript_with_timestamps.txt", "r", encoding="utf-8") as f:
                        st.download_button(
                            "📄 Download TXT",
                            f.read(),
                            file_name="transcript.txt",
                            mime="text/plain",
                            key="download_txt_current"
                        )
                
                if st.session_state.analysis_text:
                    with col2:
                        st.download_button(
                            "📊 Download Analysis",
                            st.session_state.analysis_text,
                            file_name="equity_analysis.txt",
                            mime="text/plain",
                            key="download_analysis_current"
                        )
            

    
    # Tab 2: Full Transcript
    with tab2:
        st.header("📝 Full Transcript")
        
        if st.session_state.transcript is None:
            st.info("👆 First transcribe a video in the 'Transcribe' tab to view the full transcript.")
        else:
            # Show video info
            if hasattr(st.session_state.transcript, 'title') and st.session_state.transcript.title:
                st.subheader(st.session_state.transcript.title)
            if hasattr(st.session_state.transcript, 'channel') and st.session_state.transcript.channel:
                st.caption(f"Channel: {st.session_state.transcript.channel}")
            if hasattr(st.session_state.transcript, 'duration') and st.session_state.transcript.duration:
                minutes = int(st.session_state.transcript.duration // 60)
                seconds = int(st.session_state.transcript.duration % 60)
                st.caption(f"Duration: {minutes}:{seconds:02d}")
            
            st.divider()
            
            # Format Transcript Button
            col1, col2 = st.columns([1, 3])
            with col1:
                if st.button("✨ Format Transcript (Paragraphs)", use_container_width=True, help="Reformat transcript into paragraphs with speaker labels (uses GPT)"):
                    with st.spinner("Formatting transcript..."):
                        try:
                            formatted_text = format_transcript(st.session_state.transcript, st.session_state.output_dir)
                            st.session_state.formatted_transcript = formatted_text
                            st.success("✓ Transcript formatted!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Error formatting transcript: {e}")
            
            st.divider()
            
            # Display formatted transcript if available, otherwise raw segments
            if st.session_state.formatted_transcript:
                st.info("✓ Viewing formatted transcript")
                # Escape dollar signs to prevent Streamlit from interpreting them as LaTeX
                safe_text = st.session_state.formatted_transcript.replace("$", "\\$")
                st.markdown(f'<div class="transcript-text">{safe_text}</div>', unsafe_allow_html=True)
            else:
                # Display full transcript with better formatting
                transcript_text = "\n\n".join(
                    f"[{int(seg.start // 60):02d}:{int(seg.start % 60):02d}] {seg.text}"
                    for seg in st.session_state.transcript.segments
                )
                
                st.markdown(f'<div class="transcript-text">{transcript_text}</div>', unsafe_allow_html=True)
    
    # Tab 3: Chat
    with tab3:
        st.header("💬 Ask Questions About the Transcript")
        
        # Check for transcript in session state
        if st.session_state.transcript is None:
            st.info("👆 First transcribe a video in the 'Transcribe' tab to start asking questions.")
        else:
            # Show video info if available
            if hasattr(st.session_state.transcript, 'title') and st.session_state.transcript.title:
                st.caption(f"📹 {st.session_state.transcript.title}")
            st.success("✓ Video loaded")
            
            # Display chat history
            if st.session_state.chat_messages:
                st.subheader("💭 Conversation History")
                for i, (role, content) in enumerate(st.session_state.chat_messages):
                    with st.chat_message(role):
                        # Fix number formatting to prevent breaking
                        fixed_content = fix_number_formatting(content)
                        st.markdown(fixed_content, unsafe_allow_html=True)
            
            # Chat input
            user_question = st.chat_input("Ask your video for a recap, or any other question!")
            
            if user_question:
                # Add user message to history
                st.session_state.chat_messages.append(("user", user_question))
                
                # Get AI response
                with st.spinner("Thinking..."):
                    try:
                        # Initialize OpenAI client
                        from openai import OpenAI
                        client = OpenAI(api_key=Config.OPENAI_API_KEY, timeout=300.0)
                        
                        # Get transcript text
                        from yt2txt.analyzer import get_transcript_text
                        transcript_text = get_transcript_text(st.session_state.transcript)
                        
                        # Build messages
                        messages = [
                            {
                                "role": "system",
                                "content": "You are an expert equity analyst analyzing a CEO interview transcript. Answer questions based on the transcript content. If the transcript doesn't contain the information, say so. Never guess or make up information."
                            },
                            {
                                "role": "user",
                                "content": f"Here is the transcript from a CEO interview:\n\n{transcript_text}"
                            }
                        ]
                        
                        # Add conversation history
                        for role, content in st.session_state.chat_messages:
                            messages.append({"role": role, "content": content})
                        
                        # Get response
                        analysis_model = Config.ANALYSIS_MODEL
                        request_params = {
                            "model": analysis_model,
                            "messages": messages
                        }
                        
                        if not analysis_model.startswith("gpt-5"):
                            request_params["temperature"] = 0.3
                        
                        response = client.chat.completions.create(**request_params)
                        ai_response = response.choices[0].message.content
                        
                        # Add AI response to history
                        st.session_state.chat_messages.append(("assistant", ai_response))
                        
                        # Rerun to show new messages
                        st.rerun()
                        
                    except Exception as e:
                        st.error(f"Error getting response: {str(e)}")
                        # Remove the user message if there was an error
                        if st.session_state.chat_messages and st.session_state.chat_messages[-1][0] == "user":
                            st.session_state.chat_messages.pop()
            
            # Clear chat button
            if st.session_state.chat_messages:
                if st.button("🗑️ Clear Conversation"):
                    st.session_state.chat_messages = []
                    st.rerun()
    
    # Tab 4: Analysis
    with tab4:
        st.header("📊 Equity Analysis")
        
        # Check if transcript is available
        if st.session_state.transcript is None:
            st.info("👆 First transcribe a video in the 'Transcribe' tab to run equity analysis.")
        else:
            # Show video info if available
            if hasattr(st.session_state.transcript, 'title') and st.session_state.transcript.title:
                st.caption(f"📹 {st.session_state.transcript.title}")
            
            # Check if analysis already exists
            if st.session_state.analysis_text:
                # Display existing analysis
                st.markdown(f'<div class="analysis-text">{st.session_state.analysis_text}</div>', unsafe_allow_html=True)
            else:
                # Prompt user to run analysis
                st.info("Would you like to run a stock-specific analysis prompt?")
                st.caption("This will use GPT to analyze the transcript from an equity research perspective.")
                
                if st.button("📊 Run Equity Analysis", type="primary", use_container_width=False):
                    # Check if cached analysis exists
                    if st.session_state.output_dir:
                        analysis_path = st.session_state.output_dir / "equity_analysis.txt"
                        if analysis_path.exists():
                            # Load cached analysis
                            with st.spinner("Loading cached analysis..."):
                                with open(analysis_path, 'r', encoding='utf-8') as f:
                                    st.session_state.analysis_text = f.read()
                                st.success("✓ Analysis loaded from cache!")
                                st.rerun()
                        else:
                            # Run new analysis
                            with st.spinner("Analyzing transcript with GPT (this may take a minute)..."):
                                try:
                                    from yt2txt.analyzer import analyze_transcript
                                    from yt2txt.writers.analysis_writer import write_analysis
                                    
                                    analysis_text = analyze_transcript(st.session_state.transcript, st.session_state.output_dir, force=False)
                                    write_analysis(analysis_text, analysis_path)
                                    st.session_state.analysis_text = analysis_text
                                    st.success("✓ Analysis complete!")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"⚠ Error analyzing transcript: {str(e)}")
                    else:
                        st.error("Output directory not found. Please re-process the video.")


if __name__ == "__main__":
    main()

