"""Data models for transcripts and segments."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class Segment:
    """A single segment of transcribed text with timing information."""
    start: float  # Start time in seconds
    end: float    # End time in seconds
    text: str     # Transcribed text


@dataclass
class Transcript:
    """Complete transcript with metadata."""
    video_id: str
    url: str
    title: Optional[str] = None
    channel: Optional[str] = None
    duration: Optional[int] = None  # Duration in seconds
    language: Optional[str] = None
    segments: list[Segment] = None
    
    def __post_init__(self):
        """Initialize segments list if not provided."""
        if self.segments is None:
            self.segments = []

