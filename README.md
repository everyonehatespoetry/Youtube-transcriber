# YouTube Video Transcriber

A simple, reliable tool to transcribe YouTube videos using OpenAI's Whisper API. Downloads audio directly (no ffmpeg required) and outputs transcripts in multiple formats.

## Features

- 🎥 Downloads audio from YouTube videos (m4a format, no ffmpeg needed)
- 🤖 Transcribes using OpenAI Whisper API
- 📝 Outputs transcripts in TXT, JSON, and SRT formats
- 💾 Caching: Reuses downloaded audio and transcripts (unless `--force` is used)
- 🔄 Automatic retries for network errors
- 🪟 Windows ARM64 compatible
- 🖱️ Interactive UI: Double-click to run, paste URL, get results

## Requirements

- Python 3.11 or newer
- OpenAI API key
- Internet connection

## Installation

1. **Clone or download this repository**

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up your OpenAI API key:**
   
   Create a `.env` file in the project root:
   ```
   OPENAI_API_KEY=sk-your-api-key-here
   OUT_DIR=./out
   MODEL=whisper-1
   MAX_RETRIES=2
   ```
   
   You can copy `.env.example` as a template (if it exists).

## Usage

### Interactive Mode (Recommended)

**Double-click `run.bat`** (Windows) or run:
```bash
python -m yt2txt.main
```

The program will:
1. Ask you to paste a YouTube URL
2. Download the audio
3. Transcribe using OpenAI Whisper API
4. Save all files to the output directory
5. Show you the path where files were saved
6. Ask if you want to transcribe another video

### Command Line Mode

You can also run it directly:
```bash
python -m yt2txt.main
```

## Output Files

For each video, the following files are saved in `out/<video-id>-<video-title>/`:

- **`audio.m4a`** - The downloaded audio file
- **`meta.json`** - Video metadata (title, channel, duration, etc.)
- **`transcript.json`** - Full transcript with segments in JSON format
- **`transcript_with_timestamps.txt`** - Human-readable transcript with timestamps
  - Format: `[HH:MM:SS - HH:MM:SS] text`
- **`transcript.srt`** - Subtitle file in SRT format

### Example TXT Output

```
[00:00:00 - 00:00:05] Hello and welcome to this video.
[00:00:05 - 00:00:12] Today we're going to discuss...
[00:00:12 - 00:00:20] First, let's talk about...
```

### Example JSON Output

```json
{
  "video_id": "abc123",
  "url": "https://www.youtube.com/watch?v=abc123",
  "title": "My Video Title",
  "channel": "Channel Name",
  "duration": 300,
  "language": "en",
  "segments": [
    {
      "start": 0.0,
      "end": 5.0,
      "text": "Hello and welcome to this video."
    }
  ]
}
```

## Configuration

Edit your `.env` file to customize:

- **`OPENAI_API_KEY`** - Your OpenAI API key (required)
- **`OUT_DIR`** - Output directory (default: `./out`)
- **`MODEL`** - Whisper model to use (default: `whisper-1`)
- **`MAX_RETRIES`** - Number of retry attempts (default: `2`)

## Caching

The tool automatically caches:
- Downloaded audio files
- Generated transcripts

If you want to re-download or re-transcribe, you'll need to manually delete the cached files or modify the code to add a `--force` flag.

## Error Handling

- If a video fails to download, the error is shown and you can try another video
- Network errors automatically retry up to `MAX_RETRIES` times
- Clear error messages for common issues (missing API key, quota errors, etc.)

## Troubleshooting

### "OPENAI_API_KEY is required"
- Make sure you've created a `.env` file with your API key
- Check that the `.env` file is in the project root directory

### "Failed to download audio"
- Check your internet connection
- Verify the YouTube URL is valid and accessible
- Some videos may be private or region-restricted

### "Rate limit exceeded"
- You've hit OpenAI's API rate limit
- Wait a few minutes and try again
- Consider upgrading your OpenAI plan if this happens frequently

### "Quota/billing error"
- Check your OpenAI account billing status
- Ensure you have credits available

## Technical Details

- **Audio Format**: Downloads m4a directly (no ffmpeg conversion needed)
- **Transcription**: Uses OpenAI Whisper API (`whisper-1` model)
- **Compatibility**: Works on Windows ARM64 (Snapdragon X Elite)
- **Dependencies**: yt-dlp, openai, python-dotenv, tqdm

## License

This project is provided as-is for personal use.

