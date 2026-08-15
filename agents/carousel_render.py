"""Agente — Rendering delle slide del carosello in immagini PNG.

Prende la struttura testuale prodotta da `agents/carousel_copy.py` e la
renderizza in PNG (1080x1350, formato 4:5 per il feed Instagram) usando
il template HTML/CSS in `templates/carousel/` e un browser headless
(Playwright/Chromium).

Richiede: `pip install playwright && playwright install chromium`.
"""

from __future__ import annotations

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
    kind: str          # "hook" | "body" | "cta"
    index: int
    total: int
    headline: str
    copy: str = ""

    @property
    def fill_opacity(self) -> float:
        if self.total <= 1:
            return FILL_MIN
        t = (self.index - 1) / (self.total - 1)
        return round(FILL_MAX * (1 - t), 3)


def build_slide_specs(copy: CarouselCopy) -> list[SlideSpec]:
    total = copy.total_slides
    specs = [SlideSpec(kind="hook", index=1, total=total, headline=copy.hook)]
    for i, s in enumerate(copy.slides, start=2):
        specs.append(SlideSpec(kind="body", index=i, total=total,
                                headline=s["headline"], copy=s.get("copy", "")))
    specs.append(SlideSpec(kind="cta", index=total, total=total,
                            headline=copy.cta_headline, copy=copy.cta_copy))
    return specs


def render_carousel(copy: CarouselCopy, output_dir: str | Path, stem: str) -> list[Path]:
    """Renderizza tutte le slide e restituisce i path dei PNG generati, in ordine."""
    from playwright.sync_api import sync_playwright  # lazy: serve solo in produzione

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    specs = build_slide_specs(copy)

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("slide.html")

    paths: list[Path] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": SLIDE_WIDTH, "height": SLIDE_HEIGHT})
        try:
            for spec in specs:
                html = template.render(
                    kind=spec.kind,
                    index=spec.index,
                    total=spec.total,
                    headline=spec.headline,
                    copy=spec.copy,
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
