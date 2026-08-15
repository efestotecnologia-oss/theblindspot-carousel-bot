"""Pipeline di produzione: topic → script → voce → video finale → bozza.

Orchestra gli agenti 1-3 e salva il risultato come Post in stato DRAFT
nello store dei contenuti: da lì in poi vale il flusso già esistente
(preview → approve → run), quindi niente va online senza approvazione.

Prerequisiti oltre alle API key dei singoli agenti:
- BASE_VIDEO_PATH nel .env: il footage locale della persona che parla
  in camera (il "video base" a cui verrà sincronizzato il labiale)
- MEDIA_UPLOADER configurato: Sync Labs legge video e audio da URL
  pubblici, quindi serve l'uploader del progetto (content/uploader.py)
- ffmpeg/ffprobe installati sul sistema
"""

from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path

from agents import script_generator, video_editor, voice_agent
from content.factory import ContentStore
from content.uploader import MediaUploader, get_uploader
from core.models import Media, MediaType, Platform, Post

# Piattaforme di destinazione delle bozze prodotte (modificabili poi
# nello store, prima dell'approvazione)
DEFAULT_PLATFORMS = "telegram,instagram,facebook"


def _target_platforms() -> list[Platform]:
    raw = os.getenv("PRODUCE_PLATFORMS", DEFAULT_PLATFORMS)
    return [Platform(p.strip()) for p in raw.split(",") if p.strip()]


def _build_caption(script_text: str) -> str:
    """Didascalia del post: l'hook dello script + hashtag/CTA configurabili."""
    first_line = script_text.strip().splitlines()[0][:150]
    suffix = os.getenv("CAPTION_SUFFIX", "").strip()
    return f"{first_line}\n\n{suffix}" if suffix else first_line


def _check_prerequisites() -> tuple[Path, MediaUploader]:
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("ffmpeg/ffprobe non trovati: installali (es. `brew install ffmpeg`)")

    base_video = Path(os.getenv("BASE_VIDEO_PATH", ""))
    if not base_video.is_file():
        raise RuntimeError(
            "BASE_VIDEO_PATH mancante o inesistente nel .env: serve il footage "
            "locale della persona che parla in camera"
        )

    uploader = get_uploader()
    if uploader is None:
        raise RuntimeError(
            "Nessun MEDIA_UPLOADER configurato: Sync Labs legge i file da URL "
            "pubblici. Configura l'uploader nel .env (local o s3)."
        )
    return base_video, uploader


def produce_one(store: ContentStore, topic: str, post_id: str,
                base_video_url: str, platforms: list[Platform],
                uploader: MediaUploader) -> Post:
    """Produce un singolo contenuto e lo salva come bozza nello store."""
    print(f"[1/3] Script per: {topic!r}")
    script_text = script_generator.generate_script(topic)

    print("[2/3] Voce (ElevenLabs)")
    audio_path = voice_agent.generate_voice(script_text, f"{post_id}.mp3")
    audio_url = uploader.upload(str(audio_path))
    duration = video_editor.get_audio_duration(audio_path)

    print("[3/3] Video: lip-sync + sottotitoli + formato")
    final_video = video_editor.produce_final_video(
        video_url=base_video_url,
        audio_url=audio_url,
        script_text=script_text,
        audio_duration_seconds=duration,
        output_stem=post_id,
    )

    post = Post(
        id=post_id,
        text=_build_caption(script_text),
        media=[Media(url=str(final_video), type=MediaType.VIDEO)],
        platforms=platforms,
    )
    store.upsert(post)
    return post


def produce(store: ContentStore, topics: list[str] | None = None) -> list[Post]:
    """Produce una bozza per ogni topic (default: TOPICS del piano editoriale)."""
    base_video, uploader = _check_prerequisites()
    platforms = _target_platforms()
    topics = topics or script_generator.TOPICS

    # Il video base è lo stesso per tutti i topic: caricato una volta sola
    base_video_url = uploader.upload(str(base_video))

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    posts = []
    for i, topic in enumerate(topics, start=1):
        post_id = f"auto-{stamp}-{i:02d}"
        posts.append(produce_one(store, topic, post_id, base_video_url,
                                 platforms, uploader))
    return posts
