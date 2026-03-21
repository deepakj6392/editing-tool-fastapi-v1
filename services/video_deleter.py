import asyncio
import os
import uuid
from pathlib import Path
from typing import List

from .video_processor import VideoProcessingError, cleanup_file, get_video_info

async def delete_frame_from_video(
    input_path: str,
    frame_time: float,
    frame_duration: float = 0.033,  # ~30fps
    output_path: str = None,
    delete_radius: float = 0.0
) -> str:
    """
    Delete a specific frame/time slice from video by cutting it out.
    
    Args:
        input_path: Path to input video
        frame_time: Time position of frame to delete (seconds)
        frame_duration: Duration to delete around frame (seconds)
        output_path: Optional output path
        delete_radius: Additional padding before/after frame (seconds)
        
    Returns:
        Path to processed video
    """
    if not os.path.exists(input_path):
        raise VideoProcessingError(f"Input file not found: {input_path}")
    
    if output_path is None:
        stem = Path(input_path).stem
        output_path = f"{stem}_frame_deleted_{uuid.uuid4().hex[:8]}.mp4"
    
    # Calculate segment to cut out
    start_time = max(0, frame_time - frame_duration/2 - delete_radius)
    probe = await get_video_info(input_path)
    duration = float(probe.get('duration', 0.0) or 0.0)
    has_audio = bool(probe.get('has_audio'))
    end_time = min(duration, start_time + frame_duration + 2 * delete_radius)

    if duration <= 0:
        raise VideoProcessingError("Invalid input duration")
    if end_time <= start_time:
        raise VideoProcessingError("Delete range is empty")

    epsilon = 1e-6
    filter_parts = []
    map_args = ['-map', '[vout]']
    audio_codec_args = ['-an']

    # If cut starts at beginning, keep tail only.
    if start_time <= epsilon:
        filter_parts.append(f"[0:v]trim=start={end_time:.6f},setpts=PTS-STARTPTS[vout]")
        if has_audio:
            filter_parts.append(f"[0:a]atrim=start={end_time:.6f},asetpts=PTS-STARTPTS[aout]")
            map_args += ['-map', '[aout]']
            audio_codec_args = ['-c:a', 'aac', '-b:a', '192k']
    # If cut ends at (or beyond) file end, keep head only.
    elif end_time >= duration - epsilon:
        filter_parts.append(f"[0:v]trim=start=0:end={start_time:.6f},setpts=PTS-STARTPTS[vout]")
        if has_audio:
            filter_parts.append(f"[0:a]atrim=start=0:end={start_time:.6f},asetpts=PTS-STARTPTS[aout]")
            map_args += ['-map', '[aout]']
            audio_codec_args = ['-c:a', 'aac', '-b:a', '192k']
    else:
        # Cut from middle: concat head + tail.
        filter_parts.extend([
            f"[0:v]trim=start=0:end={start_time:.6f},setpts=PTS-STARTPTS[v0]",
            f"[0:v]trim=start={end_time:.6f},setpts=PTS-STARTPTS[v1]",
            "[v0][v1]concat=n=2:v=1:a=0[vout]",
        ])
        if has_audio:
            filter_parts.extend([
                f"[0:a]atrim=start=0:end={start_time:.6f},asetpts=PTS-STARTPTS[a0]",
                f"[0:a]atrim=start={end_time:.6f},asetpts=PTS-STARTPTS[a1]",
                "[a0][a1]concat=n=2:v=0:a=1[aout]",
            ])
            map_args += ['-map', '[aout]']
            audio_codec_args = ['-c:a', 'aac', '-b:a', '192k']

    filter_complex = ';'.join(filter_parts)

    ffmpeg_cmd = [
        'ffmpeg',
        '-i', input_path,
        '-filter_complex', filter_complex,
        *map_args,
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        '-pix_fmt', 'yuv420p',
        '-movflags', '+faststart',
        *audio_codec_args,
        '-y', output_path
    ]
    
    try:
        print(f"Executing FFmpeg command: {' '.join(ffmpeg_cmd)}")
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            print(f"FFmpeg stdout: {stdout.decode()}")
            print(f"FFmpeg stderr: {stderr.decode()}")
            raise VideoProcessingError(f"FFmpeg failed to delete frame: {stderr.decode()}")
        
        if not os.path.exists(output_path):
            raise VideoProcessingError("Output file not created")
        
        print(f"Frame deletion successful. Output: {output_path} (size: {os.path.getsize(output_path)} bytes)")
        return output_path
        
    except Exception as e:
        raise VideoProcessingError(f"Failed to delete frames: {str(e)}")


async def delete_multiple_frames(
    input_path: str,
    frame_times: List[float],
    frame_duration: float = 0.033,
    output_path: str = None
) -> str:
    """
    Delete multiple frames from video.
    """
    if not os.path.exists(input_path):
        raise VideoProcessingError(f"Input file not found: {input_path}")
    
    if output_path is None:
        stem = Path(input_path).stem
        output_path = f"{stem}_frames_deleted_{uuid.uuid4().hex[:8]}.mp4"
    
    filters = []
    for t in frame_times:
        start = max(0, t - frame_duration/2)
        end = start + frame_duration
        filters.append(
            "drawbox="
            "x=0:y=0:w=iw:h=ih:color=black:t=fill:"
            f"enable='between(t,{start:.6f},{end:.6f})'"
        )

    # Chain drawbox filters so each requested frame window is blacked out.
    video_filter = ",".join(filters)
    
    ffmpeg_cmd = [
        'ffmpeg',
        '-i', input_path,
        '-vf', video_filter,
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '23',
        '-c:a', 'copy',
        '-y', output_path
    ]
    
    try:
        print(f"Executing multiple frames FFmpeg: {' '.join(ffmpeg_cmd)}")
        process = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            raise VideoProcessingError(f"FFmpeg failed: {stderr.decode()}")
        
        return output_path
        
    except Exception as e:
        raise VideoProcessingError(f"Failed to delete frames: {str(e)}")
