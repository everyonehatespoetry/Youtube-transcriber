@echo off
REM Double-click launcher for YouTube Video Transcriber (Streamlit UI)

cd /d "%~dp0"
echo Starting Streamlit app...
echo.
echo IMPORTANT: When prompted for email, just press Enter to skip.
echo.
echo The app will open in your browser automatically once the server starts.
echo If it doesn't, manually go to: http://localhost:8501
echo.
echo Press Ctrl+C in this window to stop the server.
echo.

REM Run Streamlit (this will show output in this window)
REM Streamlit will automatically open browser when ready
streamlit run streamlit_app.py

if errorlevel 1 (
    echo.
    echo An error occurred. Press any key to exit...
    pause >nul
)

