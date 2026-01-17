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
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles

from models.video_process import (
    TextOverlay,
    LogoOverlay,
    VideoInfoResponse,
)
from services.video_processor import (
    get_video_info,
    process_video,
    cleanup_file,
    is_ffmpeg_installed,
    is_ffprobe_installed,
    VideoProcessingError,
)
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
    
    temp_video_path = os.path.join(UPLOAD_DIR, f"info_{video.filename}")
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


@app.post("/video/process")
async def process_video_endpoint(
    video: UploadFile = File(..., description="Video file"),
    trimStart: str = Form("0", description="Trim start time"),
    trimDuration: Optional[str] = Form(None, description="Trim duration"),
    brightness: str = Form("0", description="Brightness"),
    contrast: str = Form("1", description="Contrast"),
    saturation: str = Form("1", description="Saturation"),
    textOverlays: str = Form("[]", description="Text overlays JSON"),
    logoOverlays: str = Form("[]", description="Logo overlays JSON"),
):
    """
    Process video with trim, brightness, contrast, saturation, text/logo overlays.
    
    Note: For logo files, include them in the form data with field names like:
    - logo_0, logo_1, etc. for the actual image files
    - logoOverlay_0, logoOverlay_1, etc. for the corresponding overlay configs
    """
    if not is_ffmpeg_installed():
        raise HTTPException(
            status_code=500,
            detail="FFmpeg is not installed."
        )
    
    log_debug("=" * 60)
    log_debug("VIDEO PROCESS ENDPOINT")
    log_debug("=" * 60)
    log_debug(f"Video file: {video.filename}")
    log_debug(f"Video content_type: {video.content_type}")
    
    # Convert string parameters to float
    try:
        trim_start = float(trimStart) if trimStart else 0
        trim_duration = float(trimDuration) if trimDuration else None
        brightness_val = float(brightness) if brightness else 0
        contrast_val = float(contrast) if contrast else 1
        saturation_val = float(saturation) if saturation else 1
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid numeric parameter: {str(e)}")
    
    # Parse overlay configurations
    try:
        text_overlays_raw = json.loads(textOverlays) if textOverlays else []
        logo_overlays_raw = json.loads(logoOverlays) if logoOverlays else []
        
        text_overlays = [TextOverlay(**t) for t in text_overlays_raw]
        logo_overlays = [LogoOverlay(**l) for l in logo_overlays_raw]
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in overlays: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid overlay data: {str(e)}")
    
    log_debug(f"Parameters: trimStart={trim_start}, trimDuration={trim_duration}")
    log_debug(f"Adjustments: brightness={brightness_val}, contrast={contrast_val}, saturation={saturation_val}")
    log_debug(f"Text overlays: {len(text_overlays)}")
    log_debug(f"Logo overlays: {len(logo_overlays)}")
    
    # Build logo files map - initially empty
    logo_files: Dict[str, str] = {}
    
    # Save main video file
    temp_video_path = os.path.join(UPLOAD_DIR, f"proc_{video.filename}")
    temp_files_to_cleanup = [temp_video_path]
    
    try:
        # Save main video
        with open(temp_video_path, "wb") as f:
            content = await video.read()
            f.write(content)
        
        log_debug(f"Main video saved: {temp_video_path}")
        log_debug(f"Logo files map: {logo_files}")
        
        # Generate output path
        output_filename = f"processed_{Path(video.filename).stem}_{int(asyncio.get_event_loop().time() * 1000)}.mp4"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        log_debug(f"Starting FFmpeg processing...")
        log_debug(f"Output path: {output_path}")
        
        # Process video
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
            logo_files=logo_files,
            debug_mode=DEBUG_MODE
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Video processing failed")
        
        log_debug(f"SUCCESS: Video processed -> {output_path}")
        
        # Return video file
        return FileResponse(
            path=output_path,
            media_type="video/mp4",
            filename=output_filename
        )
        
    except HTTPException:
        raise
    except VideoProcessingError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        log_debug(f"ERROR: Processing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    finally:
        # Cleanup temporary files
        if not should_keep_file():
            for file_path in temp_files_to_cleanup:
                cleanup_file(file_path)
            log_debug(f"Cleaned up {len(temp_files_to_cleanup)} temp files")


# =========================
# Alternative endpoint with raw form data parsing
# =========================

@app.post("/video/process-alt")
async def process_video_endpoint_alt(request: Request):
    """
    Alternative endpoint - parses ALL form data including dynamic logo file fields.
    Use this if logo files are sent with field names like 'logo_0', 'logo_1', etc.
    """
    if not is_ffmpeg_installed():
        raise HTTPException(status_code=500, detail="FFmpeg is not installed")
    
    log_debug("=" * 60)
    log_debug("VIDEO PROCESS ALT ENDPOINT (Raw Form Data)")
    log_debug("=" * 60)
    
    # Parse multipart form data manually
    form_data = await request.form()
    
    # Find video file (first UploadFile that's not a logo)
    video_file = None
    video_filename = None
    
    for key, value in form_data.items():
        if isinstance(value, UploadFile) and not key.startswith('logo_'):
            video_file = value
            video_filename = value.filename
            break
    
    if not video_file:
        log_debug("No video file found!")
        raise HTTPException(status_code=400, detail="No video file found in request")
    
    log_debug(f"Video file: {video_filename}")
    
    # Get other parameters
    try:
        trim_start = float(form_data.get("trimStart", 0) or 0)
        trim_duration = float(form_data.get("trimDuration", 0) or 0) if form_data.get("trimDuration") else None
        brightness_val = float(form_data.get("brightness", 0) or 0)
        contrast_val = float(form_data.get("contrast", 1) or 1)
        saturation_val = float(form_data.get("saturation", 1) or 1)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid parameter: {str(e)}")
    
    # Parse overlays
    try:
        text_overlays_raw = json.loads(form_data.get("textOverlays", "[]") or "[]")
        logo_overlays_raw = json.loads(form_data.get("logoOverlays", "[]") or "[]")
        text_overlays = [TextOverlay(**t) for t in text_overlays_raw]
        logo_overlays = [LogoOverlay(**l) for l in logo_overlays_raw]
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid overlay JSON: {str(e)}")
    
    log_debug(f"Text overlays: {len(text_overlays)}")
    log_debug(f"Logo overlays: {len(logo_overlays)}")
    
    # Find logo files (logo_0, logo_1, etc.)
    logo_files: Dict[str, str] = {}
    logo_pattern = re.compile(r'^logo_(\d+)$')
    
    for key, value in form_data.items():
        if isinstance(value, UploadFile):
            match = logo_pattern.match(key)
            if match:
                idx = int(match.group(1))
                overlay_key = f"logoOverlay_{idx}"
                overlay_config_str = form_data.get(overlay_key, "{}") or "{}"
                
                try:
                    overlay_config = json.loads(overlay_config_str)
                    if overlay_config and "filename" in overlay_config:
                        logo_path = os.path.join(UPLOAD_DIR, f"logo_{idx}_{value.filename}")
                        with open(logo_path, "wb") as f:
                            content = await value.read()
                            f.write(content)
                        logo_files[overlay_config["filename"]] = logo_path
                        log_debug(f"Saved logo: {logo_path} -> {overlay_config['filename']}")
                except json.JSONDecodeError:
                    log_debug(f"Failed to parse {overlay_key}")
    
    log_debug(f"Logo files found: {logo_files}")
    
    if len(logo_overlays) > 0 and len(logo_files) == 0:
        log_debug("Warning: Logo overlays present but no logo files found!")
    
    # Save video and process
    temp_video_path = os.path.join(UPLOAD_DIR, f"proc_{video_filename}")
    temp_files_to_cleanup = [temp_video_path] + list(logo_files.values())
    
    try:
        with open(temp_video_path, "wb") as f:
            content = await video_file.read()
            f.write(content)
        
        output_path = os.path.join(OUTPUT_DIR, f"processed_{Path(video_filename).stem}_{int(asyncio.get_event_loop().time() * 1000)}.mp4")
        
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
            logo_files=logo_files,
            debug_mode=DEBUG_MODE
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="Video processing failed")
        
        log_debug(f"SUCCESS: Video processed -> {output_path}")
        
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

