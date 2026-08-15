"""Agente 3 — Editor video.

Prende il video "base" (footage reale della persona che parla in camera)
+ l'audio generato dall'agente voce, e produce il video finale:
1. labiale sincronizzato al nuovo audio (lip-sync, via Sync Labs)
2. sottotitoli impressi nel video
3. formato verticale 1080x1920 (va bene per Reels/Shorts/TikTok/Telegram)

Sync Labs legge video e audio da URL PUBBLICI, non accetta upload
diretti: i file locali vanno prima passati dall'uploader del progetto
(content/uploader.py, env MEDIA_UPLOADER) — se ne occupa agents/produce.py.

Richiede SYNC_API_KEY nel .env e ffmpeg/ffprobe installati sul sistema
(es. `brew install ffmpeg`).
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

SYNC_BASE_URL = "https://api.sync.so/v2"

# Modello di lip-sync. "lipsync-2-pro" = qualità migliore (dettagli del
# volto), "sync-3" = gestisce meglio angolazioni difficili/primi piani.
# Verificare i modelli disponibili aggiornati su sync.so/docs se necessario.
SYNC_MODEL = os.getenv("SYNC_MODEL", "lipsync-2-pro")

OUTPUT_DIR = Path("output_video")

VIDEO_WIDTH, VIDEO_HEIGHT = 1080, 1920


# =========================================================
# STEP 1 - LIP SYNC (Sync Labs API)
# =========================================================


def lipsync_video(video_url: str, audio_url: str, poll_interval: int = 5) -> Path:
    """Sincronizza il labiale del video base con il nuovo audio, via Sync Labs.

    `video_url` e `audio_url` devono essere URL pubblici già raggiungibili.

    NOTA: la struttura esatta del payload è ricostruita dalla documentazione
    ufficiale sync.so; in caso di errore 400 controllare https://sync.so/docs
    (il messaggio della API indica cosa correggere).
    """
    api_key = os.getenv("SYNC_API_KEY")
    if not api_key:
        raise RuntimeError("SYNC_API_KEY mancante: compilala nel file .env")

    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    payload = {
        "model": SYNC_MODEL,
        "input": [
            {"type": "video", "url": video_url},
            {"type": "audio", "url": audio_url},
        ],
    }

    resp = requests.post(f"{SYNC_BASE_URL}/generate", headers=headers,
                         json=payload, timeout=60)
    resp.raise_for_status()
    generation_id = resp.json()["id"]
    print(f"  lip-sync avviato su Sync Labs: {generation_id}")

    while True:
        status_resp = requests.get(f"{SYNC_BASE_URL}/generate/{generation_id}",
                                   headers=headers, timeout=60)
        status_resp.raise_for_status()
        data = status_resp.json()
        status = data.get("status")

        if status == "COMPLETED":
            output_url = data.get("outputUrl") or data.get("output_url")
            return _download_file(output_url, OUTPUT_DIR / f"lipsync_{generation_id}.mp4")
        if status in ("FAILED", "REJECTED"):
            raise RuntimeError(f"Generazione lip-sync fallita: {data}")

        print(f"  stato Sync Labs: {status}, attendo {poll_interval}s...")
        time.sleep(poll_interval)


def _download_file(url: str, destination: Path) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    with requests.get(url, stream=True, timeout=300) as resp:
        resp.raise_for_status()
        with open(destination, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1 << 20):
                f.write(chunk)
    return destination


# =========================================================
# STEP 2 - SOTTOTITOLI
# =========================================================


def get_audio_duration(audio_path: Path) -> float:
    """Durata dell'audio in secondi, via ffprobe."""
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def generate_subtitles(script_text: str, audio_duration_seconds: float) -> str:
    """Genera il contenuto di un file .srt con i sottotitoli.

    Il testo è distribuito in modo uniforme sulla durata dell'audio
    (approssimativo ma funzionante). Per una sincronizzazione precisa
    parola-per-parola si può integrare Whisper per i timestamp reali —
    miglioramento da valutare in una seconda fase.
    """
    words = script_text.split()
    chunk_size = 6  # parole per sottotitolo
    chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
    seconds_per_chunk = audio_duration_seconds / max(len(chunks), 1)

    srt_lines = []
    for i, chunk in enumerate(chunks):
        start = i * seconds_per_chunk
        end = (i + 1) * seconds_per_chunk
        srt_lines.append(str(i + 1))
        srt_lines.append(f"{_format_srt_time(start)} --> {_format_srt_time(end)}")
        srt_lines.append(chunk)
        srt_lines.append("")

    return "\n".join(srt_lines)


def _format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


# =========================================================
# STEP 3 - FORMATO VERTICALE + BURN-IN SOTTOTITOLI (ffmpeg)
# =========================================================


def _escape_filter_path(path: Path) -> str:
    """Escapa il percorso per il filtro `subtitles` di ffmpeg (: e ')."""
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def finalize_video(video_path: Path, srt_path: Path, output_stem: str) -> Path:
    """Porta il video a 1080x1920 e imprime i sottotitoli, via ffmpeg."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    output_path = OUTPUT_DIR / f"{output_stem}.mp4"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vf",
        f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={VIDEO_WIDTH}:{VIDEO_HEIGHT},"
        f"subtitles='{_escape_filter_path(srt_path)}'",
        "-c:a", "copy",
        str(output_path),
    ]
    subprocess.run(cmd, check=True)
    return output_path


# =========================================================
# PIPELINE COMPLETA DI UN SINGOLO VIDEO
# =========================================================


def produce_final_video(
    video_url: str,
    audio_url: str,
    script_text: str,
    audio_duration_seconds: float,
    output_stem: str,
) -> Path:
    """Lip-sync + sottotitoli + formato: restituisce il video finale locale."""
    synced_video = lipsync_video(video_url, audio_url)

    srt_content = generate_subtitles(script_text, audio_duration_seconds)
    srt_path = OUTPUT_DIR / f"{synced_video.stem}.srt"
    srt_path.write_text(srt_content, encoding="utf-8")

    return finalize_video(synced_video, srt_path, output_stem)
