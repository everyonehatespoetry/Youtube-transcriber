"""Minimal test version to diagnose startup issues."""

import streamlit as st
import sys
import os
from pathlib import Path

st.set_page_config(
    page_title="YouTube Video Transcriber - Test",
    page_icon="🎥",
    layout="wide"
)

st.title("🔍 Diagnostic Test")

# Test 1: Basic Streamlit
st.success("✓ Streamlit is working")

# Test 2: Check project structure
project_root = Path(__file__).parent
st.write(f"Project root: {project_root}")

# Test 3: Try loading .env
try:
    from dotenv import load_dotenv
    env_path = project_root / '.env'
    if env_path.exists():
        load_dotenv(env_path, override=False)
        st.success(f"✓ .env file found at {env_path}")
    else:
        st.warning(f"⚠️ .env file not found at {env_path}")
except Exception as e:
    st.error(f"✗ Error loading dotenv: {e}")

# Test 4: Check secrets
try:
    if hasattr(st, 'secrets') and st.secrets:
        if 'OPENAI_API_KEY' in st.secrets:
            st.success("✓ OPENAI_API_KEY found in Streamlit secrets")
        else:
            st.warning("⚠️ OPENAI_API_KEY not in Streamlit secrets")
    else:
        st.info("ℹ️ Streamlit secrets not available")
except Exception as e:
    st.error(f"✗ Error accessing secrets: {e}")

# Test 5: Try importing config
try:
    sys.path.insert(0, str(project_root))
    from yt2txt.config import Config
    st.success("✓ Config imported successfully")
    
    # Test accessing config
    try:
        api_key = Config.OPENAI_API_KEY
        if api_key:
            st.success(f"✓ API key loaded (length: {len(api_key)})")
        else:
            st.warning("⚠️ API key is empty")
    except Exception as e:
        st.error(f"✗ Error accessing Config.OPENAI_API_KEY: {e}")
        
except Exception as e:
    st.error(f"✗ Error importing Config: {e}")
    import traceback
    st.code(traceback.format_exc())

# Test 6: Try importing other modules
modules_to_test = [
    'yt2txt.downloader',
    'yt2txt.transcriber',
    'yt2txt.analyzer',
]

for module_name in modules_to_test:
    try:
        __import__(module_name)
        st.success(f"✓ {module_name} imported")
    except Exception as e:
        st.error(f"✗ {module_name} failed: {e}")
        import traceback
        st.code(traceback.format_exc())

st.info("If you see all checkmarks, the main app should work. If any fail, that's the issue.")

