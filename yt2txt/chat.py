"""Interactive chat interface for asking questions about transcripts."""

from typing import List, Dict
from openai import OpenAI
from openai import APIError, RateLimitError, APIConnectionError
import time

from yt2txt.config import Config
from yt2txt.models import Transcript
from yt2txt.analyzer import get_transcript_text


def start_chat_session(transcript: Transcript) -> None:
    """
    Start an interactive chat session where user can ask questions about the transcript.
    
    Args:
        transcript: Transcript object with segments
    """
    # Validate API key
    Config.validate()
    
    # Initialize OpenAI client
    client = OpenAI(
        api_key=Config.OPENAI_API_KEY,
        timeout=300.0
    )
    
    # Get transcript text
    transcript_text = get_transcript_text(transcript)
    
    # Get analysis model from config
    analysis_model = Config.ANALYSIS_MODEL
    
    # Initialize conversation with transcript as context
    messages: List[Dict[str, str]] = [
        {
            "role": "system",
            "content": "You are an expert equity analyst analyzing a CEO interview transcript. Answer questions based on the transcript content. If the transcript doesn't contain the information, say so. Never guess or make up information."
        },
        {
            "role": "user",
            "content": f"Here is the transcript from a CEO interview:\n\n{transcript_text}"
        }
    ]
    
    print()
    print("=" * 60)
    print("INTERACTIVE Q&A MODE")
    print("=" * 60)
    print()
    print("You can now ask questions about the transcript.")
    print("The AI has access to the full transcript and will answer based on it.")
    print("Type 'quit', 'exit', or 'q' to end the session.")
    print()
    
    conversation_count = 0
    
    while True:
        try:
            # Get user question
            question = input("Your question: ").strip()
            
            if not question:
                continue
            
            # Check for exit commands
            if question.lower() in ('quit', 'exit', 'q'):
                print("\nEnding chat session. Goodbye!")
                break
            
            # Add user question to conversation
            messages.append({
                "role": "user",
                "content": question
            })
            
            # Show thinking indicator
            print("Thinking...", end="", flush=True)
            
            # Get response with retries
            response_text = None
            last_error = None
            
            for attempt in range(Config.MAX_RETRIES + 1):
                try:
                    # Prepare request parameters
                    request_params = {
                        "model": analysis_model,
                        "messages": messages
                    }
                    
                    # Only set temperature if model supports it
                    if not analysis_model.startswith("gpt-5"):
                        request_params["temperature"] = 0.3
                    
                    response = client.chat.completions.create(**request_params)
                    response_text = response.choices[0].message.content
                    break
                    
                except RateLimitError as e:
                    last_error = e
                    if attempt < Config.MAX_RETRIES:
                        wait_time = 2 ** attempt
                        print(f"\nRate limit hit. Waiting {wait_time} seconds...")
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
                        print(f"\nConnection error. Waiting {wait_time} seconds...")
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
                    
                    # Retry on 5xx server errors
                    if (is_html_error or is_5xx_error) and attempt < Config.MAX_RETRIES:
                        last_error = e
                        wait_time = 2 ** attempt
                        if is_html_error:
                            print(f"\nServer error (502 Bad Gateway). Waiting {wait_time} seconds...")
                        else:
                            print(f"\nServer error ({getattr(e, 'status_code', '5xx')}). Waiting {wait_time} seconds...")
                        time.sleep(wait_time)
                        continue
                    
                    # Non-retryable API errors
                    if "quota" in error_msg.lower() or "billing" in error_msg.lower():
                        raise RuntimeError(
                            f"OpenAI API quota/billing error: {error_msg}. "
                            f"Please check your OpenAI account."
                        ) from e
                    
                    if is_html_error:
                        raise RuntimeError(
                            "OpenAI API server error (502 Bad Gateway). "
                            "This is a temporary issue on OpenAI's servers. Please try again in a few minutes."
                        ) from e
                    
                    raise RuntimeError(f"OpenAI API error: {error_msg}") from e
            
            if response_text:
                # Clear "Thinking..." and show response
                print("\r" + " " * 50 + "\r", end="")  # Clear line
                print(f"AI: {response_text}\n")
                
                # Add assistant response to conversation history
                messages.append({
                    "role": "assistant",
                    "content": response_text
                })
                
                conversation_count += 1
                
                # Warn if conversation is getting long (to avoid token limits)
                if conversation_count > 20:
                    print("⚠ Note: Long conversation detected. Consider starting a new session for better performance.\n")
            else:
                raise RuntimeError("Failed to get response from API")
                
        except KeyboardInterrupt:
            print("\n\nInterrupted by user. Ending chat session.")
            break
        except Exception as e:
            print(f"\n✗ Error: {str(e)}")
            print("You can continue asking questions or type 'quit' to exit.\n")
            # Remove the last user message if there was an error
            if messages and messages[-1]["role"] == "user":
                messages.pop()

