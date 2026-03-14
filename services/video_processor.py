"""
Video processing service using FFmpeg subprocess.
Provides functions for video metadata extraction, trimming, adjusting, and overlaying.
"""
import subprocess
import json
import os
import asyncio
import shutil
import re
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
        '-show_entries',
        'stream=index,codec_type,codec_name,width,height,r_frame_rate,display_aspect_ratio,channels,sample_rate',
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
        
        streams = probe_data.get('streams', [])
        if len(streams) == 0:
            raise VideoProcessingError("No video stream found in file")

        video_stream = next((s for s in streams if s.get('codec_type') == 'video'), None)
        if not video_stream:
            raise VideoProcessingError("No video stream found in file")

        audio_stream = next((s for s in streams if s.get('codec_type') == 'audio'), None)
        format_info = probe_data.get('format', {})
        
        # Calculate FPS from r_frame_rate (e.g., "30/1" -> 30.0)
        fps_parts = video_stream.get('r_frame_rate', '30/1').split('/')
        fps = float(fps_parts[0]) / float(fps_parts[1]) if len(fps_parts) == 2 else 30.0
        
        info = {
            'duration': float(format_info.get('duration', 0)),
            'size': int(format_info.get('size', 0)),
            'bitrate': int(format_info.get('bit_rate', 0)),
            'format': format_info.get('format_name', 'unknown'),
            'has_audio': bool(audio_stream),
            'video': {
                'codec': video_stream.get('codec_name', 'unknown'),
                'width': int(video_stream.get('width', 0)),
                'height': int(video_stream.get('height', 0)),
                'fps': fps,
                'aspect_ratio': video_stream.get('display_aspect_ratio', '16:9')
            }
        }

        if audio_stream:
            info['audio'] = {
                'codec': audio_stream.get('codec_name', 'unknown'),
                'channels': int(audio_stream.get('channels', 0) or 0),
                'sample_rate': int(audio_stream.get('sample_rate', 0) or 0),
            }
        
        return info
        
    except subprocess.SubprocessError as e:
        raise VideoProcessingError(f"Failed to execute ffprobe: {str(e)}")
    except json.JSONDecodeError as e:
        raise VideoProcessingError(f"Failed to parse ffprobe output: {str(e)}")


def _resolve_overlay_time(primary: Optional[float], secondary: Optional[float], default: Optional[float]) -> Optional[float]:
    """Resolve overlay time from multiple aliases without treating 0 as falsy."""
    if primary is not None:
        return float(primary)
    if secondary is not None:
        return float(secondary)
    return default


def _escape_drawtext_text(text: str) -> str:
    """Escape text for FFmpeg drawtext filter."""
    return (
        text
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("\n", "\\n")
    )


def _normalize_ffmpeg_color(color: Optional[str]) -> str:
    """
    Normalize frontend color strings for FFmpeg drawtext.
    Converts #RRGGBB / #RGB to 0xRRGGBB for better filter compatibility.
    """
    if not color:
        return 'white'
    value = str(color).strip()
    if not value.startswith('#'):
        return value
    hex_value = value[1:]
    if len(hex_value) == 3 and re.fullmatch(r'[0-9a-fA-F]{3}', hex_value):
        hex_value = ''.join(ch * 2 for ch in hex_value)
    if re.fullmatch(r'[0-9a-fA-F]{6}([0-9a-fA-F]{2})?', hex_value):
        return f"0x{hex_value}"
    return 'white'


def build_overlay_filter(
    trim_start: float,
    text_overlays: List[TextOverlay],
    logo_overlays: List[LogoOverlay],
    logo_files: Dict[str, str],  # filename -> file_path mapping
    video_width: int,
    video_height: int,
    logo_file_sequence: Optional[List[Optional[str]]] = None,
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
        logo_file_sequence: Optional list of file paths aligned to logo_overlays index
        video_width: Video width in pixels
        video_height: Video height in pixels
        brightness: Brightness adjustment (-1 to 1)
        contrast: Contrast adjustment (0 to 4)
        saturation: Saturation adjustment (0 to 4)
        
    Returns:
        Tuple of (filter_complex string, list of additional input files)
    """
    inputs: List[str] = []
    resolved_logo_paths: List[Optional[str]] = []

    for idx, logo in enumerate(logo_overlays):
        logo_file_path: Optional[str] = None
        if logo_file_sequence and idx < len(logo_file_sequence):
            logo_file_path = logo_file_sequence[idx]
        if not logo_file_path:
            logo_file_path = logo_files.get(logo.filename)
        if logo_file_path and os.path.exists(logo_file_path):
            resolved_logo_paths.append(logo_file_path)
            inputs.extend(['-i', logo_file_path])
        else:
            resolved_logo_paths.append(None)

    # Add logo inputs first
    # Build filter complex
    # Start with brightness/contrast/saturation adjustment
    # eq=brightness=X:contrast=Y:saturation=Z
    filter_complex = f"[0:v]eq=brightness={brightness}:contrast={contrast}:saturation={saturation}[base]"
    
    current_label = 'base'
    logo_index = 1
    
    # Add logo overlays
    for idx, logo in enumerate(logo_overlays):
        logo_file_path = resolved_logo_paths[idx] if idx < len(resolved_logo_paths) else None
        if not logo_file_path:
            continue
        
        # Calculate start and end times relative to trim
        start_value = _resolve_overlay_time(logo.start, logo.startTime, 0.0) or 0.0
        end_value = _resolve_overlay_time(logo.end, logo.endTime, None)
        start_time = max(0.0, start_value - trim_start)
        end_time = end_value
        if end_time is not None:
            end_time = max(0.0, end_time - trim_start)

        enable_clause = f"enable='between(t,{start_time},{end_time if end_time is not None else 1e9})'"
        
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
        start_value = _resolve_overlay_time(text.start, text.startTime, 0.0) or 0.0
        end_value = _resolve_overlay_time(text.end, text.endTime, None)
        start_time = max(0.0, start_value - trim_start)
        end_time = end_value
        if end_time is not None:
            end_time = max(0.0, end_time - trim_start)

        enable_clause = f"enable='between(t,{start_time},{end_time if end_time is not None else 1e9})'"
        
        # Scale font size based on video resolution
        preview_width = 640
        scale_factor = video_width / preview_width
        base_fontsize = text.fontSize or text.fontsize or 24
        scaled_fontsize = round(base_fontsize * scale_factor)
        
        # Get font color (handle alternative field names)
        font_color = _normalize_ffmpeg_color(text.color or text.fontcolor or 'white')
        escaped_text = _escape_drawtext_text(text.text or '')

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
    logo_file_sequence: Optional[List[Optional[str]]] = None,
    music_path: Optional[str] = None,
    music_start: float = 0.0,
    music_end: Optional[float] = None,
    music_volume: float = 1.0,
    source_audio_volume: float = 1.0,
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
        logo_file_sequence: Optional list of logo file paths aligned to overlays by index
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
    logo_file_sequence = logo_file_sequence or []
    
    # Build filter complex
    filter_complex, additional_inputs = build_overlay_filter(
        trim_start=trim_start,
        text_overlays=text_overlays,
        logo_overlays=logo_overlays,
        logo_files=logo_files,
        logo_file_sequence=logo_file_sequence,
        video_width=video_width,
        video_height=video_height,
        brightness=brightness,
        contrast=contrast,
        saturation=saturation
    )
    
    source_duration = float(video_info.get('duration', 0) or 0)
    has_source_audio = bool(video_info.get('has_audio'))
    bounded_source_audio_volume = max(0.0, min(float(source_audio_volume), 2.0))
    source_audio_enabled = has_source_audio and bounded_source_audio_volume > 0.001
    output_duration = trim_duration
    if output_duration is None and source_duration > 0:
        output_duration = max(0.0, source_duration - trim_start)
    if output_duration is not None and output_duration <= 0:
        raise VideoProcessingError("Trim duration is 0 after applying trim start/time range")

    # Build FFmpeg command
    ffmpeg_cmd = [
        'ffmpeg',
        '-ss', str(trim_start),
    ]

    if output_duration is not None:
        ffmpeg_cmd.extend(['-t', str(output_duration)])

    ffmpeg_cmd.extend([
        '-i', input_path,
        *additional_inputs,
    ])

    logo_input_count = len(additional_inputs) // 2
    music_input_index: Optional[int] = None
    if music_path and os.path.exists(music_path):
        music_input_index = 1 + logo_input_count
        ffmpeg_cmd.extend(['-i', music_path])

    filter_complex_audio = filter_complex
    map_audio_args: List[str] = []
    audio_codec_args: List[str] = []

    if music_input_index is not None and output_duration is not None:
        norm_music_start = max(0.0, float(music_start or 0.0))
        norm_music_end = float(music_end) if music_end is not None else (trim_start + output_duration)
        if norm_music_end < norm_music_start:
            norm_music_end = norm_music_start

        music_output_start = max(0.0, norm_music_start - trim_start)
        music_overlap_end = min(output_duration, max(0.0, norm_music_end - trim_start))
        music_active_duration = max(0.0, music_overlap_end - music_output_start)
        music_input_seek = max(0.0, trim_start - norm_music_start)
        bounded_music_volume = max(0.0, min(float(music_volume), 2.0))

        if music_active_duration > 0.001:
            if source_audio_enabled:
                filter_complex_audio += f';[0:a]volume={bounded_source_audio_volume}[srca]'
            else:
                filter_complex_audio += f";anullsrc=channel_layout=stereo:sample_rate=48000,atrim=duration={output_duration},asetpts=N/SR/TB[srca]"

            filter_complex_audio += (
                f";[{music_input_index}:a]atrim=start={music_input_seek}:duration={music_active_duration},"
                f"asetpts=PTS-STARTPTS,volume={bounded_music_volume}[musicclip]"
            )

            if music_output_start > 0:
                delay_ms = int(round(music_output_start * 1000))
                filter_complex_audio += f";[musicclip]adelay={delay_ms}|{delay_ms}[musicaligned]"
            else:
                filter_complex_audio += ';[musicclip]anull[musicaligned]'

            filter_complex_audio += ';[srca][musicaligned]amix=inputs=2:duration=first:dropout_transition=2,aresample=async=1[outa]'
            map_audio_args = ['-map', '[outa]']
            audio_codec_args = ['-c:a', 'aac', '-b:a', '192k']
        elif source_audio_enabled:
            filter_complex_audio += f';[0:a]volume={bounded_source_audio_volume},aresample=async=1[outa]'
            map_audio_args = ['-map', '[outa]']
            audio_codec_args = ['-c:a', 'aac', '-b:a', '192k']
    elif source_audio_enabled:
        filter_complex_audio += f';[0:a]volume={bounded_source_audio_volume},aresample=async=1[outa]'
        map_audio_args = ['-map', '[outa]']
        audio_codec_args = ['-c:a', 'aac', '-b:a', '192k']
    
    ffmpeg_cmd.extend([
        '-filter_complex', filter_complex_audio,
        '-map', '[outv]',
    ])

    if map_audio_args:
        ffmpeg_cmd.extend(map_audio_args)
        ffmpeg_cmd.extend(audio_codec_args)
    else:
        ffmpeg_cmd.append('-an')

    ffmpeg_cmd.extend([
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        '-y',
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
