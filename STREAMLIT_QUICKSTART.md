# Streamlit Web App - Quick Start Guide

## What Was Created

✅ **`streamlit_app.py`** - Main Streamlit web application
✅ **`.streamlit/config.toml`** - Streamlit configuration
✅ **`DEPLOYMENT.md`** - Full deployment instructions
✅ **Updated `requirements.txt`** - Added Streamlit dependency

## Features

The web app includes:
- 🎥 **Transcription Tab**: Upload YouTube URL, transcribe, download files
- 💬 **Chat Tab**: Ask questions about the transcript interactively
- 📊 **Analysis Tab**: View the equity analysis results
- 📥 **File Downloads**: Download transcripts in TXT, JSON, SRT formats

## Local Testing (Before Deployment)

1. Install Streamlit:
   ```bash
   pip install streamlit
   ```

2. Make sure your `.env` file has your API key:
   ```
   OPENAI_API_KEY=sk-your-key-here
   ```

3. Run locally:
   ```bash
   streamlit run streamlit_app.py
   ```

4. Open your browser to `http://localhost:8501`

## Deploy to Streamlit Cloud

1. **Push to GitHub** (if not already):
   ```bash
   git add .
   git commit -m "Add Streamlit web app"
   git push
   ```

2. **Go to Streamlit Cloud**: https://share.streamlit.io/

3. **Click "New app"** and connect your GitHub repo

4. **Set main file**: `streamlit_app.py`

5. **Add secrets** (in app settings → Secrets):
   ```
   OPENAI_API_KEY=sk-your-key-here
   MODEL=whisper-1
   ANALYSIS_MODEL=gpt-4o-mini
   OUT_DIR=./out
   MAX_RETRIES=2
   ```

6. **Deploy!** Your app will be live at `https://YOUR_APP_NAME.streamlit.app`

## Key Points

- ✅ **API key is secure**: Stored in Streamlit Cloud secrets, never exposed to users
- ✅ **Free hosting**: Streamlit Cloud free tier is sufficient
- ✅ **No user setup**: Friends just visit the URL and use it
- ✅ **You pay for API usage**: Same costs as running locally

## Troubleshooting

- **Import errors**: Make sure all files are in the repo
- **API errors**: Check secrets are set correctly
- **Slow performance**: Large videos take time to process (normal)

