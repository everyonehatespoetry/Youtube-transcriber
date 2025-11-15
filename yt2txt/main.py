"""Interactive main entry point for YouTube transcription."""

import sys
from pathlib import Path
from yt2txt.config import Config
from yt2txt.downloader import download_audio, get_output_dir
from yt2txt.video_downloader import download_video
from yt2txt.transcriber import transcribe_audio
from yt2txt.analyzer import analyze_transcript
from yt2txt.chat import start_chat_session
from yt2txt.slide_extractor import SlideExtractor
from yt2txt.writers.txt_writer import write_txt
from yt2txt.writers.json_writer import write_json
from yt2txt.writers.srt_writer import write_srt
from yt2txt.writers.analysis_writer import write_analysis


def process_video(url: str, force: bool = False, extract_slides: bool = False, analyze: bool = False):
    """
    Process a single video: download, transcribe, and write outputs.
    
    Args:
        url: YouTube video URL
        force: If True, re-download even if cached
        extract_slides: If True, extract and OCR slides from video
        analyze: If True, analyze transcript with GPT for equity analysis
        
    Returns:
        Tuple of (output_dir, transcript, analysis_text)
    """
    try:
        # Download audio
        audio_path, metadata, video_id = download_audio(url, force=force)
        output_dir = audio_path.parent
        
        # Transcribe
        transcript = transcribe_audio(audio_path, video_id, url, metadata, force=force)
        
        # Write outputs
        print("Writing transcript files...")
        write_json(transcript, output_dir / "transcript.json")
        write_txt(transcript, output_dir / "transcript_with_timestamps.txt")
        write_srt(transcript, output_dir / "transcript.srt")
        
        # Analyze transcript if requested
        analysis_text = None
        if analyze:
            print()
            print("Analyzing transcript with GPT...")
            try:
                analysis_text = analyze_transcript(transcript, output_dir, force=force)
                write_analysis(analysis_text, output_dir / "equity_analysis.txt")
                print(f"✓ Equity analysis saved to: equity_analysis.txt")
                
                # Show the analysis
                print()
                print("=" * 60)
                print("EQUITY ANALYSIS")
                print("=" * 60)
                print(analysis_text)
                print("=" * 60)
                
            except Exception as e:
                print(f"⚠ Error analyzing transcript: {str(e)}")
                print("Continuing without analysis...")
        
        # Extract slides if requested
        if extract_slides:
            print()
            print("Extracting slides from video...")
            try:
                # Download video (not just audio)
                video_path, _, _ = download_video(url, force=force)
                
                # Extract slides (images only, no OCR)
                extractor = SlideExtractor()
                # Extract every 1 second, then deduplicate in post-processing
                slides = extractor.process_video(video_path, output_dir, interval_seconds=1.0)
                
                if slides:
                    # Create a manifest file listing all slides with timestamps
                    import json
                    slides_manifest = [
                        {
                            'timestamp': timestamp,
                            'image_path': str(slide_path.relative_to(output_dir)),
                            'time_formatted': f"{int(timestamp // 60):02d}:{int(timestamp % 60):02d}"
                        }
                        for timestamp, slide_path in slides
                    ]
                    manifest_path = output_dir / "slides_manifest.json"
                    with open(manifest_path, 'w', encoding='utf-8') as f:
                        json.dump(slides_manifest, f, indent=2)
                    
                    # Create an HTML file for easy viewing
                    html_content = """<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Video Slides</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        h1 {
            color: #333;
            border-bottom: 2px solid #333;
            padding-bottom: 10px;
        }
        .slide {
            background: white;
            margin: 30px 0;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .slide-header {
            font-size: 20px;
            font-weight: bold;
            color: #333;
            margin-bottom: 15px;
        }
        .slide img {
            width: 100%;
            max-width: 1200px;
            height: auto;
            border: 2px solid #ddd;
            border-radius: 4px;
            display: block;
            margin: 0 auto;
            image-rendering: -webkit-optimize-contrast;
            image-rendering: crisp-edges;
        }
        .slide img:hover {
            border-color: #666;
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }
    </style>
</head>
<body>
    <h1>Video Slides</h1>
"""
                    for i, (timestamp, slide_path) in enumerate(slides, 1):
                        time_formatted = f"{int(timestamp // 60):02d}:{int(timestamp % 60):02d}"
                        relative_path = slide_path.relative_to(output_dir)
                        html_content += f"""
    <div class="slide">
        <div class="slide-header">Slide {i} - Time: {time_formatted}</div>
        <img src="{relative_path.as_posix()}" alt="Slide at {time_formatted}">
    </div>
"""
                    html_content += """
</body>
</html>
"""
                    html_path = output_dir / "slides_viewer.html"
                    with open(html_path, 'w', encoding='utf-8') as f:
                        f.write(html_content)
                    
                    print(f"✓ Slide images saved to: frames/")
                    print(f"✓ Slide manifest saved to: slides_manifest.json")
                    print(f"✓ Slide viewer saved to: slides_viewer.html (open in browser to view all slides)")
                else:
                    print("⚠ No slides found in video")
                    
            except Exception as e:
                print(f"⚠ Error extracting slides: {str(e)}")
                print("Continuing without slide extraction...")
        
        print(f"✓ All files saved successfully!")
        return output_dir, transcript, analysis_text
        
    except Exception as e:
        print(f"\n✗ Error processing video: {str(e)}", file=sys.stderr)
        raise


def main():
    """Interactive main function."""
    print("=" * 60)
    print("YouTube Video Transcriber")
    print("=" * 60)
    print()
    
    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        print(f"✗ Configuration Error: {str(e)}", file=sys.stderr)
        print("\nPlease create a .env file with your OPENAI_API_KEY.")
        print("See .env.example for reference.")
        input("\nPress Enter to exit...")
        sys.exit(1)
    
    # Ensure output directory exists
    Config.OUT_DIR.mkdir(parents=True, exist_ok=True)
    
    while True:
        print()
        print("-" * 60)
        url = input("Please paste the URL of the YouTube video you wish to transcribe: ").strip()
        
        if not url:
            print("No URL provided. Exiting...")
            break
        
        print()
        extract_slides = input("Extract slides from video? (y/n): ").strip().lower() in ('y', 'yes')
        print()
        analyze = input("Analyze transcript with GPT for equity analysis? (y/n): ").strip().lower() in ('y', 'yes')
        
        print()
        print("Processing video...")
        print()
        
        try:
            output_dir, transcript, analysis_text = process_video(url, force=False, extract_slides=extract_slides, analyze=analyze)
            
            print()
            print("=" * 60)
            print("✓ Transcription complete!")
            print(f"Files saved to: {output_dir}")
            print("=" * 60)
            
            # Offer interactive chat (available whenever transcript exists)
            if transcript:
                print()
                chat_choice = input("Would you like to ask questions about the transcript? (y/n): ").strip().lower()
                if chat_choice in ('y', 'yes'):
                    try:
                        start_chat_session(transcript)
                    except Exception as e:
                        print(f"\n⚠ Error starting chat session: {str(e)}")
            
        except Exception as e:
            print()
            print("=" * 60)
            print(f"✗ Failed to process video: {str(e)}")
            print("=" * 60)
        
        print()
        another = input("Would you like to transcribe another video? (y/n): ").strip().lower()
        if another not in ('y', 'yes'):
            break
    
    print()
    print("Thank you for using YouTube Video Transcriber!")
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()

