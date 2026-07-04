import os
import torch
import uuid
import numpy as np
from typing import Optional

# Global variables for lazy loading
_processor = None
_model = None

def get_musicgen_model():
    """
    Lazy loads the processor and model to keep server startup fast.
    Downloads the model to Hugging Face cache on the first run (~1.2GB).
    """
    global _processor, _model
    if _model is None:
        print("[AI-MUSIC] Loading facebook/musicgen-small model and processor...")
        from transformers import MusicgenForConditionalGeneration, AutoProcessor
        
        # Disable GPU warning on Mac if MPS is not preferred/supported for MusicGen.
        # CPU is safe and standard.
        device = "cpu"
        if torch.cuda.is_available():
            device = "cuda"
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            # MusicGen can sometimes run on MPS, but CPU is extremely stable.
            pass
            
        _processor = AutoProcessor.from_pretrained("facebook/musicgen-small")
        _model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-small").to(device)
        print(f"[AI-MUSIC] Model loaded successfully on device: {device}")
        
    return _processor, _model

async def generate_ai_music(prompt: str, duration_sec: float, output_path: str) -> str:
    """
    Generate audio from a text story prompt using facebook/musicgen-small.
    Runs the inference block inside a thread pool to avoid blocking the FastAPI event loop.
    """
    import asyncio
    
    def _infer():
        processor, model = get_musicgen_model()
        device = model.device
        
        inputs = processor(
            text=[prompt],
            padding=True,
            return_tensors="pt",
        ).to(device)
        
        # MusicGen outputs 50 frame tokens per second of generated audio.
        # We calculate max_new_tokens = duration_sec * 50
        max_tokens = int(max(5.0, min(30.0, duration_sec)) * 50)
        
        print(f"[AI-MUSIC] Starting inference. Prompt: '{prompt}' | Duration: {duration_sec}s | Tokens: {max_tokens}")
        
        with torch.no_grad():
            audio_values = model.generate(**inputs, max_new_tokens=max_tokens)
            
        # The output is a tensor of shape (batch, channels, sequence_length)
        sampling_rate = model.config.audio_encoder.sampling_rate
        
        # Move back to CPU to save as wav
        audio_data = audio_values[0, 0].cpu().numpy()
        
        # Normalize audio signal to prevent clipping and fit 16-bit range
        max_val = np.max(np.abs(audio_data))
        if max_val > 0:
            audio_data = audio_data / max_val
            
        audio_data_int = (audio_data * 32767).astype(np.int16)
        
        from scipy.io import wavfile
        wavfile.write(output_path, sampling_rate, audio_data_int)
        
        print(f"[AI-MUSIC] Generated audio saved to: {output_path}")
        return output_path

    return await asyncio.to_thread(_infer)
