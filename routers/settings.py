import os
import tempfile
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from db import get_all_settings, set_setting
from tts_engine import get_tts_engine

router = APIRouter(prefix="/settings", tags=["settings"])

class SettingUpdate(BaseModel):
    key: str
    value: str

@router.get("/")
async def get_settings():
    """Get all TTS settings."""
    try:
        return get_all_settings()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/")
async def update_setting(setting: SettingUpdate):
    """Update a TTS setting."""
    valid_keys = {'tts_engine', 'ollama_url', 'ollama_model', 'kokoro_voice', 'edge_tts_voice'}
    if setting.key not in valid_keys:
        raise HTTPException(status_code=400, detail=f"Unknown setting: {setting.key}")
    try:
        set_setting(setting.key, setting.value)
        return {"success": True, "key": setting.key, "value": setting.value}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tts-status")
async def get_tts_status():
    """Check if the configured TTS engine is available. Used by frontend to switch modes."""
    try:
        settings = get_all_settings()
        engine_type = settings.get('tts_engine', 'ollama')

        if engine_type == 'ollama':
            engine = get_tts_engine(
                'ollama',
                ollama_url=settings.get('ollama_url', 'http://localhost:11434'),
                model=settings.get('ollama_model', 'legraphista/Orpheus:latest')
            )
            model_label = settings.get('ollama_model', 'Orpheus')
        elif engine_type == 'edge_tts':
            engine = get_tts_engine('edge_tts', voice=settings.get('edge_tts_voice', 'es-ES-AlvaroNeural'))
            model_label = settings.get('edge_tts_voice', 'es-ES-AlvaroNeural')
        else:
            engine = get_tts_engine('kokoro', voice=settings.get('kokoro_voice', 'af_heart'))
            model_label = settings.get('kokoro_voice', 'af_heart')

        available = engine.is_available()
        return {
            "available": available,
            "engine": engine_type,
            "model": model_label,
        }
    except Exception as e:
        return {"available": False, "engine": "unknown", "model": None}

@router.post("/preview-voice")
def preview_voice(engine_type: str = None, voice: str = None):
    """Generate a short audio sample and return it for playback."""
    settings = get_all_settings()
    engine_type = engine_type or settings.get('tts_engine', 'edge_tts')

    SAMPLE_TEXTS = {
        'edge_tts': 'Hola, esta es una muestra de la voz seleccionada. Escucha qué natural suena.',
        'ollama': 'Hello, this is a sample of the Orpheus voice.',
        'kokoro': 'Hello, this is a sample of the Kokoro voice.',
    }
    sample_text = SAMPLE_TEXTS.get(engine_type, 'Hello, this is a voice sample.')

    if engine_type == 'edge_tts':
        voice = voice or settings.get('edge_tts_voice', 'es-ES-AlvaroNeural')
        engine = get_tts_engine('edge_tts', voice=voice)
        ext = '.mp3'
        media_type = 'audio/mpeg'
    elif engine_type == 'ollama':
        voice = voice or settings.get('ollama_model', 'legraphista/Orpheus:latest')
        engine = get_tts_engine(
            'ollama',
            ollama_url=settings.get('ollama_url', 'http://localhost:11434'),
            model=settings.get('ollama_model', 'legraphista/Orpheus:latest'),
        )
        ext = '.wav'
        media_type = 'audio/wav'
    else:
        voice = voice or settings.get('kokoro_voice', 'af_heart')
        engine = get_tts_engine('kokoro', voice=voice)
        ext = '.wav'
        media_type = 'audio/wav'

    if not engine.is_available():
        raise HTTPException(status_code=503, detail="Motor TTS no disponible.")

    tmp = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
    tmp.close()
    try:
        success = engine.generate_audio(sample_text, tmp.name)
        if not success:
            raise HTTPException(status_code=503, detail="No se pudo generar el audio de muestra.")
        with open(tmp.name, 'rb') as f:
            audio_bytes = f.read()
        return Response(content=audio_bytes, media_type=media_type)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)
