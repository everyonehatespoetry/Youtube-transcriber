"""Writer for equity analysis output."""

from pathlib import Path


def write_analysis(analysis_text: str, output_path: Path) -> None:
    """
    Write analysis text to file.
    
    Args:
        analysis_text: The analysis text from GPT
        output_path: Path where analysis will be saved
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(analysis_text)

