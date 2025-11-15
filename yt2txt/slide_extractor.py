"""Extract slides from video as images using scene change detection."""

import cv2
import numpy as np
from pathlib import Path
from typing import List, Tuple


class SlideExtractor:
    """Extract slides from video as images using scene change detection."""
    
    def __init__(self):
        """Initialize slide extractor."""
        pass
    
    def _detect_scene_change(self, frame1: np.ndarray, frame2: np.ndarray, threshold: float = 0.3) -> bool:
        """
        Detect if there's a significant scene change between two frames.
        Returns True if frames are different enough to be considered a new slide.
        
        Uses multiple methods:
        1. Histogram difference
        2. Structural similarity (SSIM-like)
        3. Edge difference
        """
        # Resize to same size for comparison
        h1, w1 = frame1.shape[:2]
        h2, w2 = frame2.shape[:2]
        target_h, target_w = min(h1, h2, 360), min(w1, w2, 640)
        
        f1 = cv2.resize(frame1, (target_w, target_h))
        f2 = cv2.resize(frame2, (target_w, target_h))
        
        # Method 1: Histogram difference
        hist1 = cv2.calcHist([f1], [0], None, [256], [0, 256])
        hist2 = cv2.calcHist([f2], [0], None, [256], [0, 256])
        hist_diff = cv2.compareHist(hist1, hist2, cv2.HISTCMP_BHATTACHARYYA)
        
        # Method 2: Structural difference (pixel-level)
        diff = cv2.absdiff(f1, f2)
        mean_diff = np.mean(diff) / 255.0
        
        # Method 3: Edge difference (captures layout changes)
        edges1 = cv2.Canny(f1, 50, 150)
        edges2 = cv2.Canny(f2, 50, 150)
        edge_diff = cv2.absdiff(edges1, edges2)
        edge_change = np.sum(edge_diff > 0) / (target_h * target_w)
        
        # Combine metrics - if any indicates significant change, it's a new slide
        # Lower threshold = more sensitive (catches more slides)
        is_change = (hist_diff > threshold) or (mean_diff > threshold) or (edge_change > 0.15)
        
        return is_change
    
    def extract_frames(
        self,
        video_path: Path,
        output_dir: Path,
        interval_seconds: float = 0.5,  # Check frequently for scene changes
        scene_change_threshold: float = 0.25  # Lower = more sensitive to changes
    ) -> List[Tuple[float, Path]]:
        """
        Extract slides by detecting scene changes (slide transitions).
        
        This approach detects WHEN slides change, rather than comparing to previous slides.
        More reliable for presentation videos.
        
        Args:
            video_path: Path to video file
            output_dir: Directory to save extracted frames
            interval_seconds: How often to check for scene changes (seconds)
            scene_change_threshold: Sensitivity for detecting changes (0-1, lower = more sensitive)
            
        Returns:
            List of (timestamp, frame_path) tuples for unique slides
        """
        if not video_path.exists():
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        output_dir.mkdir(parents=True, exist_ok=True)
        frames_dir = output_dir / "frames"
        frames_dir.mkdir(exist_ok=True)
        
        print(f"Detecting slide changes in video (checking every {interval_seconds}s)...")
        
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise RuntimeError(
                f"Could not open video file: {video_path}\n"
                f"This usually means the video file is corrupted or in an unsupported format.\n"
                f"Try deleting the cached video file and re-downloading."
            )
        
        # Get video properties
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = total_frames / fps if fps > 0 else 0
        
        # Verify we can actually read frames
        ret, test_frame = cap.read()
        if not ret or test_frame is None:
            cap.release()
            raise RuntimeError(
                f"Video file exists but cannot read frames: {video_path}\n"
                f"The video file may be corrupted. Try deleting it and re-downloading."
            )
        # Reset to beginning
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        
        print(f"  Video resolution: {width}x{height}, FPS: {fps:.2f}, Duration: {duration:.1f}s")
        
        if width < 640 or height < 360:
            print(f"  ⚠ WARNING: Video resolution is very low ({width}x{height}). Slides may not be readable.")
            print(f"  ⚠ The video file may need to be re-downloaded in higher quality.")
            print(f"  ⚠ Delete the cached video file at: {video_path}")
        
        frame_interval = max(1, int(fps * interval_seconds)) if fps > 0 else 1
        
        extracted_frames = []
        previous_frame = None
        previous_timestamp = None
        frame_count = 0
        slide_count = 0
        
        print("  Scanning for slide changes...")
        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Check at intervals
                if frame_count % frame_interval == 0:
                    timestamp = frame_count / fps
                    
                    # Convert to grayscale for comparison
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    
                    # Detect if this is a scene change (new slide)
                    is_new_slide = True
                    if previous_frame is not None:
                        # Use scene change detection instead of similarity
                        is_new_slide = self._detect_scene_change(previous_frame, gray, scene_change_threshold)
                    
                    # Always save the first frame, and any detected scene changes
                    if previous_frame is None or is_new_slide:
                        # Save the frame
                        frame_filename = frames_dir / f"slide_{slide_count:03d}_{timestamp:.1f}s.png"
                        cv2.imwrite(str(frame_filename), frame, [cv2.IMWRITE_PNG_COMPRESSION, 1])
                        extracted_frames.append((timestamp, frame_filename))
                        previous_frame = gray.copy()
                        previous_timestamp = timestamp
                        slide_count += 1
                        print(f"  ✓ Found slide {slide_count} at {timestamp:.1f}s")
                
                frame_count += 1
                
        finally:
            cap.release()
        
        print(f"✓ Extracted {len(extracted_frames)} slides using scene change detection")
        return extracted_frames
    
    def _compare_frames_old(self, frame1: np.ndarray, frame2: np.ndarray) -> float:
        """Compare two frames and return similarity score (0-1). Higher = more similar."""
        # Resize frames to same size for comparison (use larger size for better accuracy)
        # Use aspect-ratio preserving resize
        h1, w1 = frame1.shape[:2]
        h2, w2 = frame2.shape[:2]
        
        # Resize to a standard size while maintaining aspect ratio
        target_size = 480
        scale1 = target_size / max(h1, w1)
        scale2 = target_size / max(h2, w2)
        
        new_w1, new_h1 = int(w1 * scale1), int(h1 * scale1)
        new_w2, new_h2 = int(w2 * scale2), int(h2 * scale2)
        
        frame1_resized = cv2.resize(frame1, (new_w1, new_h1))
        frame2_resized = cv2.resize(frame2, (new_w2, new_h2))
        
        # Method 1: Histogram comparison (good for overall color similarity)
        hist1 = cv2.calcHist([frame1_resized], [0], None, [256], [0, 256])
        hist2 = cv2.calcHist([frame2_resized], [0], None, [256], [0, 256])
        hist_correlation = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
        
        # Method 2: Template matching (better for structural similarity)
        # Resize both to same size for template matching
        min_h = min(new_h1, new_h2)
        min_w = min(new_w1, new_w2)
        frame1_match = cv2.resize(frame1_resized, (min_w, min_h))
        frame2_match = cv2.resize(frame2_resized, (min_w, min_h))
        
        # Calculate normalized correlation
        result = cv2.matchTemplate(frame1_match, frame2_match, cv2.TM_CCOEFF_NORMED)
        template_sim = result[0, 0]
        
        # Method 3: Pixel difference (for exact matches)
        diff = cv2.absdiff(frame1_match, frame2_match)
        pixel_diff = np.mean(diff) / 255.0
        pixel_sim = 1.0 - pixel_diff
        
        # Combine methods - template matching is most important for slides
        similarity = (hist_correlation * 0.2 + template_sim * 0.6 + pixel_sim * 0.2)
        return similarity
    
    def process_video(
        self,
        video_path: Path,
        output_dir: Path,
        interval_seconds: float = 2.0
    ) -> List[Tuple[float, Path]]:
        """
        Process video to extract slides as images (no OCR).
        
        Args:
            video_path: Path to video file
            output_dir: Output directory
            interval_seconds: Time between frame extractions
            
        Returns:
            List of (timestamp, image_path) tuples
        """
        # Extract frames (saves as JPG images)
        frames = self.extract_frames(video_path, output_dir, interval_seconds)
        
        print(f"✓ Extracted {len(frames)} slide images (ready for AI analysis)")
        return frames
