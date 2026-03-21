"""
FastAPI Server with Background Removal and Video Processing capabilities.

Features:
- Background removal from images (rembg)
- Video metadata extraction (ffprobe)
- Video processing with FFmpeg (trim, adjust, overlays)
"""
import os
import json
import re
import shutil
import asyncio
import math
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

from models.video_process import (
    TextOverlay,
    LogoOverlay,
)
from services.video_processor import (
    get_video_info,
    process_video,
    compress_video,
    extract_audio,
    generate_gif,
    cleanup_file,
    is_ffmpeg_installed,
    is_ffprobe_installed,
    VideoProcessingError,
)
from services.video_deleter import delete_frame_from_video

from services.background_remover import (
    remove_background,
    BackgroundRemovalError,
)


app = FastAPI(title="FastAPI Server", version="1.0.0")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
UPLOAD_DIR = "uploads"
OUTPUT_DIR = "outputs"
DEBUG_MODE = os.environ.get("DEBUG_KEEP_UPLOADS", "false").lower() == "true"
FORCE_LOGGING = True

# Create directories
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def log_debug(message: str, data: any = None):
    """Debug logging helper"""
    print(f"[VIDEO-DEBUG] {message}", data if data else "")


def should_keep_file() -> bool:
    """Check if files should be kept (debug mode)"""
    return DEBUG_MODE


def _is_upload_file(value: Any) -> bool:
    return hasattr(value, "filename") and hasattr(value, "read")


def _safe_filename(filename: Optional[str], fallback: str) -> str:
    base = Path(filename or fallback).name
    sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", base).strip("._")
    return sanitized or fallback


def _parse_form_float(
    form_data: Dict[str, Any],
    key: str,
    default: Optional[float],
    *,
    minimum: Optional[float] = None,
    maximum: Optional[float] = None,
    allow_none: bool = False,
) -> Optional[float]:
    raw_value = form_data.get(key)
    if raw_value in (None, ""):
        if allow_none:
            return None
        return float(default if default is not None else 0.0)

    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"Invalid numeric value for '{key}'")

    if not math.isfinite(value):
        raise HTTPException(status_code=400, detail=f"'{key}' must be a finite number")

    if minimum is not None:
        value = max(minimum, value)
    if maximum is not None:
        value = min(maximum, value)
    return value


def _parse_json_array(form_data: Dict[str, Any], key: str) -> List[Any]:
    raw = form_data.get(key, "[]")
    if raw in (None, ""):
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in '{key}': {exc.msg}")

    if not isinstance(parsed, list):
        raise HTTPException(status_code=400, detail=f"'{key}' must be a JSON array")
    return parsed


# Mount static files for output directory
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")


@app.get("/")
def root():
    return {"message": "Welcome to FastAPI Server"}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/video/ffmpeg-check")
async def check_ffmpeg():
    """
    Check if FFmpeg and FFprobe are installed on the system.
    Required for video processing functionality.
    """
    ffmpeg_ok = is_ffmpeg_installed()
    ffprobe_ok = is_ffprobe_installed()
    
    return {
        "ffmpeg": {
            "installed": ffmpeg_ok,
            "path": shutil.which("ffmpeg") if ffmpeg_ok else None
        },
        "ffprobe": {
            "installed": ffprobe_ok,
            "path": shutil.which("ffprobe") if ffprobe_ok else None
        },
        "video_processing_available": ffmpeg_ok and ffprobe_ok
    }


# =========================
# Background Removal Endpoints
# =========================

@app.post("/remove-bg")
async def remove_bg_endpoint(file: UploadFile = File(...)):
    """
    Remove background from an image.
    
    Returns: Image with transparent background (PNG)
    """
    try:
        input_image = await file.read()
        output_image = remove_background(input_image)
        return Response(content=output_image, media_type="image/png")
    except BackgroundRemovalError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process image: {str(e)}")


# =========================
# Video Processing Endpoints
# =========================

@app.post("/video/info")
async def get_video_metadata(video: UploadFile = File(...)):
    """
    Extract video metadata using ffprobe.
    
    Returns: duration, size, bitrate, format, video codec, resolution, fps
    """
    if not is_ffprobe_installed():
        raise HTTPException(
            status_code=500,
            detail="FFprobe is not installed. Install FFmpeg to enable video processing."
        )
    
    safe_video_name = _safe_filename(video.filename, "video.mp4")
    temp_video_path = os.path.join(UPLOAD_DIR, f"info_{uuid.uuid4().hex}_{safe_video_name}")
    try:
        with open(temp_video_path, "wb") as f:
            content = await video.read()
            f.write(content)
        
        log_debug(f"Video file saved for info extraction: {temp_video_path}")
        info = await get_video_info(temp_video_path)
        return info
        
    except VideoProcessingError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process video: {str(e)}")
    finally:
        if not should_keep_file():
            cleanup_file(temp_video_path)


@app.post("/video/compress")
async def compress_video_endpoint(request: Request, background_tasks: BackgroundTasks):
    """
    Compress video (with optional trim).
    """
    if not is_ffmpeg_installed():
        raise HTTPException(status_code=500, detail="FFmpeg is not installed")

    form_data = await request.form()
    
    # Get video file (prefer "video", fallback to first file)
    video_file = form_data.get("video")
    if not video_file or not _is_upload_file(video_file):
        for key, value in form_data.items():
            if _is_upload_file(value):
                video_file = value
                break
    
    if not video_file:
        raise HTTPException(status_code=400, detail="No video file found")
    
    safe_video_name = _safe_filename(video_file.filename, "video.mp4")
    temp_video_path = os.path.join(UPLOAD_DIR, f"comp_{uuid.uuid4().hex}_{safe_video_name}")
    temp_files = [temp_video_path]
    
    trim_start = _parse_form_float(form_data, "trimStart", 0.0, minimum=0.0)
    trim_duration = _parse_form_float(form_data, "trimDuration", None, minimum=0.1, allow_none=True)
    
    try:
        with open(temp_video_path, "wb") as f:
            content = await video_file.read()
            f.write(content)
        
        output_path = os.path.join(OUTPUT_DIR, f"compressed_{Path(safe_video_name).stem}_{uuid.uuid4().hex}.mp4")
        
        success = await compress_video(
            input_path=temp_video_path,
            output_path=output_path,
            trim_start=trim_start,
            trim_duration=trim_duration
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Compression failed")
        
        background_tasks.add_task(cleanup_file, output_path)
        return FileResponse(path=output_path, media_type="video/mp4", filename=Path(output_path).name)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if not should_keep_file():
            for f in temp_files:
                cleanup_file(f)


@app.post("/video/audio")
async def extract_audio_endpoint(request: Request, background_tasks: BackgroundTasks):
    """
    Extract original audio from video.
    """
    if not is_ffmpeg_installed():
        raise HTTPException(status_code=500, detail="FFmpeg is not installed")

    form_data = await request.form()
    
    video_file = form_data.get("video")
    if not video_file or not _is_upload_file(video_file):
        for key, value in form_data.items():
            if _is_upload_file(value):
                video_file = value
                break
    
    if not video_file:
        raise HTTPException(status_code=400, detail="No video file found")
    
    safe_video_name = _safe_filename(video_file.filename, "video.mp4")
    temp_video_path = os.path.join(UPLOAD_DIR, f"audio_{uuid.uuid4().hex}_{safe_video_name}")
    temp_files = [temp_video_path]
    
    try:
        with open(temp_video_path, "wb") as f:
            content = await video_file.read()
            f.write(content)
        
        output_path = os.path.join(OUTPUT_DIR, f"{Path(safe_video_name).stem}_audio_{uuid.uuid4().hex}.m4a")
        
        success = await extract_audio(temp_video_path, output_path)
        
        if not success:
            raise HTTPException(status_code=500, detail="Audio extraction failed")
        
        background_tasks.add_task(cleanup_file, output_path)
        return FileResponse(path=output_path, media_type="audio/mp4", filename=Path(output_path).name)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if not should_keep_file():
            for f in temp_files:
                cleanup_file(f)


@app.post("/video/gif")
async def generate_gif_endpoint(request: Request, background_tasks: BackgroundTasks):
    """
    Generate GIF from video (first 10s default).
    """
    if not is_ffmpeg_installed():
        raise HTTPException(status_code=500, detail="FFmpeg is not installed")

    form_data = await request.form()
    
    video_file = form_data.get("video")
    if not video_file or not _is_upload_file(video_file):
        for key, value in form_data.items():
            if _is_upload_file(value):
                video_file = value
                break
    
    if not video_file:
        raise HTTPException(status_code=400, detail="No video file found")
    
    safe_video_name = _safe_filename(video_file.filename, "video.mp4")
    temp_video_path = os.path.join(UPLOAD_DIR, f"gif_{uuid.uuid4().hex}_{safe_video_name}")
    temp_files = [temp_video_path]
    
    start_time = _parse_form_float(form_data, "startTime", 0.0, minimum=0.0)
    gif_duration = _parse_form_float(form_data, "duration", 10.0, minimum=1.0, maximum=30.0)
    gif_width = int(_parse_form_float(form_data, "width", 640, minimum=320, maximum=1280) or 640)
    
    try:
        with open(temp_video_path, "wb") as f:
            content = await video_file.read()
            f.write(content)
        
        output_path = os.path.join(OUTPUT_DIR, f"{Path(safe_video_name).stem}_gif_{uuid.uuid4().hex}.gif")
        
        success = await generate_gif(
            temp_video_path,
            output_path,
            start_time=start_time,
            duration=gif_duration,
            width=gif_width
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="GIF generation failed")
        
        background_tasks.add_task(cleanup_file, output_path)
        return FileResponse(path=output_path, media_type="image/gif", filename=Path(output_path).name)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if not should_keep_file():
            for f in temp_files:
                cleanup_file(f)


@app.post("/video/process")
async def process_video_endpoint(request: Request, background_tasks: BackgroundTasks):
    """
    Process video with trim, adjustments, overlays, and optional music track.
    Supports dynamic logo fields ('logo_0', 'logo_1', ...) plus one optional 'music' file.
    """
    if not is_ffmpeg_installed():
        raise HTTPException(status_code=500, detail="FFmpeg is not installed")

    log_debug("=" * 60)
    log_debug("VIDEO PROCESS ENDPOINT")
    log_debug("=" * 60)

    # Parse multipart form data manually
    form_data = await request.form()

    log_debug(f"Form data keys: {list(form_data.keys())}")
    for key, value in form_data.items():
        log_debug(f"Key: {key}, Type: {type(value)}, Filename: {getattr(value, 'filename', None)}")

    # Video file: prefer explicit "video" key, then fallback to first non-logo/non-music file
    video_file = form_data.get("video")
    video_filename = getattr(video_file, "filename", None) if video_file else None
    if not video_filename:
        video_file = None
        for key, value in form_data.items():
            if _is_upload_file(value) and not key.startswith('logo_') and key != 'music' and not key.startswith('music_'):
                video_file = value
                video_filename = value.filename
                break

    if not video_file:
        log_debug("No video file found!")
        raise HTTPException(status_code=400, detail="No video file found in request")

    log_debug(f"Video file: {video_filename}")

    # Get other parameters
    trim_start = _parse_form_float(form_data, "trimStart", 0.0, minimum=0.0)
    trim_duration = _parse_form_float(form_data, "trimDuration", None, minimum=0.1, allow_none=True)
    brightness_val = _parse_form_float(form_data, "brightness", 0.0, minimum=-1.0, maximum=1.0)
    contrast_val = _parse_form_float(form_data, "contrast", 1.0, minimum=0.0, maximum=4.0)
    saturation_val = _parse_form_float(form_data, "saturation", 1.0, minimum=0.0, maximum=4.0)
    music_start = _parse_form_float(form_data, "musicStart", 0.0, minimum=0.0)
    music_end = _parse_form_float(form_data, "musicEnd", None, minimum=0.0, allow_none=True)
    music_volume = _parse_form_float(form_data, "musicVolume", 1.0, minimum=0.0, maximum=2.0)
    source_audio_volume = _parse_form_float(form_data, "sourceAudioVolume", 1.0, minimum=0.0, maximum=2.0)
    music_tracks_raw = _parse_json_array(form_data, "musicTracks")
    if music_end is not None and music_end < music_start:
        music_end = music_start

    # Parse overlays
    text_overlays_raw = _parse_json_array(form_data, "textOverlays")
    logo_overlays_raw = _parse_json_array(form_data, "logoOverlays")

    text_overlays: List[TextOverlay] = []
    for index, item in enumerate(text_overlays_raw):
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail=f"textOverlays[{index}] must be an object")
        try:
            text_overlays.append(TextOverlay(**item))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid textOverlays[{index}]: {str(exc)}")

    logo_overlays: List[LogoOverlay] = []
    for index, item in enumerate(logo_overlays_raw):
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail=f"logoOverlays[{index}] must be an object")
        try:
            logo_overlays.append(LogoOverlay(**item))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid logoOverlays[{index}]: {str(exc)}")

    log_debug(f"Text overlays: {len(text_overlays)}")
    log_debug(f"Logo overlays: {len(logo_overlays)}")

    # Find logo files (logo_0, logo_1, etc.)
    logo_files_by_filename: Dict[str, str] = {}
    logo_files_by_index: Dict[int, str] = {}
    saved_logo_paths: List[str] = []

    for key, value in form_data.items():
        if not (_is_upload_file(value) and key.startswith("logo_")):
            continue
        match = re.match(r"^logo_(\d+)$", key)
        if not match:
            continue

        idx = int(match.group(1))
        safe_logo_name = _safe_filename(getattr(value, "filename", None), f"logo_{idx}.png")
        logo_path = os.path.join(UPLOAD_DIR, f"logo_{idx}_{uuid.uuid4().hex}_{safe_logo_name}")
        with open(logo_path, "wb") as f:
            content = await value.read()
            f.write(content)

        logo_files_by_index[idx] = logo_path
        saved_logo_paths.append(logo_path)

        overlay_key = f"logoOverlay_{idx}"
        overlay_config_str = form_data.get(overlay_key, "{}") or "{}"
        try:
            overlay_config = json.loads(overlay_config_str)
        except json.JSONDecodeError:
            overlay_config = {}
            log_debug(f"Failed to parse {overlay_key}")

        if isinstance(overlay_config, dict):
            filename_key = overlay_config.get("filename")
            if isinstance(filename_key, str) and filename_key:
                logo_files_by_filename[filename_key] = logo_path
                log_debug(f"Saved logo: {logo_path} -> {filename_key}")

    logo_file_sequence: List[Optional[str]] = []
    for index, overlay in enumerate(logo_overlays):
        logo_file_sequence.append(
            logo_files_by_index.get(index) or logo_files_by_filename.get(overlay.filename)
        )

    log_debug(f"Logo files found by index: {logo_files_by_index}")
    log_debug(f"Logo files found by filename: {logo_files_by_filename}")

    if len(logo_overlays) > 0 and not any(logo_file_sequence):
        log_debug("Warning: Logo overlays present but no logo files found!")

    # Save video and optional music track
    safe_video_name = _safe_filename(video_filename, "video.mp4")
    temp_video_path = os.path.join(UPLOAD_DIR, f"proc_{uuid.uuid4().hex}_{safe_video_name}")
    temp_files_to_cleanup = [temp_video_path, *saved_logo_paths]
    music_file = form_data.get("music")
    music_file_path: Optional[str] = None
    if _is_upload_file(music_file) and getattr(music_file, "filename", None):
        safe_music_name = _safe_filename(music_file.filename, "music.mp3")
        music_file_path = os.path.join(UPLOAD_DIR, f"music_{uuid.uuid4().hex}_{safe_music_name}")
        temp_files_to_cleanup.append(music_file_path)

    parsed_music_tracks: List[Dict[str, Any]] = []
    for index, item in enumerate(music_tracks_raw):
        if not isinstance(item, dict):
            continue
        file_key = item.get("fileKey") or f"music_{index}"
        music_upload = form_data.get(file_key)
        if not _is_upload_file(music_upload):
            continue
        safe_name = _safe_filename(getattr(music_upload, "filename", None), f"{file_key}.mp3")
        track_path = os.path.join(UPLOAD_DIR, f"{file_key}_{uuid.uuid4().hex}_{safe_name}")
        temp_files_to_cleanup.append(track_path)
        with open(track_path, "wb") as f:
            content = await music_upload.read()
            f.write(content)
        track_start = _parse_form_float(item, "startTime", 0.0, minimum=0.0)
        track_end = _parse_form_float(item, "endTime", None, minimum=0.0, allow_none=True)
        track_volume = _parse_form_float(item, "volume", 1.0, minimum=0.0, maximum=2.0)
        if track_end is not None and track_end < track_start:
            track_end = track_start
        parsed_music_tracks.append({
            "path": track_path,
            "start": track_start,
            "end": track_end,
            "volume": track_volume,
        })

    try:
        with open(temp_video_path, "wb") as f:
            content = await video_file.read()
            f.write(content)

        if music_file_path and music_file:
            with open(music_file_path, "wb") as f:
                content = await music_file.read()
                f.write(content)

        output_path = os.path.join(OUTPUT_DIR, f"processed_{Path(safe_video_name).stem}_{uuid.uuid4().hex}.mp4")

        log_debug(f"Starting FFmpeg processing...")
        log_debug(f"Output path: {output_path}")

        success = await process_video(
            input_path=temp_video_path,
            output_path=output_path,
            trim_start=trim_start,
            trim_duration=trim_duration,
            brightness=brightness_val,
            contrast=contrast_val,
            saturation=saturation_val,
            text_overlays=text_overlays,
            logo_overlays=logo_overlays,
            logo_files=logo_files_by_filename,
            logo_file_sequence=logo_file_sequence,
            music_tracks=parsed_music_tracks,
            music_path=music_file_path,
            music_start=music_start,
            music_end=music_end,
            music_volume=music_volume,
            source_audio_volume=source_audio_volume,
            debug_mode=DEBUG_MODE
        )

        if not success:
            raise HTTPException(status_code=500, detail="Video processing failed")

        log_debug(f"SUCCESS: Video processed -> {output_path}")

        # Schedule cleanup of output file after response is sent
        background_tasks.add_task(cleanup_file, output_path)

        return FileResponse(path=output_path, media_type="video/mp4", filename=Path(output_path).name)

    except HTTPException:
        raise
    except Exception as e:
        log_debug(f"ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if not should_keep_file():
            for f in temp_files_to_cleanup:
                cleanup_file(f)

@app.post("/video/delete-frame")
async def delete_frame_endpoint(request: Request, background_tasks: BackgroundTasks):
    """
    Delete a specific frame/time slice from video by cutting that range out.
    """
    if not is_ffmpeg_installed():
        raise HTTPException(status_code=500, detail="FFmpeg is not installed")

    form_data = await request.form()
    
    video_file = form_data.get("video")
    if not video_file or not _is_upload_file(video_file):
        raise HTTPException(status_code=400, detail="No video file found")
    
    frame_time = _parse_form_float(form_data, "frameTime", None, minimum=0.0)
    frame_duration = _parse_form_float(form_data, "frameDuration", 0.033, minimum=0.01, maximum=5.0)
    delete_radius = _parse_form_float(form_data, "deleteRadius", 0.0, minimum=0.0)
    
    if frame_time is None:
        raise HTTPException(status_code=400, detail="frameTime parameter required")
    
    safe_video_name = _safe_filename(video_file.filename, "video.mp4")
    temp_video_path = os.path.join(UPLOAD_DIR, f"del_{uuid.uuid4().hex}_{safe_video_name}")
    temp_files = [temp_video_path]
    
    try:
        with open(temp_video_path, "wb") as f:
            content = await video_file.read()
            f.write(content)
        
        output_path = os.path.join(OUTPUT_DIR, f"{Path(safe_video_name).stem}_frame_deleted_{uuid.uuid4().hex}.mp4")
        
        await delete_frame_from_video(
            temp_video_path,
            frame_time,
            frame_duration,
            output_path,
            delete_radius
        )
        
        background_tasks.add_task(cleanup_file, output_path)
        return FileResponse(path=output_path, media_type="video/mp4", filename=Path(output_path).name)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if not should_keep_file():
            for f in temp_files:
                cleanup_file(f)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
