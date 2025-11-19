"""Streamlit web application for YouTube video transcription and analysis."""

import streamlit as st
import sys
import os
from pathlib import Path
import tempfile
import shutil

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
from yt2txt.models import Transcript, Segment
import json


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
    </style>
""", unsafe_allow_html=True)

# Initialize session state
if 'transcript' not in st.session_state:
    st.session_state.transcript = None
if 'analysis_text' not in st.session_state:
    st.session_state.analysis_text = None
if 'output_dir' not in st.session_state:
    st.session_state.output_dir = None
if 'chat_messages' not in st.session_state:
    st.session_state.chat_messages = []
if 'processing' not in st.session_state:
    st.session_state.processing = False


def process_video_streamlit(url: str, extract_slides: bool, analyze: bool, force: bool = False):
    """Process video with Streamlit progress indicators."""
    try:
        # Validate configuration first
        with st.spinner("Validating configuration..."):
            Config.validate()
            st.success("✓ Configuration validated")
        
        # Create temporary output directory
        temp_dir = Path(tempfile.mkdtemp())
        original_out_dir = Config.OUT_DIR
        Config.OUT_DIR = temp_dir
        
        try:
            # Download audio
            with st.spinner("Downloading audio from YouTube..."):
                audio_path, metadata, video_id = download_audio(url, force=force)
                output_dir = audio_path.parent
                st.session_state.output_dir = output_dir
                
                # Check if using cached audio
                audio_cached = audio_path.exists() and not force
                if audio_cached:
                    st.info("ℹ️ Using cached audio file - video was previously downloaded")
            
            # Check if transcript is already cached before transcribing
            transcript_path = output_dir / "transcript.json"
            transcript_cached = transcript_path.exists() and not force
            
            if transcript_cached:
                # Load cached transcript
                st.info("ℹ️ Using cached transcript - loading from previous run")
                with open(transcript_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                from yt2txt.models import Segment
                segments = [
                    Segment(start=s['start'], end=s['end'], text=s['text'])
                    for s in data.get('segments', [])
                ]
                
                from yt2txt.models import Transcript
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
                st.success("✓ Cached transcript loaded")
            else:
                # Transcribe (not cached)
                with st.spinner("Transcribing audio (this may take a few minutes for long videos)..."):
                    transcript = transcribe_audio(audio_path, video_id, url, metadata, force=force)
                    st.session_state.transcript = transcript
                    st.success("✓ New transcript created")
            
            # Write transcript files
            with st.spinner("Saving transcript files..."):
                write_json(transcript, output_dir / "transcript.json")
                write_txt(transcript, output_dir / "transcript_with_timestamps.txt")
                write_srt(transcript, output_dir / "transcript.srt")
            
            # Extract slides if requested
            if extract_slides:
                with st.spinner("Extracting slides from video..."):
                    try:
                        # Import SlideExtractor only when needed (avoids cv2 import issues on Streamlit Cloud)
                        try:
                            from yt2txt.slide_extractor import SlideExtractor
                        except ImportError as e:
                            st.error(f"Slide extraction is not available: {str(e)}. This feature requires OpenCV which may not be available on this platform.")
                            return True, output_dir
                        
                        video_path, _, _ = download_video(url, force=False)
                        extractor = SlideExtractor()
                        slides = extractor.process_video(video_path, output_dir, interval_seconds=1.0)
                        
                        if slides:
                            import json
                            slides_manifest = [
                                {
                                    'timestamp': timestamp,
                                    'image_path': str(slide_path.relative_to(output_dir)),
                                    'time_formatted': f"{int(timestamp // 60):02d}:{int(timestamp % 60):02d}"
                                }
                                for timestamp, slide_path in slides
                            ]
                            manifest_path = output_dir / "slides_manifest.json"
                            with open(manifest_path, 'w', encoding='utf-8') as f:
                                json.dump(slides_manifest, f, indent=2)
                            st.success(f"✓ Extracted {len(slides)} slides")
                        else:
                            st.warning("⚠ No slides found in video")
                    except Exception as e:
                        st.error(f"⚠ Error extracting slides: {str(e)}")
            
            # Analyze transcript if requested
            if analyze:
                analysis_path = output_dir / "equity_analysis.txt"
                if analysis_path.exists() and not force:
                    st.info("ℹ️ Using cached analysis - loading from previous run")
                    with open(analysis_path, 'r', encoding='utf-8') as f:
                        analysis_text = f.read()
                    st.session_state.analysis_text = analysis_text
                    st.success("✓ Analysis loaded from cache!")
                else:
                    with st.spinner("Analyzing transcript with GPT (this may take a minute)..."):
                        try:
                            analysis_text = analyze_transcript(transcript, output_dir, force=force)
                            write_analysis(analysis_text, output_dir / "equity_analysis.txt")
                            st.session_state.analysis_text = analysis_text
                            st.success("✓ Analysis complete!")
                        except Exception as e:
                            st.error(f"⚠ Error analyzing transcript: {str(e)}")
            
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
        extract_slides = st.checkbox("Extract slides from video", value=False)
        analyze = st.checkbox("Run equity analysis", value=True)
        
        # Add force reprocess option
        st.divider()
        force_reprocess = st.checkbox("🔄 Force reprocess (ignore cache)", value=False, help="Check this to re-download and re-transcribe even if already processed")
    
    # Main content area
    tab1, tab2, tab3 = st.tabs(["📥 Transcribe", "💬 Chat", "📊 Analysis"])
    
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
                    if force_reprocess:
                        st.warning("⚠️ Force reprocess enabled - will re-download and re-transcribe")
                
                st.session_state.processing = True
                try:
                    success, output_dir = process_video_streamlit(url, extract_slides, analyze, force_reprocess)
                    st.session_state.processing = False
                    
                    if success:
                        st.success("✅ Video processed successfully!")
                        
                        # Show download options
                        st.subheader("📥 Download Files")
                        
                        col1, col2, col3, col4 = st.columns(4)
                        
                        with col1:
                            with open(output_dir / "transcript_with_timestamps.txt", "r", encoding="utf-8") as f:
                                st.download_button(
                                    "📄 Download TXT",
                                    f.read(),
                                    file_name="transcript.txt",
                                    mime="text/plain"
                                )
                        
                        with col2:
                            with open(output_dir / "transcript.json", "r", encoding="utf-8") as f:
                                st.download_button(
                                    "📋 Download JSON",
                                    f.read(),
                                    file_name="transcript.json",
                                    mime="application/json"
                                )
                        
                        with col3:
                            with open(output_dir / "transcript.srt", "r", encoding="utf-8") as f:
                                st.download_button(
                                    "🎬 Download SRT",
                                    f.read(),
                                    file_name="transcript.srt",
                                    mime="text/plain"
                                )
                        
                        if st.session_state.analysis_text:
                            with col4:
                                st.download_button(
                                    "📊 Download Analysis",
                                    st.session_state.analysis_text,
                                    file_name="equity_analysis.txt",
                                    mime="text/plain"
                                )
                        
                        # Show transcript preview
                        if st.session_state.transcript:
                            st.subheader("📝 Transcript Preview")
                            transcript_text = "\n".join(
                                f"[{int(seg.start // 60):02d}:{int(seg.start % 60):02d}] {seg.text}"
                                for seg in st.session_state.transcript.segments[:20]
                            )
                            if len(st.session_state.transcript.segments) > 20:
                                transcript_text += f"\n\n... and {len(st.session_state.transcript.segments) - 20} more segments"
                            st.text_area("", transcript_text, height=300, disabled=True)
                except Exception as e:
                    st.session_state.processing = False
                    st.error(f"❌ Error: {str(e)}")
                    st.exception(e)  # Show full error traceback for debugging
    
    # Tab 2: Chat
    with tab2:
        st.header("💬 Ask Questions About the Transcript")
        
        # Check for transcript in session state
        if st.session_state.transcript is None:
            st.info("👆 First transcribe a video in the 'Transcribe' tab to start asking questions.")
        else:
            # Show video info if available
            if hasattr(st.session_state.transcript, 'title') and st.session_state.transcript.title:
                st.caption(f"📹 {st.session_state.transcript.title}")
            st.success(f"✓ Transcript loaded ({len(st.session_state.transcript.segments)} segments)")
            
            # Display chat history
            if st.session_state.chat_messages:
                st.subheader("💭 Conversation History")
                for i, (role, content) in enumerate(st.session_state.chat_messages):
                    with st.chat_message(role):
                        st.write(content)
            
            # Chat input
            user_question = st.chat_input("Ask a question about the transcript...")
            
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
    
    # Tab 3: Analysis
    with tab3:
        st.header("📊 Equity Analysis")
        
        # Check for analysis in session state
        if st.session_state.analysis_text is None or st.session_state.analysis_text == "":
            st.info("👆 Run equity analysis in the 'Transcribe' tab (check 'Run equity analysis' option) to see the analysis here.")
        else:
            # Show video info if available
            if st.session_state.transcript and hasattr(st.session_state.transcript, 'title') and st.session_state.transcript.title:
                st.caption(f"📹 {st.session_state.transcript.title}")
            st.text_area(
                "Analysis Results",
                st.session_state.analysis_text,
                height=600,
                disabled=True
            )


if __name__ == "__main__":
    main()

