"""Writer for slide text with timestamps."""

from pathlib import Path
from yt2txt.writers.txt_writer import format_seconds


def write_slides(slides: list, output_path: Path) -> None:
    """
    Write slide text to file with timestamps.
    
    Args:
        slides: List of (timestamp, text) tuples
        output_path: Path to output file
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        for timestamp, text in slides:
            time_str = format_seconds(timestamp)
            f.write(f"[{time_str}]\n")
            f.write(f"{text}\n")
            f.write("\n" + "-" * 60 + "\n\n")

