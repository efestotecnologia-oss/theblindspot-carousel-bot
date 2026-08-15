"""Agente — Immagine di copertina del carosello.

Procura un'immagine full-bleed per la prima slide (copertina) e la
stilizza in coerenza con il brand "The Blind Spot", prima che
`agents/carousel_render.py` la componga con il titolo.

Catena dei provider (il primo disponibile/configurato vince):
1. AI generation (Stability AI) — nello stile scelto dal copy agent
   (cinematic / anime / photographic / digital-art / painterly).
2. Stock fotografico royalty-free (Pexels) — fallback se manca la API key
   di generazione o la chiamata fallisce.
3. Nessuna immagine — il template di copertina ha una variante puramente
   tipografica per questo caso, la pipeline non si blocca mai per questo.

Nota deliberata: non si scaricano screenshot di film/anime reali. Per una
pagina che pubblica ogni giorno senza supervisione, riusare frame protetti
da copyright espone a takedown/ban — fuori scope per questo agente.
"""

from __future__ import annotations

import io
import os
import random
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

STABILITY_API_KEY = os.getenv("STABILITY_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
PROVIDER = os.getenv("COVER_IMAGE_PROVIDER", "auto")  # auto | stability | pexels | none

# Mappa lo stile scelto dal copy agent sui preset dell'API Stability AI.
_STABILITY_STYLE_PRESET = {
    "cinematic": "cinematic",
    "anime": "anime",
    "photographic": "photographic",
    "digital-art": "digital-art",
    "painterly": "fantasy-art",
}

# Query di ripiego per Pexels quando lo stile non è "photographic" — Pexels
# ha solo foto reali, quindi orientiamo la ricerca su mood/atmosfera invece
# che sullo stile pittorico/anime che non può restituire.
_PEXELS_MOOD_HINTS = {
    "cinematic": "moody cinematic",
    "anime": "dramatic silhouette",
    "photographic": "",
    "digital-art": "abstract dark texture",
    "painterly": "atmospheric fine art",
}


def _download(url: str, headers: dict | None = None) -> bytes | None:
    try:
        resp = requests.get(url, headers=headers or {}, timeout=30)
        resp.raise_for_status()
        return resp.content
    except requests.RequestException:
        return None


def _generate_stability(prompt: str, style: str) -> bytes | None:
    if not STABILITY_API_KEY:
        return None
    preset = _STABILITY_STYLE_PRESET.get(style, "cinematic")
    try:
        resp = requests.post(
            "https://api.stability.ai/v2beta/stable-image/generate/core",
            headers={
                "Authorization": f"Bearer {STABILITY_API_KEY}",
                "Accept": "image/*",
            },
            files={"none": ""},
            data={
                "prompt": prompt,
                "aspect_ratio": "4:5",
                "style_preset": preset,
                "output_format": "png",
            },
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.content
        return None
    except requests.RequestException:
        return None


def _search_pexels(topic_keywords: str, style: str) -> bytes | None:
    if not PEXELS_API_KEY:
        return None
    query = " ".join(filter(None, [topic_keywords, _PEXELS_MOOD_HINTS.get(style, "")]))
    try:
        resp = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query.strip() or "abstract dark mood", "per_page": 10,
                    "orientation": "portrait"},
            timeout=20,
        )
        resp.raise_for_status()
        photos = resp.json().get("photos", [])
        if not photos:
            return None
        photo = random.choice(photos[:5])
        return _download(photo["src"]["large2x"])
    except (requests.RequestException, KeyError, ValueError):
        return None


def _stylize(raw: bytes) -> bytes:
    """Applica un trattamento coerente col brand a qualsiasi immagine
    sorgente: desatura leggermente, vira i toni verso la palette
    ink/highlight, aggiunge vignettatura e grana leggera."""
    from PIL import Image, ImageEnhance, ImageOps, ImageDraw, ImageFilter
    import numpy as np

    img = Image.open(io.BytesIO(raw)).convert("RGB")
    # Riempi/croppa a 4:5 (1080x1350) mantenendo il centro dell'inquadratura.
    target_w, target_h = 1080, 1350
    src_ratio = img.width / img.height
    target_ratio = target_w / target_h
    if src_ratio > target_ratio:
        new_w = int(img.height * target_ratio)
        left = (img.width - new_w) // 2
        img = img.crop((left, 0, left + new_w, img.height))
    else:
        new_h = int(img.width / target_ratio)
        top = (img.height - new_h) // 2
        img = img.crop((0, top, img.width, top + new_h))
    img = img.resize((target_w, target_h), Image.LANCZOS)

    # Desaturazione parziale + duotone verso la palette del brand.
    gray = ImageOps.grayscale(img)
    shadow, light = (19, 18, 17), (236, 232, 223)  # --ink, --paper
    duotone = ImageOps.colorize(gray, black=shadow, white=light).convert("RGB")
    img = Image.blend(img, duotone, alpha=0.55)
    img = ImageEnhance.Contrast(img).enhance(1.12)
    img = ImageEnhance.Color(img).enhance(0.85)
    img = ImageEnhance.Brightness(img).enhance(0.92)

    # Vignettatura.
    vignette = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(vignette)
    draw.ellipse((-target_w * 0.35, -target_h * 0.25,
                   target_w * 1.35, target_h * 1.1), fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(180))
    black = Image.new("RGB", img.size, (5, 5, 5))
    img = Image.composite(img, black, vignette)

    # Grana leggera.
    noise = (np.random.default_rng().normal(0, 9, (target_h, target_w, 1))
             .repeat(3, axis=2))
    arr = np.clip(np.array(img).astype(float) + noise, 0, 255).astype("uint8")
    img = Image.fromarray(arr, "RGB")

    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


def get_cover_image(topic: str, cover_image_prompt: str, cover_style: str,
                     out_path: str | Path) -> Path | None:
    """Procura e stilizza l'immagine di copertina. Ritorna None (nessun
    errore) se nessun provider è configurato o tutti falliscono: il
    template di copertina ha una variante senza immagine per questo caso."""
    out_path = Path(out_path)
    prompt = cover_image_prompt or topic
    raw = None

    if PROVIDER in ("auto", "stability"):
        raw = _generate_stability(prompt, cover_style)
    if raw is None and PROVIDER in ("auto", "pexels"):
        raw = _search_pexels(topic, cover_style)
    if raw is None:
        return None

    try:
        styled = _stylize(raw)
    except ImportError:
        # Pillow/numpy non installati: meglio un'immagine non stilizzata
        # che nessuna immagine.
        styled = raw
    out_path.write_bytes(styled)
    return out_path
