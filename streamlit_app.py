"""Streamlit web application for YouTube video transcription and analysis."""

import streamlit as st
import sys
import os
from pathlib import Path
import tempfile
import shutil

# Add the project root to the path so we can import yt2txt modules
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load .env file from project root (for local development)
from dotenv import load_dotenv
env_path = project_root / '.env'
if env_path.exists():
    load_dotenv(env_path, override=False)
else:
    # Try loading from current directory
    load_dotenv(override=False)

from yt2txt.config import Config
from yt2txt.downloader import download_audio
from yt2txt.video_downloader import download_video
from yt2txt.transcriber import transcribe_audio
from yt2txt.analyzer import analyze_transcript
from yt2txt.writers.txt_writer import write_txt
from yt2txt.writers.json_writer import write_json
from yt2txt.writers.srt_writer import write_srt
from yt2txt.writers.analysis_writer import write_analysis
from yt2txt.models import Transcript


# Page configuration
st.set_page_config(
    page_title="YouTube Video Transcriber",
    page_icon="🎥",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Load API key from Streamlit secrets (for cloud deployment) - AFTER page config
# Streamlit secrets take precedence over .env file
try:
    if hasattr(st, 'secrets') and st.secrets:
        if 'OPENAI_API_KEY' in st.secrets:
            os.environ['OPENAI_API_KEY'] = st.secrets['OPENAI_API_KEY']
        if 'MODEL' in st.secrets:
            os.environ['MODEL'] = st.secrets['MODEL']
        if 'ANALYSIS_MODEL' in st.secrets:
            os.environ['ANALYSIS_MODEL'] = st.secrets['ANALYSIS_MODEL']
        if 'OUT_DIR' in st.secrets:
            os.environ['OUT_DIR'] = st.secrets['OUT_DIR']
        if 'MAX_RETRIES' in st.secrets:
            os.environ['MAX_RETRIES'] = str(st.secrets['MAX_RETRIES'])
        # Reload Config after setting environment variables
        Config._reload_from_env()
except (AttributeError, TypeError, KeyError):
    # st.secrets not available or key not found - will use .env file
    pass

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


def process_video_streamlit(url: str, extract_slides: bool, analyze: bool):
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
                audio_path, metadata, video_id = download_audio(url, force=False)
                output_dir = audio_path.parent
                st.session_state.output_dir = output_dir
            
            # Transcribe
            with st.spinner("Transcribing audio (this may take a few minutes for long videos)..."):
                transcript = transcribe_audio(audio_path, video_id, url, metadata, force=False)
                st.session_state.transcript = transcript
            
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
                with st.spinner("Analyzing transcript with GPT (this may take a minute)..."):
                    try:
                        analysis_text = analyze_transcript(transcript, output_dir, force=False)
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
        
        st.subheader("Options")
        extract_slides = st.checkbox("Extract slides from video", value=False)
        analyze = st.checkbox("Run equity analysis", value=True)
    
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
                
                st.session_state.processing = True
                try:
                    success, output_dir = process_video_streamlit(url, extract_slides, analyze)
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
        
        if not st.session_state.transcript:
            st.info("👆 First transcribe a video in the 'Transcribe' tab to start asking questions.")
        else:
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
        
        if not st.session_state.analysis_text:
            st.info("👆 Run equity analysis in the 'Transcribe' tab to see the analysis here.")
        else:
            st.text_area(
                "Analysis Results",
                st.session_state.analysis_text,
                height=600,
                disabled=True
            )


if __name__ == "__main__":
    main()

