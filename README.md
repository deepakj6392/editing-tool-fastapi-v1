# FastAPI Server with Background Removal and Video Processing

A FastAPI server with image background removal and video processing capabilities using FFmpeg.

## 🚀 Quick Start

Run the project with these commands:

```bash
cd fastapi_backend
source venv/bin/activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Access the server:**
- API URL: http://localhost:8000
- Swagger Docs: http://localhost:8000/docs

## Prerequisites

### Required Software
- **Python 3.12** (Required - Python 3.14 is not supported by rembg)
- **Homebrew** (for macOS users, to install Python 3.12 and FFmpeg)
- **FFmpeg** (required for video processing)

### Check Your Python Version
```bash
python3 --version
```

If you have Python 3.14 or higher and need Python 3.12:

**macOS with Homebrew:**
```bash
# Install Python 3.12 if not already installed
brew install python@3.12

# Verify installation
python3.12 --version
```

**Install FFmpeg (required for video processing):**
```bash
brew install ffmpeg

# Verify installation
ffmpeg -version
ffprobe -version
```

## Installation Steps

### 1. Navigate to the project directory
```bash
cd fastapi_backend
```

### 2. Create virtual environment with Python 3.12
```bash
# Using Python 3.12 directly (recommended)
python3.12 -m venv venv

# OR if using pyenv
pyenv local 3.12
python -m venv venv
```

### 3. Activate virtual environment
```bash
# macOS/Linux
source venv/bin/activate

# Windows (Command Prompt)
venv\Scripts\activate

# Windows (PowerShell)
venv\Scripts\Activate.ps1
```

### 4. Upgrade pip
```bash
pip install --upgrade pip
```

### 5. Install dependencies
```bash
pip install -r requirements.txt
```

### 6. Run the server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Alternative run command:**
```bash
python main.py
```

### 7. Verify the server is running
Open your browser and navigate to:
- **API URL**: http://localhost:8000
- **Swagger Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Available Endpoints

### Background Removal
| Method | Endpoint | Description | Request Body |
|--------|----------|-------------|--------------|
| POST | `/remove-bg` | Remove image background | `file`: Image file (PNG, JPG, etc.) |

### FFmpeg Check
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/video/ffmpeg-check` | Check if FFmpeg/FFprobe are installed |

### Video Processing
| Method | Endpoint | Description | Request Body |
|--------|----------|-------------|--------------|
| POST | `/video/info` | Get video metadata (duration, resolution, fps) | `video`: Video file |
| POST | `/video/process` | Process video (trim, adjust, overlay) | `video`, `trimStart`, `trimDuration`, `brightness`, `contrast`, `saturation`, `textOverlays`, `logoOverlays`, `files` |

## Video Processing API Details

### Check FFmpeg Installation
```bash
curl http://localhost:8000/video/ffmpeg-check
```

Response:
```json
{
  "ffmpeg": {
    "installed": true,
    "path": "/opt/homebrew/bin/ffmpeg"
  },
  "ffprobe": {
    "installed": true,
    "path": "/opt/homebrew/bin/ffprobe"
  },
  "video_processing_available": true
}
```

### Get Video Info
```bash
curl -X POST -F "video=@video.mp4" http://localhost:8000/video/info
```

Response:
```json
{
  "duration": 120.5,
  "size": 5242880,
  "bitrate": 1000000,
  "format": "mp4",
  "video": {
    "codec": "h264",
    "width": 1920,
    "height": 1080,
    "fps": 30.0,
    "aspect_ratio": "16:9"
  },
  "timestamp": "2024-01-01T00:00:00.000000"
}
```

### Process Video (cURL Example)

**Basic trimming:**
```bash
curl -X POST \
  -F "video=@input.mp4" \
  -F "trimStart=10" \
  -F "trimDuration=30" \
  -F "output.mp4" \
  http://localhost:8000/video/process
```

**With brightness, contrast, and saturation adjustment:**
```bash
curl -X POST \
  -F "video=@input.mp4" \
  -F "trimStart=0" \
  -F "brightness=0.1" \
  -F "contrast=1.2" \
  -F "saturation=1.1" \
  http://localhost:8000/video/process
```

**With text overlays:**
```bash
curl -X POST \
  -F "video=@input.mp4" \
  -F "trimStart=0" \
  -F 'textOverlays=[{"text":"Hello World","x":50,"y":50,"start":0,"end":10,"fontsize":24,"fontcolor":"white"}]' \
  http://localhost:8000/video/process
```

**With logo overlay:**
```bash
curl -X POST \
  -F "video=@input.mp4" \
  -F "logoFiles=@logo.png" \
  -F 'logoOverlays=[{"filename":"logo.png","x":90,"y":90,"width":100,"height":100,"start":0,"end":10}]' \
  http://localhost:8000/video/process
```

**Full example with all features:**
```bash
curl -X POST \
  -F "video=@input.mp4" \
  -F "trimStart=5" \
  -F "trimDuration=60" \
  -F "brightness=0.05" \
  -F "contrast=1.1" \
  -F "saturation=1.2" \
  -F 'textOverlays=[{"text":"My Video","x":50,"y":10,"start":0,"end":30,"fontsize":36,"fontcolor":"white"}]' \
  -F "logoFiles=@logo.png" \
  -F 'logoOverlays=[{"filename":"logo.png","x":85,"y":85,"width":80,"height":80,"start":0}]' \
  http://localhost:8000/video/process
```

### Process Video Parameters

| Parameter | Type | Default | Range | Description |
|-----------|------|---------|-------|-------------|
| `video` | File | Required | - | Main video file (MP4, AVI, MOV, etc.) |
| `trimStart` | float | 0.0 | ≥0 | Start time for trimming (seconds) |
| `trimDuration` | float | null | >0 | Duration to keep (seconds, optional) |
| `brightness` | float | 0.0 | -1 to 1 | Brightness adjustment |
| `contrast` | float | 1.0 | 0 to 4 | Contrast adjustment |
| `saturation` | float | 1.0 | 0 to 4 | Saturation adjustment |
| `textOverlays` | string | "[]" | JSON | JSON array of text overlays |
| `logoOverlays` | string | "[]" | JSON | JSON array of logo overlays |
| `files` | Files | [] | - | Logo image files to upload |

### Text Overlay Object
```json
{
  "text": "Hello World",
  "x": 50,
  "y": 50,
  "start": 0,
  "end": 10,
  "fontsize": 24,
  "fontcolor": "white"
}
```

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `text` | string | Required | Text to display |
| `x` | float | 50 | X position as percentage (0-100) |
| `y` | float | 50 | Y position as percentage (0-100) |
| `start`/`startTime` | float | 0 | Start time in seconds |
| `end`/`endTime` | float | null | End time in seconds |
| `fontsize`/`fontSize` | int | 24 | Font size in pixels |
| `fontcolor`/`color` | string | "white" | Font color |

### Logo Overlay Object
```json
{
  "filename": "logo.png",
  "x": 90,
  "y": 90,
  "width": 100,
  "height": 100,
  "start": 0,
  "end": 10
}
```

| Property | Type | Default | Description |
|----------|------|---------|-------------|
| `filename` | string | Required | Filename of uploaded logo |
| `x` | float | 50 | X position as percentage (0-100) |
| `y` | float | 50 | Y position as percentage (0-100) |
| `width` | int | 100 | Logo width in pixels |
| `height` | int | 100 | Logo height in pixels |
| `start`/`startTime` | float | 0 | Start time in seconds |
| `end`/`endTime` | float | null | End time in seconds |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG_KEEP_UPLOADS` | false | Set to "true" to keep uploaded files for debugging |
| `DEBUG_VERBOSE` | false | Set to "true" for detailed logging |

## Project Structure
```
fastapi_backend/
├── main.py              # Main FastAPI application
├── models/
│   ├── __init__.py
│   └── video_process.py # Pydantic models for video processing
├── services/
│   ├── __init__.py
│   └── video_processor.py # FFmpeg processing logic
├── requirements.txt     # Python dependencies
├── README.md            # This file
└── venv/               # Virtual environment (created during setup)
```

## Testing with Swagger UI

1. Open http://localhost:8000/docs
2. Navigate to the desired endpoint
3. Click "Try it out"
4. Fill in the parameters
5. Click "Execute"
6. Download the resulting file

## Troubleshooting

### FFmpeg Not Found
If you get "FFmpeg is not installed" error:
```bash
# Install FFmpeg
brew install ffmpeg

# Verify installation
which ffmpeg
which ffprobe
```

### Python Version Issue
Make sure you're using Python 3.12:
```bash
# Check Python version
python3.12 --version

# Recreate venv with Python 3.12
rm -rf venv
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Port Already in Use
```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>

# OR use a different port
uvicorn main:app --reload --port 8001
```

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | >=0.100.0 | Web framework |
| uvicorn | >=0.23.0 | ASGI server |
| python-multipart | >=0.0.6 | Form data parsing |
| rembg | >=2.0.50 | Background removal |
| pydantic | >=2.7.0 | Data validation |
| onnxruntime | >=1.23.2 | ML inference runtime |
| numpy | >=2.3.0 | Numerical computing |
| pillow | >=12.1.0 | Image processing |

## License
MIT License

