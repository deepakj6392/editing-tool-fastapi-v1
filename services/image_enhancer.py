"""
Image enhancement service using Real-ESRGAN.
"""
from __future__ import annotations

import io
import os
import sys
import types
from threading import Lock
from typing import Optional

import numpy as np
from PIL import Image


class ImageEnhancementError(Exception):
    """Custom exception for image enhancement errors."""


_UPSAMPLER = None
_UPSAMPLER_LOCK = Lock()


def _default_model_path() -> str:
    return os.environ.get(
        "REAL_ESRGAN_MODEL_PATH",
        os.path.join("weights", "RealESRGAN_x4plus.pth"),
    )


def _build_upsampler():
    try:
        import cv2
        import torch
        import torchvision.transforms.functional as torchvision_functional

        if "torchvision.transforms.functional_tensor" not in sys.modules:
            functional_tensor = types.ModuleType("torchvision.transforms.functional_tensor")
            functional_tensor.rgb_to_grayscale = torchvision_functional.rgb_to_grayscale
            sys.modules["torchvision.transforms.functional_tensor"] = functional_tensor

        from basicsr.archs.rrdbnet_arch import RRDBNet
        from realesrgan import RealESRGANer
    except ImportError as exc:
        raise ImageEnhancementError(
            "Real-ESRGAN dependencies are not installed. Install torch, "
            "realesrgan, basicsr, torchvision, and opencv-python-headless. "
            f"Original import error: {exc}"
        ) from exc

    model_path = _default_model_path()
    if not os.path.exists(model_path):
        raise ImageEnhancementError(
            f"Real-ESRGAN model weights not found at '{model_path}'. "
            "Set REAL_ESRGAN_MODEL_PATH or place RealESRGAN_x4plus.pth in the weights directory."
        )

    model = RRDBNet(
        num_in_ch=3,
        num_out_ch=3,
        num_feat=64,
        num_block=23,
        num_grow_ch=32,
        scale=4,
    )

    use_half = bool(torch.cuda.is_available())
    tile = int(os.environ.get("REAL_ESRGAN_TILE", "0") or "0")
    tile_pad = int(os.environ.get("REAL_ESRGAN_TILE_PAD", "10") or "10")
    pre_pad = int(os.environ.get("REAL_ESRGAN_PRE_PAD", "0") or "0")

    try:
        return RealESRGANer(
            scale=4,
            model_path=model_path,
            model=model,
            tile=tile,
            tile_pad=tile_pad,
            pre_pad=pre_pad,
            half=use_half,
            gpu_id=0 if torch.cuda.is_available() else None,
        )
    except Exception as exc:
        raise ImageEnhancementError(f"Failed to initialize Real-ESRGAN: {exc}") from exc


def _get_upsampler():
    global _UPSAMPLER
    if _UPSAMPLER is not None:
        return _UPSAMPLER

    with _UPSAMPLER_LOCK:
        if _UPSAMPLER is None:
            _UPSAMPLER = _build_upsampler()

    return _UPSAMPLER


def enhance_image(input_image: bytes, outscale: float = 4.0) -> bytes:
    """
    Enhance an image with Real-ESRGAN and return PNG bytes.
    """
    if not input_image:
        raise ImageEnhancementError("Input image is empty")

    if outscale <= 0:
        raise ImageEnhancementError("outscale must be greater than 0")

    try:
        import cv2
    except ImportError as exc:
        raise ImageEnhancementError(
            "opencv-python-headless is required for image enhancement."
        ) from exc

    try:
        pil_image = Image.open(io.BytesIO(input_image)).convert("RGB")
    except Exception as exc:
        raise ImageEnhancementError(f"Invalid image file: {exc}") from exc

    image_array = np.array(pil_image)
    image_bgr = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR)

    try:
        upsampler = _get_upsampler()
        output_bgr, _ = upsampler.enhance(image_bgr, outscale=float(outscale))
    except ImageEnhancementError:
        raise
    except Exception as exc:
        raise ImageEnhancementError(f"Failed to enhance image: {exc}") from exc

    output_rgb = cv2.cvtColor(output_bgr, cv2.COLOR_BGR2RGB)
    output_image = Image.fromarray(output_rgb)
    buffer = io.BytesIO()
    output_image.save(buffer, format="PNG")
    return buffer.getvalue()
