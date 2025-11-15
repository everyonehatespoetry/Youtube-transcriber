# Deployment Guide for Streamlit Cloud

This guide will help you deploy the YouTube Video Transcriber to Streamlit Cloud.

## Prerequisites

1. A GitHub account
2. Your OpenAI API key
3. A Streamlit Cloud account (free at https://streamlit.io/cloud)

## Step 1: Push to GitHub

1. Create a new repository on GitHub (or use an existing one)
2. Push your code to GitHub:
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO.git
   git push -u origin main
   ```

## Step 2: Deploy to Streamlit Cloud

1. Go to https://share.streamlit.io/
2. Click "New app"
3. Connect your GitHub account if not already connected
4. Select your repository
5. Set the main file path to: `streamlit_app.py`
6. Click "Deploy"

## Step 3: Configure API Key

1. In your Streamlit Cloud app settings, go to "Secrets"
2. Add your OpenAI API key:
   ```
   OPENAI_API_KEY=sk-your-api-key-here
   MODEL=whisper-1
   ANALYSIS_MODEL=gpt-4o-mini
   OUT_DIR=./out
   MAX_RETRIES=2
   ```

## Step 4: Deploy

1. Click "Save" in the secrets section
2. Your app will automatically redeploy
3. Access your app at: `https://YOUR_APP_NAME.streamlit.app`

## Important Notes

- **API Key Security**: Your API key is stored securely in Streamlit Cloud secrets and is never exposed to users
- **Costs**: You'll pay for OpenAI API usage based on how much the app is used
- **Rate Limits**: Be aware of OpenAI rate limits if multiple users use the app simultaneously
- **File Storage**: Temporary files are created during processing but cleaned up automatically

## Customization

You can customize the app by:
- Editing `streamlit_app.py` to change the UI
- Modifying `.streamlit/config.toml` for theme customization
- Updating the analysis prompt in `yt2txt/analyzer.py`

## Troubleshooting

- **Import errors**: Make sure all dependencies are in `requirements.txt`
- **API errors**: Check that your OpenAI API key is correct and has credits
- **Deployment fails**: Check the logs in Streamlit Cloud dashboard

