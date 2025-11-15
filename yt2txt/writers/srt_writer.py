"""Writer for SRT subtitle format."""

from pathlib import Path
from yt2txt.models import Transcript


def format_timestamp(seconds: float) -> str:
    """Format seconds as SRT timestamp: HH:MM:SS,mmm."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def write_srt(transcript: Transcript, output_path: Path) -> None:
    """Write transcript to SRT subtitle file."""
    with open(output_path, 'w', encoding='utf-8') as f:
        for index, segment in enumerate(transcript.segments, start=1):
            start_time = format_timestamp(segment.start)
            end_time = format_timestamp(segment.end)
            
            # SRT format: index, timestamps, text (with line breaks)
            f.write(f"{index}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{segment.text}\n")
            f.write("\n")  # Blank line between entries

