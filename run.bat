@echo off
REM Double-click launcher for YouTube Video Transcriber

cd /d "%~dp0"
python -m yt2txt.main

if errorlevel 1 (
    echo.
    echo An error occurred. Press any key to exit...
    pause >nul
)

