"""Agente — Rendering delle slide del carosello in immagini PNG.

Prende la struttura testuale prodotta da `agents/carousel_copy.py` e la
renderizza in PNG (1080x1350, formato 4:5 per il feed Instagram) usando
il template HTML/CSS in `templates/carousel/` e un browser headless
(Playwright/Chromium).

Richiede: `pip install playwright && playwright install chromium`.
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from agents.carousel_copy import CarouselCopy

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "carousel"
SLIDE_WIDTH = 1080
SLIDE_HEIGHT = 1350

# Opacità del "punto cieco": quasi pieno sulla prima slide (non vedi ancora),
# vuoto sull'ultima (ora vedi). Interpolazione lineare sull'indice.
FILL_MAX = 0.4
FILL_MIN = 0.0


@dataclass
class SlideSpec:
    kind: str          # "cover" | "hook" | "body" | "cta"
    index: int
    total: int
    headline: str
    copy: str = ""
    layout: str = "standard"   # "standard" | "stat" | "quote" | "list"
    highlight: str = ""
    items: list[str] | None = None
    cover_image_data_uri: str = ""

    @property
    def fill_opacity(self) -> float:
        if self.total <= 1:
            return FILL_MIN
        t = (self.index - 1) / (self.total - 1)
        return round(FILL_MAX * (1 - t), 3)


def _image_data_uri(path: Path | None) -> str:
    if not path:
        return ""
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def build_slide_specs(copy: CarouselCopy, cover_image_path: Path | None = None) -> list[SlideSpec]:
    total = copy.total_slides
    specs = [SlideSpec(kind="cover", index=1, total=total, headline=copy.cover_title,
                        cover_image_data_uri=_image_data_uri(cover_image_path))]
    specs.append(SlideSpec(kind="hook", index=2, total=total, headline=copy.hook))
    for i, s in enumerate(copy.slides, start=3):
        specs.append(SlideSpec(
            kind="body", index=i, total=total,
            headline=s["headline"], copy=s.get("copy", ""),
            layout=s.get("layout", "standard"),
            highlight=s.get("highlight", ""),
            items=s.get("items") or None,
        ))
    specs.append(SlideSpec(kind="cta", index=total, total=total,
                            headline=copy.cta_headline, copy=copy.cta_copy))
    return specs


def render_carousel(copy: CarouselCopy, output_dir: str | Path, stem: str,
                     cover_image_path: str | Path | None = None) -> list[Path]:
    """Renderizza tutte le slide e restituisce i path dei PNG generati, in ordine."""
    from playwright.sync_api import sync_playwright  # lazy: serve solo in produzione

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    specs = build_slide_specs(copy, Path(cover_image_path) if cover_image_path else None)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("slide.html")

    paths: list[Path] = []
    with sync_playwright() as p:
        # Alcuni ambienti cloud hanno una versione di Chromium pre-installata
        # più vecchia di quella attesa dal pacchetto playwright pinnato: in
        # quel caso preferiamo l'eseguibile già presente invece di tentare
        # (e fallire) un download.
        browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
        executable_path = None
        if browsers_path:
            candidates = sorted(Path(browsers_path).glob("chromium*/chrome-linux/chrome"))
            if candidates:
                executable_path = str(candidates[-1])
        browser = p.chromium.launch(executable_path=executable_path) if executable_path \
            else p.chromium.launch()
        page = browser.new_page(viewport={"width": SLIDE_WIDTH, "height": SLIDE_HEIGHT})
        try:
            for spec in specs:
                html = template.render(
                    kind=spec.kind,
                    index=spec.index,
                    total=spec.total,
                    headline=spec.headline,
                    copy=spec.copy,
                    layout=spec.layout,
                    highlight=spec.highlight,
                    items=spec.items,
                    cover_image_data_uri=spec.cover_image_data_uri,
                    fill_opacity=spec.fill_opacity,
                )
                tmp_html = TEMPLATE_DIR / "_tmp_slide.html"
                tmp_html.write_text(html, encoding="utf-8")
                page.goto(tmp_html.as_uri())
                page.wait_for_timeout(80)  # margine per il caricamento dei font
                out_path = output_dir / f"{stem}-{spec.index:02d}.png"
                page.locator(".slide").screenshot(path=str(out_path))
                paths.append(out_path)
                tmp_html.unlink(missing_ok=True)
        finally:
            browser.close()
    return paths
