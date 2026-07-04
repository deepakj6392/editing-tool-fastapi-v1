import asyncio
from gtts import gTTS

async def generate_ai_speech(text: str, output_path: str, lang: str = "en") -> str:
    """
    Generate speech from a text story prompt using Google Text-to-Speech (gTTS).
    Runs the save function inside a thread pool to avoid blocking the FastAPI event loop.
    """
    def _synthesize():
        print(f"[AI-SPEECH] Starting speech synthesis. Text length: {len(text)} | Language: {lang}")
        tts = gTTS(text=text, lang=lang)
        tts.save(output_path)
        print(f"[AI-SPEECH] Generated speech saved to: {output_path}")
        return output_path

    return await asyncio.to_thread(_synthesize)
