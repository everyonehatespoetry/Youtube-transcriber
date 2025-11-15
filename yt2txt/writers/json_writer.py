"""Writer for JSON format."""

import json
from pathlib import Path
from yt2txt.models import Transcript


def write_json(transcript: Transcript, output_path: Path) -> None:
    """Write transcript to JSON file."""
    data = {
        'video_id': transcript.video_id,
        'url': transcript.url,
        'title': transcript.title,
        'channel': transcript.channel,
        'duration': transcript.duration,
        'language': transcript.language,
        'segments': [
            {
                'start': segment.start,
                'end': segment.end,
                'text': segment.text
            }
            for segment in transcript.segments
        ]
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

