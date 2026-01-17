"""
Background removal service using rembg.
Provides functions for removing backgrounds from images.
"""
from PIL import Image
from rembg import remove, new_session


class BackgroundRemovalError(Exception):
    """Custom exception for background removal errors"""
    pass


def remove_background(input_image: bytes, model: str = "u2net") -> bytes:
    """
    Remove background from an image.
    
    Args:
        input_image: Raw image bytes (PNG, JPG, etc.)
        model: rembg model to use (default: "u2net")
        
    Returns:
        Processed image bytes with transparent background (PNG)
        
    Raises:
        BackgroundRemovalError: If background removal fails
    """
    try:
        output_image = remove(input_image)
        return output_image
    except Exception as e:
        raise BackgroundRemovalError(f"Failed to remove background: {str(e)}")


def remove_background_with_model(input_image: bytes, model_name: str = "u2net") -> bytes:
    """
    Remove background from an image using a specific model.
    
    Args:
        input_image: Raw image bytes
        model_name: Model name (e.g., "u2net", "u2netp", "briaai/RMBG-1.4")
        
    Returns:
        Processed image bytes with transparent background
        
    Raises:
        BackgroundRemovalError: If background removal fails
    """
    try:
        session = new_session(model_name)
        output_image = remove(input_image, session=session)
        return output_image
    except Exception as e:
        raise BackgroundRemovalError(f"Failed to remove background: {str(e)}")


def remove_background_pil(image: Image.Image) -> Image.Image:
    """
    Remove background from a PIL Image.
    
    Args:
        image: PIL Image object
        
    Returns:
        PIL Image with transparent background
        
    Raises:
        BackgroundRemovalError: If background removal fails
    """
    try:
        output_image = remove(image)
        return output_image
    except Exception as e:
        raise BackgroundRemovalError(f"Failed to remove background: {str(e)}")

