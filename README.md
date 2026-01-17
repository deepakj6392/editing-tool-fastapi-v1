# FastAPI Server with Background Removal

A simple and clean FastAPI server with image background removal capability.

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
- **Homebrew** (for macOS users, to install Python 3.12)

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

**Alternative (using pyenv):**
```bash
# Install pyenv
brew install pyenv

# Install Python 3.12
pyenv install 3.12.x

# Set Python 3.12 for this project
pyenv local 3.12.x
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

**Note:** This will install:
- `fastapi` - Modern web framework
- `uvicorn[standard]` - ASGI server with auto-reload
- `python-multipart` - Form data parsing for file uploads
- `rembg[cpu]` - Background removal using CPU

### 6. Run the server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

**Alternative run command:**
```bash
python main.py
```

**If port 8000 is in use, use a different port:**
```bash
uvicorn main:app --reload --port 8001
```

### 7. Verify the server is running
Open your browser and navigate to:
- **API URL**: http://localhost:8000
- **Swagger Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/health

## Available Endpoints

| Method | Endpoint | Description | Request Body |
|--------|----------|-------------|--------------|
| GET | `/` | Root endpoint | None |
| GET | `/health` | Health check | None |
| POST | `/remove-bg` | Remove image background | `file`: Image file (PNG, JPG, etc.) |

## Testing the Background Removal API

### Using cURL
```bash
curl -X POST -F "file=@image.png" http://localhost:8000/remove-bg -o output.png
```

### Using Swagger UI
1. Open http://localhost:8000/docs
2. Click on the `/remove-bg` endpoint
3. Click "Try it out"
4. Choose an image file
5. Click "Execute"
6. Download the resulting image with transparent background

## Project Structure
```
fastapi_backend/
├── main.py           # Main FastAPI application
├── README.md         # This file
├── requirements.txt  # Python dependencies
└── venv/            # Virtual environment (created during setup)
```

## Commands Summary

### First-time Setup
```bash
cd fastapi_backend
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

### Run the Server
```bash
cd fastapi_backend
source venv/bin/activate
uvicorn main:app --reload
```

### Stop the Server
Press `Ctrl+C` in the terminal

### Deactivate Virtual Environment (when done)
```bash
deactivate
```

### Restart the Server (after deactivation)
```bash
cd fastapi_backend
source venv/bin/activate
uvicorn main:app --reload
```

## Troubleshooting

### "Python 3.14 is not supported" Error
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

### Port 8000 Already in Use
```bash
# Find process using port 8000
lsof -i :8000

# Kill the process (replace PID with actual process ID)
kill -9 <PID>

# OR use a different port
uvicorn main:app --reload --port 8001
```

### Virtual Environment Activation Fails
```bash
# Recreate the virtual environment
rm -rf venv
python3.12 -m venv venv
source venv/bin/activate
```

### Module Not Found Errors
Reinstall dependencies:
```bash
source venv/bin/activate
pip install --force-reinstall -r requirements.txt
```

## Dependencies Details

| Package | Version | Purpose |
|---------|---------|---------|
| fastapi | >=0.100.0 | Web framework |
| uvicorn | >=0.23.0 | ASGI server implementation |
| python-multipart | >=0.0.6 | Form data parsing |
| rembg | >=2.0.50 | Background removal |
| onnxruntime | >=1.23.2 | ML inference runtime (for rembg) |
| numpy | >=2.3.0 | Numerical computing |
| pillow | >=12.1.0 | Image processing |
| scikit-image | >=0.26.0 | Image processing algorithms |
| pydantic | >=2.7.0 | Data validation |

## License
MIT License


