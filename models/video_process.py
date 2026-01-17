"""
Pydantic models for video processing API.
Defines request/response schemas for video trim, adjust, and overlay operations.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from enum import Enum


class TextOverlay(BaseModel):
    """Text overlay configuration"""
    text: str = Field(..., description="Text to display")
    x: float = Field(default=50.0, ge=0, le=100, description="X position as percentage of video width (0-100)")
    y: float = Field(default=50.0, ge=0, le=100, description="Y position as percentage of video height (0-100)")
    start: Optional[float] = Field(default=None, ge=0, description="Start time in seconds")
    end: Optional[float] = Field(default=None, ge=0, description="End time in seconds")
    startTime: Optional[float] = Field(default=None, ge=0, alias="startTime", description="Start time in seconds (alternative)")
    endTime: Optional[float] = Field(default=None, ge=0, alias="endTime", description="End time in seconds (alternative)")
    fontsize: Optional[int] = Field(default=24, ge=1, description="Font size in pixels")
    fontSize: Optional[int] = Field(default=None, alias="fontSize", description="Font size (alternative)")
    fontcolor: Optional[str] = Field(default="white", description="Font color (e.g., 'white', '#FF0000', 'red')")
    color: Optional[str] = Field(default=None, description="Font color (alternative)")

    class Config:
        populate_by_name = True


class LogoOverlay(BaseModel):
    """Logo overlay configuration"""
    filename: str = Field(..., description="Filename of the uploaded logo image")
    x: float = Field(default=50.0, ge=0, le=100, description="X position as percentage of video width (0-100)")
    y: float = Field(default=50.0, ge=0, le=100, description="Y position as percentage of video height (0-100)")
    width: Optional[int] = Field(default=100, ge=1, description="Width of the logo in pixels")
    height: Optional[int] = Field(default=100, ge=1, description="Height of the logo in pixels")
    start: Optional[float] = Field(default=None, ge=0, description="Start time in seconds")
    end: Optional[float] = Field(default=None, ge=0, description="End time in seconds")
    startTime: Optional[float] = Field(default=None, ge=0, alias="startTime", description="Start time in seconds (alternative)")
    endTime: Optional[float] = Field(default=None, ge=0, alias="endTime", description="End time in seconds (alternative)")

    class Config:
        populate_by_name = True


class VideoTrimParams(BaseModel):
    """Video trimming parameters"""
    trimStart: float = Field(default=0.0, ge=0, description="Start time for trimming in seconds")
    trimDuration: Optional[float] = Field(default=None, ge=0, description="Duration to keep from trimStart (if omitted, keeps until end)")

    class Config:
        populate_by_name = True


class VideoAdjustParams(BaseModel):
    """Video adjustment parameters (brightness, contrast, saturation)"""
    brightness: float = Field(default=0.0, ge=-1, le=1, description="Brightness adjustment (-1 to 1)")
    contrast: float = Field(default=1.0, ge=0, le=4, description="Contrast adjustment (0 to 4)")
    saturation: float = Field(default=1.0, ge=0, le=4, description="Saturation adjustment (0 to 4)")

    class Config:
        populate_by_name = True


class VideoProcessRequest(BaseModel):
    """Combined request model for video processing"""
    # Trim parameters
    trimStart: float = Field(default=0.0, ge=0, alias="trimStart", description="Start time for trimming in seconds")
    trimDuration: Optional[float] = Field(default=None, ge=0, alias="trimDuration", description="Duration to keep from trimStart")
    
    # Adjustment parameters
    brightness: float = Field(default=0.0, ge=-1, le=1, alias="brightness", description="Brightness adjustment (-1 to 1)")
    contrast: float = Field(default=1.0, ge=0, le=4, alias="contrast", description="Contrast adjustment (0 to 4)")
    saturation: float = Field(default=1.0, ge=0, le=4, alias="saturation", description="Saturation adjustment (0 to 4)")
    
    # Overlay parameters (passed as JSON strings in form data)
    textOverlays: str = Field(default="[]", description="JSON-encoded array of text overlays")
    logoOverlays: str = Field(default="[]", description="JSON-encoded array of logo overlays")

    class Config:
        populate_by_name = True


class VideoInfoResponse(BaseModel):
    """Video metadata response"""
    duration: float = Field(..., description="Duration in seconds")
    size: int = Field(..., description="File size in bytes")
    bitrate: int = Field(..., description="Bitrate in bps")
    format: str = Field(..., description="Format name")
    video: dict = Field(..., description="Video stream details")
    timestamp: str = Field(default_factory=lambda: str(__import__('datetime').datetime.now().isoformat()))


class VideoStreamInfo(BaseModel):
    """Video stream metadata"""
    codec: str = Field(..., description="Video codec name")
    width: int = Field(..., description="Video width in pixels")
    height: int = Field(..., description="Video height in pixels")
    fps: float = Field(..., description="Frames per second")
    aspect_ratio: str = Field(..., description="Display aspect ratio")


class ProcessStatus(BaseModel):
    """Processing status response"""
    status: str = Field(..., description="Processing status: success, error, processing")
    message: str = Field(..., description="Status message")
    output_path: Optional[str] = Field(default=None, description="Path to processed video")
    debug_mode: bool = Field(default=False, description="Whether debug mode is enabled")

