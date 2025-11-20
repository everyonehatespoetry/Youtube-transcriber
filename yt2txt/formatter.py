"""Transcript formatting using OpenAI GPT."""

import time
from pathlib import Path
from openai import OpenAI
from openai import APIError, RateLimitError, APIConnectionError
from tqdm import tqdm

from yt2txt.config import Config
from yt2txt.models import Transcript
from yt2txt.analyzer import get_transcript_text


# Formatting system prompt
FORMATTING_PROMPT = """You are an expert editor. Your task is to format the provided raw transcript into a readable, structured document.

Rules:
1.  **Paragraphs**: Group the text into logical paragraphs based on topic changes or natural pauses.
2.  **Speakers**: If you can identify different speakers (e.g., an interviewer and an interviewee), label them as "Speaker A:", "Speaker B:", etc., or use their names if they introduce themselves. If it's a monologue, just use paragraphs.
3.  **Timestamps**: PRESERVE the approximate timestamp for the start of each paragraph if possible, in the format [MM:SS].
4.  **Content**: Do NOT summarize or change the content. Keep the wording as close to verbatim as possible while fixing major dysfluencies (ums, ahs) if they distract from readability.
5.  **Structure**: Output the result as a clean, formatted text.

Example Output:
[00:00] Speaker A: Welcome to the show. Today we have a special guest.

[00:15] Speaker B: Thanks for having me. It's great to be here.

[00:20] Speaker A: Let's dive right in. Tell us about your new project.
"""


def format_transcript(
    transcript: Transcript,
    output_dir: Path,
    force: bool = False
) -> str:
    """
    Format transcript using OpenAI GPT to add paragraphs and speaker labels.
    
    Args:
        transcript: Transcript object with segments
        output_dir: Directory where formatted text will be saved
        force: If True, re-format even if cached
        
    Returns:
        Formatted transcript text
    """
    formatted_path = output_dir / "formatted_transcript.txt"
    
    # Check cache
    if not force and formatted_path.exists():
        print(f"✓ Using cached formatted transcript")
        with open(formatted_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    # Validate API key
    Config.validate()
    
    # Initialize OpenAI client
    client = OpenAI(
        api_key=Config.OPENAI_API_KEY,
        timeout=300.0  # 5 minute timeout
    )
    
    # Get transcript text
    transcript_text = get_transcript_text(transcript)
    
    # Prepare the full prompt
    user_message = f"{FORMATTING_PROMPT}\n\nRAW TRANSCRIPT:\n{transcript_text}"
    
    # Get analysis model from config (use same model as analysis)
    model = Config.ANALYSIS_MODEL
    
    # Analyze with retries
    last_error = None
    for attempt in range(Config.MAX_RETRIES + 1):
        try:
            if attempt > 0:
                print(f"Formatting transcript (attempt {attempt + 1}/{Config.MAX_RETRIES + 1})...")
            else:
                print("Formatting transcript with GPT...")
            
            # Create progress bar
            with tqdm(
                total=100,
                desc="Formatting",
                unit="%",
                bar_format="{desc}: {percentage:3.0f}%|{bar}| {elapsed}",
                ncols=80,
                leave=False
            ) as pbar:
                # Simulate progress
                progress_complete = False
                
                def update_progress():
                    """Simulate progress since API doesn't provide real-time updates."""
                    nonlocal progress_complete
                    current = 0
                    while not progress_complete and current < 95:
                        time.sleep(0.2)
                        current = min(current + 2, 95)
                        pbar.n = int(current)
                        pbar.refresh()
                
                import threading
                progress_thread = threading.Thread(target=update_progress, daemon=True)
                progress_thread.start()
                
                try:
                    # Prepare request parameters
                    request_params = {
                        "model": model,
                        "messages": [
                            {
                                "role": "user",
                                "content": user_message
                            }
                        ],
                        "temperature": 0.3  # Low temperature for faithful formatting
                    }
                    
                    response = client.chat.completions.create(**request_params)
                    
                    progress_complete = True
                    pbar.n = 100
                    pbar.refresh()
                    progress_thread.join(timeout=0.5)
                except Exception as e:
                    progress_complete = True
                    progress_thread.join(timeout=0.5)
                    raise
            
            # Extract formatted text
            formatted_text = response.choices[0].message.content
            
            # Save to file
            with open(formatted_path, 'w', encoding='utf-8') as f:
                f.write(formatted_text)
            
            print(f"✓ Formatting complete")
            return formatted_text
            
        except RateLimitError as e:
            last_error = e
            if attempt < Config.MAX_RETRIES:
                wait_time = 2 ** attempt
                print(f"Rate limit hit. Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                continue
            else:
                raise RuntimeError(f"Rate limit exceeded: {e}") from e
                
        except APIConnectionError as e:
            last_error = e
            if attempt < Config.MAX_RETRIES:
                wait_time = 2 ** attempt
                print(f"Connection error. Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                continue
            else:
                raise RuntimeError(f"Connection error: {e}") from e
                
        except APIError as e:
            # Handle server errors (5xx) with retry
            is_5xx_error = hasattr(e, 'status_code') and e.status_code and 500 <= e.status_code < 600
            if is_5xx_error and attempt < Config.MAX_RETRIES:
                wait_time = 2 ** attempt
                print(f"Server error. Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                continue
            
            raise RuntimeError(f"OpenAI API error: {e}") from e
            
        except Exception as e:
            raise RuntimeError(f"Unexpected error during formatting: {str(e)}") from e
    
    raise RuntimeError(f"Failed to format after {Config.MAX_RETRIES + 1} attempts") from last_error
