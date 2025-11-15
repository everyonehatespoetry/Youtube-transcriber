"""OpenAI GPT API integration for transcript analysis."""

import time
from pathlib import Path
from typing import Optional
from openai import OpenAI
from openai import APIError, RateLimitError, APIConnectionError
from tqdm import tqdm

from yt2txt.config import Config
from yt2txt.models import Transcript


# Equity analysis system prompt
EQUITY_ANALYSIS_PROMPT = """You are an expert equity analyst focused on U.S. and Canadian microcap companies. Your job is to extract forward-looking information, business trends, demand commentary, and operational signals from CEO interviews with extreme precision and zero hallucination.

If the transcript does not contain information, say so. Never guess.

Analyze the following CEO interview transcript and produce a structured, investor-ready summary.

Focus heavily on forward-looking signals, operational commentary, guidance, orders, demand trends, and any remarks that could materially impact revenue, margins, backlog, cash flow, or strategic positioning.

Format your output exactly as follows:

1. EXECUTIVE SUMMARY (5–8 bullet points)

The most important takeaways

No filler, only items with relevance to revenue, margins, or strategic direction

2. FORWARD-LOOKING GUIDANCE & OUTLOOK

Extract verbatim where possible. Include:

Explicit revenue / margin / EBITDA guidance

Qualitative outlook (e.g., "demand strong in Q4", "expecting sequential improvement")

Commentary on bookings, pipeline, order visibility

Any management claims about acceleration, deceleration, or inflection points

Commentary about 202X–202Y expectations

If something is vague, label it: (vague), (soft indicator), (low confidence).

If they refuse to give guidance, state that explicitly.

3. DEMAND / MARKET TRENDS

Anything related to:

Customer demand patterns

Industry tailwinds/headwinds

New regulations, incentives, or macro forces

Sector-level commentary (e.g., "retail channel improving", "industrial customers destocking")

4. OPERATIONAL UPDATES (CONCISE MAX 5 BULLET POINTS)

Capture:

Capacity expansions / constraints

Hiring, layoffs, capex plans

Supply-chain commentary

Manufacturing, lead times, throughput, backlog

Gross margin drivers, cost reductions

5. CONTRACTS, ORDERS, CUSTOMERS

List ONLY factual statements from transcript regarding:

New orders

Lost orders

Contract renewals

Customer wins or churn

Pipeline comments

If specific customers are mentioned, list them.

If not, refer to them generically.

M&A intentions

6. RISKS & CAVEATS MENTIONED BY MANAGEMENT (MAKE IT SHORT 3-4 BULLET POINTS)

Capture anything related to:

Geopolitical risk

Regulatory timelines

Financing needs

FX

Cyclicality

Concentration risks

7. QUOTES THAT MATTER

Pull 5–6 of the most important verbatim quotes that relate to:

Directional demand signals

Guidance

Strategy

Margin commentary

Customer behaviour

Only include quotes that have investment relevance."""


def get_transcript_text(transcript: Transcript) -> str:
    """
    Convert transcript segments into a single text string.
    
    Args:
        transcript: Transcript object with segments
        
    Returns:
        Full transcript text
    """
    return "\n".join(segment.text for segment in transcript.segments)


def analyze_transcript(
    transcript: Transcript,
    output_dir: Path,
    force: bool = False
) -> str:
    """
    Analyze transcript using OpenAI GPT API with equity analysis prompt.
    
    Args:
        transcript: Transcript object with segments
        output_dir: Directory where analysis will be saved
        force: If True, re-analyze even if cached
        
    Returns:
        Analysis text
    """
    analysis_path = output_dir / "equity_analysis.txt"
    
    # Check cache
    if not force and analysis_path.exists():
        print(f"✓ Using cached analysis")
        with open(analysis_path, 'r', encoding='utf-8') as f:
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
    user_message = f"{EQUITY_ANALYSIS_PROMPT}\n\nUSER: {transcript_text}"
    
    # Get analysis model from config
    analysis_model = Config.ANALYSIS_MODEL
    
    # Analyze with retries
    last_error = None
    for attempt in range(Config.MAX_RETRIES + 1):
        try:
            if attempt > 0:
                print(f"Analyzing transcript (attempt {attempt + 1}/{Config.MAX_RETRIES + 1})...")
            else:
                print("Analyzing transcript with GPT...")
            
            # Create progress bar
            with tqdm(
                total=100,
                desc="Analyzing",
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
                        "model": analysis_model,
                        "messages": [
                            {
                                "role": "user",
                                "content": user_message
                            }
                        ]
                    }
                    
                    # Only set temperature if model supports it (gpt-5-nano only supports default)
                    if not analysis_model.startswith("gpt-5"):
                        request_params["temperature"] = 0.3  # Lower temperature for more precise analysis
                    
                    response = client.chat.completions.create(**request_params)
                    
                    progress_complete = True
                    pbar.n = 100
                    pbar.refresh()
                    progress_thread.join(timeout=0.5)
                except Exception as e:
                    progress_complete = True
                    progress_thread.join(timeout=0.5)
                    raise
            
            # Extract analysis text
            analysis_text = response.choices[0].message.content
            
            print(f"✓ Analysis complete")
            return analysis_text
            
        except RateLimitError as e:
            last_error = e
            if attempt < Config.MAX_RETRIES:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"Rate limit hit. Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                continue
            else:
                raise RuntimeError(
                    f"Rate limit exceeded after {Config.MAX_RETRIES + 1} attempts. "
                    f"Please try again later."
                ) from e
                
        except APIConnectionError as e:
            last_error = e
            if attempt < Config.MAX_RETRIES:
                wait_time = 2 ** attempt
                print(f"Connection error. Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                continue
            else:
                raise RuntimeError(
                    f"Connection error after {Config.MAX_RETRIES + 1} attempts: {str(e)}"
                ) from e
                
        except APIError as e:
            error_msg = str(e)
            
            # Check if it's an HTML response (502/503 gateway errors)
            is_html_error = "<!DOCTYPE html>" in error_msg or "<html" in error_msg.lower()
            is_5xx_error = hasattr(e, 'status_code') and e.status_code and 500 <= e.status_code < 600
            
            # Retry on 5xx server errors (including 502 Bad Gateway)
            if (is_html_error or is_5xx_error) and attempt < Config.MAX_RETRIES:
                last_error = e
                wait_time = 2 ** attempt
                if is_html_error:
                    print(f"Server error (502 Bad Gateway). Waiting {wait_time} seconds before retry...")
                else:
                    print(f"Server error ({getattr(e, 'status_code', '5xx')}). Waiting {wait_time} seconds before retry...")
                time.sleep(wait_time)
                continue
            
            # Non-retryable API errors
            if "quota" in error_msg.lower() or "billing" in error_msg.lower():
                raise RuntimeError(
                    f"OpenAI API quota/billing error: {error_msg}. "
                    f"Please check your OpenAI account."
                ) from e
            
            # Clean up HTML error messages
            if is_html_error:
                raise RuntimeError(
                    "OpenAI API server error (502 Bad Gateway). "
                    "This is a temporary issue on OpenAI's servers. Please try again in a few minutes."
                ) from e
            
            raise RuntimeError(f"OpenAI API error: {error_msg}") from e
            
        except Exception as e:
            raise RuntimeError(f"Unexpected error during analysis: {str(e)}") from e
    
    # Should not reach here, but just in case
    raise RuntimeError(f"Failed to analyze after {Config.MAX_RETRIES + 1} attempts") from last_error

