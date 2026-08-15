"""Agente 2 — Voce narrante.

Trasforma lo script testuale in un file audio .mp3, usando la voce
configurata su ElevenLabs (modello multilingual, adatto all'italiano).

Richiede ELEVENLABS_API_KEY e ELEVENLABS_VOICE_ID nel .env. Se hai
clonato una voce personalizzata, il VOICE_ID è nella sezione "Voices"
della dashboard ElevenLabs.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Modello vocale ElevenLabs: multilingual è la scelta giusta per l'italiano
MODEL_ID = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")

OUTPUT_DIR = Path("output_audio")


def _get_client():
    from elevenlabs.client import ElevenLabs  # lazy: serve solo in produzione
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY mancante: compilala nel file .env")
    return ElevenLabs(api_key=api_key)


def generate_voice(script_text: str, output_filename: str) -> Path:
    """Genera l'audio a partire da un testo e lo salva su disco."""
    voice_id = os.getenv("ELEVENLABS_VOICE_ID")
    if not voice_id:
        raise RuntimeError("ELEVENLABS_VOICE_ID mancante: compilalo nel file .env")

    client = _get_client()
    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / output_filename

    audio = client.text_to_speech.convert(
        voice_id=voice_id,
        model_id=MODEL_ID,
        text=script_text,
    )

    with open(output_path, "wb") as f:
        for chunk in audio:
            f.write(chunk)

    return output_path
