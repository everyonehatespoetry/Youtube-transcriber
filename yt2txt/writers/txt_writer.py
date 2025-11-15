"""Writer for TXT format with timestamps."""

from pathlib import Path
from yt2txt.models import Transcript


def format_seconds(seconds: float) -> str:
    """Format seconds as HH:MM:SS."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def write_txt(transcript: Transcript, output_path: Path) -> None:
    """
    Write transcript to TXT file with timestamps.
    
    Format: [HH:MM:SS - HH:MM:SS] text
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        for segment in transcript.segments:
            start_time = format_seconds(segment.start)
            end_time = format_seconds(segment.end)
            f.write(f"[{start_time} - {end_time}] {segment.text}\n")

