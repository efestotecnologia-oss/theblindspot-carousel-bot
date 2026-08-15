"""Pipeline di produzione caroselli: topic → copy → slide PNG → bozza.

Orchestra `carousel_copy` (testo) e `carousel_render` (immagini) e salva il
risultato come Post in stato DRAFT nello store dei contenuti — da lì vale
il flusso già esistente (preview → approve → run): niente va online senza
approvazione, a meno che non si usi `run --auto`.

Prerequisiti:
- ANTHROPIC_API_KEY nel .env (copy)
- playwright installato + `playwright install chromium` (render)
- MEDIA_UPLOADER configurato: Instagram legge le immagini da URL pubblici
"""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from agents import carousel_copy, carousel_render
from content.factory import ContentStore
from content.uploader import MediaUploader, get_uploader
from core.models import Media, MediaType, Platform, Post

DEFAULT_PLATFORMS = "instagram,facebook"
DEFAULT_BODY_SLIDES = 5


def _target_platforms() -> list[Platform]:
    raw = os.getenv("CAROUSEL_PLATFORMS", DEFAULT_PLATFORMS)
    return [Platform(p.strip()) for p in raw.split(",") if p.strip()]


def _check_prerequisites() -> MediaUploader:
    uploader = get_uploader()
    if uploader is None:
        raise RuntimeError(
            "Nessun MEDIA_UPLOADER configurato: Instagram legge le immagini "
            "da URL pubblici. Configura l'uploader nel .env (local o s3)."
        )
    return uploader


def produce_carousel_one(store: ContentStore, topic: str, post_id: str,
                          platforms: list[Platform], uploader: MediaUploader,
                          n_body_slides: int = DEFAULT_BODY_SLIDES) -> Post:
    """Produce un singolo carosello e lo salva come bozza nello store."""
    print(f"[1/2] Copy per: {topic!r}")
    copy = carousel_copy.generate_carousel_copy(topic, n_body_slides=n_body_slides)

    print(f"[2/2] Render {copy.total_slides} slide")
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"carousel-{post_id}-"))
    try:
        slide_paths = carousel_render.render_carousel(copy, tmp_dir, post_id)
        media = [Media(url=uploader.upload(str(p)), type=MediaType.IMAGE)
                 for p in slide_paths]
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    post = Post(id=post_id, text=copy.caption, media=media, platforms=platforms)
    store.upsert(post)
    return post


def produce_carousel(store: ContentStore, topics: list[str] | None = None,
                      n_body_slides: int = DEFAULT_BODY_SLIDES) -> list[Post]:
    """Produce un carosello per ogni topic passato (nessun default: il piano
    editoriale dei caroselli va sempre indicato esplicitamente con --topic)."""
    if not topics:
        raise RuntimeError(
            "Nessun topic indicato: usa --topic \"argomento\" (ripetibile)."
        )
    uploader = _check_prerequisites()
    platforms = _target_platforms()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    posts = []
    for i, topic in enumerate(topics, start=1):
        post_id = f"carousel-{stamp}-{i:02d}"
        posts.append(produce_carousel_one(store, topic, post_id, platforms,
                                          uploader, n_body_slides))
    return posts
