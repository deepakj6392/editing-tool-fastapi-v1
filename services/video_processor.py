"""
Video processing service using FFmpeg subprocess.
Provides functions for video metadata extraction, trimming, adjusting, and overlaying.
"""
import subprocess
import json
import os
import asyncio
import shutil
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any
from models.video_process import TextOverlay, LogoOverlay


class VideoProcessingError(Exception):
    """Custom exception for video processing errors"""
    pass


def is_ffmpeg_installed() -> bool:
    """Check if FFmpeg is installed on the system"""
    return shutil.which('ffmpeg') is not None


def is_ffprobe_installed() -> bool:
    """Check if FFprobe is installed on the system"""
    return shutil.which('ffprobe') is not None


async def get_video_info(input_path: str) -> Dict[str, Any]:
    """
    Extract video metadata using ffprobe.
    
    Args:
        input_path: Path to the video file
        
    Returns:
        Dictionary containing video metadata
        
    Raises:
        VideoProcessingError: If ffprobe fails or video info cannot be extracted
    """
    if not os.path.exists(input_path):
        raise VideoProcessingError(f"Input file not found: {input_path}")
    
    ffprobe_cmd = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,codec_name,r_frame_rate,display_aspect_ratio',
        '-show_entries', 'format=duration,size,bit_rate,format_name',
        '-of', 'json',
        input_path
    ]
    
    try:
        process = await asyncio.create_subprocess_exec(
            *ffprobe_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise VideoProcessingError(f"ffprobe failed: {stderr.decode()}")
        
        probe_data = json.loads(stdout.decode())
        
        if 'streams' not in probe_data or len(probe_data['streams']) == 0:
            raise VideoProcessingError("No video stream found in file")
        
        video_stream = probe_data['streams'][0]
        format_info = probe_data.get('format', {})
        
        # Calculate FPS from r_frame_rate (e.g., "30/1" -> 30.0)
        fps_parts = video_stream.get('r_frame_rate', '30/1').split('/')
        fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else 30.0
        
        info = {
            'duration': float(format_info.get('duration', 0)),
            'size': int(format_info.get('size', 0)),
            'bitrate': int(format_info.get('bit_rate', 0)),
            'format': format_info.get('format_name', 'unknown'),
            'video': {
                'codec': video_stream.get('codec_name', 'unknown'),
                'width': int(video_stream.get('width', 0)),
                'height': int(video_stream.get('height', 0)),
                'fps': fps,
                'aspect_ratio': video_stream.get('display_aspect_ratio', '16:9')
            }
        }
        
        return info
        
    except subprocess.SubprocessError as e:
        raise VideoProcessingError(f"Failed to execute ffprobe: {str(e)}")
    except json.JSONDecodeError as e:
        raise VideoProcessingError(f"Failed to parse ffprobe output: {str(e)}")


def build_overlay_filter(
    trim_start: float,
    text_overlays: List[TextOverlay],
    logo_overlays: List[LogoOverlay],
    logo_files: Dict[str, str],  # filename -> file_path mapping
    video_width: int,
    video_height: int,
    brightness: float = 0.0,
    contrast: float = 1.0,
    saturation: float = 1.0
) -> Tuple[str, List[str]]:
    """
    Build FFmpeg filter_complex string for video processing.
    
    Args:
        trim_start: Trim start time in seconds
        text_overlays: List of text overlay configurations
        logo_overlays: List of logo overlay configurations
        logo_files: Dictionary mapping logo filenames to file paths
        video_width: Video width in pixels
        video_height: Video height in pixels
        brightness: Brightness adjustment (-1 to 1)
        contrast: Contrast adjustment (0 to 4)
        saturation: Saturation adjustment (0 to 4)
        
    Returns:
        Tuple of (filter_complex string, list of additional input files)
    """
    inputs: List[str] = []
    input_index = 1
    
    # Add logo inputs first
    for logo in logo_overlays:
        logo_file_path = logo_files.get(logo.filename)
        if logo_file_path and os.path.exists(logo_file_path):
            inputs.extend(['-i', logo_file_path])
    
    # Build filter complex
    # Start with brightness/contrast/saturation adjustment
    # eq=brightness=X:contrast=Y:saturation=Z
    filter_complex = f"[0:v]eq=brightness={brightness}:contrast={contrast}:saturation={saturation}[base]"
    
    current_label = 'base'
    logo_index = 1
    
    # Add logo overlays
    for idx, logo in enumerate(logo_overlays):
        logo_file_path = logo_files.get(logo.filename)
        if not logo_file_path or not os.path.exists(logo_file_path):
            continue
        
        # Calculate start and end times relative to trim
        start_time = max(0, (logo.start or logo.startTime or 0) - trim_start)
        end_time = (logo.end or logo.endTime)
        if end_time is not None:
            end_time = max(0, end_time - trim_start)
        
        enable_clause = f"enable='between(t,{start_time},{end_time if end_time is not None else 'INF'})'"
        
        # Scale logo based on video resolution
        # Assuming frontend preview is 640px wide
        preview_width = 640
        scale_factor = video_width / preview_width
        scaled_width = round((logo.width or 100) * scale_factor)
        scaled_height = round((logo.height or 100) * scale_factor)
        
        scaled_label = f"logo{idx}"
        
        # Add scale filter for logo
        filter_complex += f";[{logo_index}:v]scale={scaled_width}:{scaled_height}[{scaled_label}]"
        
        # Add overlay filter
        filter_complex += f";[{current_label}][{scaled_label}]overlay=(main_w*{logo.x}/100):(main_h*{logo.y}/100):{enable_clause}[out{idx}]"
        current_label = f"out{idx}"
        logo_index += 1
    
    # Add text overlays
    for idx, text in enumerate(text_overlays):
        # Calculate start and end times relative to trim
        start_time = max(0, (text.start or text.startTime or 0) - trim_start)
        end_time = (text.end or text.endTime)
        if end_time is not None:
            end_time = max(0, end_time - trim_start)
        
        enable_clause = f"enable='between(t,{start_time},{end_time if end_time is not None else 'INF'})'"
        
        # Scale font size based on video resolution
        preview_width = 640
        scale_factor = video_width / preview_width
        base_fontsize = text.fontSize or text.fontsize or 24
        scaled_fontsize = round(base_fontsize * scale_factor)
        
        # Get font color (handle alternative field names)
        font_color = text.color or text.fontcolor or 'white'
        
        # Escape single quotes in text
        escaped_text = text.text.replace("'", "\\'")
        
        drawtext_filter = f"drawtext=text='{escaped_text}':x=(w*{text.x}/100):y=(h*{text.y}/100):fontsize={scaled_fontsize}:fontcolor={font_color}:{enable_clause}"
        
        filter_complex += f";[{current_label}]{drawtext_filter}[outtext{idx}]"
        current_label = f"outtext{idx}"
    
    # Final format conversion
    filter_complex += f";[{current_label}]format=yuv420p[outv]"
    
    return filter_complex, inputs


async def process_video(
    input_path: str,
    output_path: str,
    trim_start: float,
    trim_duration: Optional[float],
    brightness: float = 0.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    text_overlays: Optional[List[TextOverlay]] = None,
    logo_overlays: Optional[List[LogoOverlay]] = None,
    logo_files: Optional[Dict[str, str]] = None,
    debug_mode: bool = False
) -> bool:
    """
    Process video with FFmpeg using the specified parameters.
    
    Args:
        input_path: Path to input video file
        output_path: Path for output video file
        trim_start: Start time for trimming in seconds
        trim_duration: Duration to keep (None for until end)
        brightness: Brightness adjustment (-1 to 1)
        contrast: Contrast adjustment (0 to 4)
        saturation: Saturation adjustment (0 to 4)
        text_overlays: List of text overlay configurations
        logo_overlays: List of logo overlay configurations
        logo_files: Dictionary mapping logo filenames to file paths
        debug_mode: If True, keep intermediate files for debugging
        
    Returns:
        True if processing succeeded
        
    Raises:
        VideoProcessingError: If FFmpeg fails
    """
    if not os.path.exists(input_path):
        raise VideoProcessingError(f"Input file not found: {input_path}")
    
    # Get video dimensions for scaling
    video_info = await get_video_info(input_path)
    video_width = video_info['video']['width']
    video_height = video_info['video']['height']
    
    # Prepare empty lists if None
    text_overlays = text_overlays or []
    logo_overlays = logo_overlays or []
    logo_files = logo_files or {}
    
    # Build filter complex
    filter_complex, additional_inputs = build_overlay_filter(
        trim_start=trim_start,
        text_overlays=text_overlays,
        logo_overlays=logo_overlays,
        logo_files=logo_files,
        video_width=video_width,
        video_height=video_height,
        brightness=brightness,
        contrast=contrast,
        saturation=saturation
    )
    
    # Build FFmpeg command
    ffmpeg_cmd = [
        'ffmpeg',
        '-i', input_path,
        *additional_inputs,
        '-ss', str(trim_start),
    ]
    
    # Add duration if specified
    if trim_duration is not None:
        ffmpeg_cmd.extend(['-t', str(trim_duration)])
    
    ffmpeg_cmd.extend([
        '-filter_complex', filter_complex,
        '-map', '[outv]',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        '-y',  # Overwrite output
        output_path
    ])
    
    print(f"[DEBUG] FFmpeg command: {' '.join(ffmpeg_cmd)}")
    
    try:
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        stderr_text = stderr.decode()
        
        if process.returncode != 0:
            print(f"[ERROR] FFmpeg stderr: {stderr_text}")
            raise VideoProcessingError(f"FFmpeg failed with exit code {process.returncode}: {stderr_text}")
        
        if not os.path.exists(output_path):
            raise VideoProcessingError("FFmpeg completed but output file was not created")
        
        print(f"[SUCCESS] Video processed successfully: {output_path}")
        return True
        
    except subprocess.SubprocessError as e:
        raise VideoProcessingError(f"Failed to execute FFmpeg: {str(e)}")


def cleanup_file(file_path: str) -> None:
    """Safely delete a file if it exists"""
    try:
        if file_path and os.path.exists(file_path):
            os.unlink(file_path)
    except Exception as e:
        print(f"[WARN] Failed to cleanup file {file_path}: {e}")


def cleanup_files(file_paths: List[str]) -> None:
    """Safely delete multiple files"""
    for path in file_paths:
        cleanup_file(path)

