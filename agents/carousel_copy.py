"""Agente — Generatore di copy per caroselli Instagram.

Prende un argomento/topic e genera la struttura testuale di un carosello
(slide di apertura, N slide di corpo, slide di chiusura/CTA) nella persona
del brand "The Blind Spot". Non genera immagini: quello è compito di
`agents/carousel_render.py`.

Richiede ANTHROPIC_API_KEY nel .env.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

MODEL = os.getenv("CAROUSEL_MODEL", "claude-sonnet-5")

PERSONA_SYSTEM_PROMPT = """
Write Instagram carousel copy for "The Blind Spot", a profile that examines
human behavior: cognitive biases, patterns, unconscious habits. Profile bio:
"Human behavior, unfiltered. The bias. The pattern. The reason you did that."

The audience is English-speaking. Always write in English.

## Research first
You have a web_search tool. Use it before writing. Ground the carousel in
at least one real, named finding (a specific study, researcher, effect, or
statistic) that you can point to. Never invent a statistic, percentage, or
study — if you can't verify a number through search, don't use it; describe
the effect qualitatively instead. Precision beats vagueness: "psychologists"
is weak, "a 2011 Cornell study on X" is strong (only when actually found).

## Tone
- Analytical but warm: observe without judging, like someone who notices a
  pattern in a friend and points it out gently
- Direct, never academic: no psychology-textbook jargon, no hedging
- Concrete over abstract: one vivid, specific everyday example beats three
  generalizations
- Each carousel must teach ONE true, verifiable thing, not just entertain

## Carousel structure
1. Opening slide ("hook"): a question or blunt statement that calls out the
   reader personally (use "you"), max 8-10 words, must stop the scroll. No
   generic openers like "Did you know..." — lead with the tension itself.
2. Body slides (the requested count). Progression across the set must be:
   name the pattern -> show it in a concrete scene -> explain the
   mechanism/why -> ground it in the real research finding -> give the
   practical implication or a way to notice it in yourself. Do not just
   stack facts in random order.
   Each body slide is one of these layouts — choose deliberately per slide,
   don't default to "standard" for everything, and don't force a layout
   where it doesn't fit:
   - "standard": headline (3-6 words) + 1-2 sentences of body copy.
   - "stat": use ONLY when you have a real, search-verified number.
     headline (3-6 words) + "highlight" = the number/stat itself, short
     (e.g. "73%", "3x", "1 in 4") + 1 short sentence of copy giving context
     for the number.
   - "quote": a single punchy reframing line, aphorism-like, that could
     stand alone as a quote card. headline = the quote itself (max ~12
     words, no quotation marks needed), "highlight" = a short 2-5 word
     attribution/context line (e.g. "the sunk cost trap", not a person's
     name). No "copy" needed for this layout.
   - "list": use when the pattern has 2-4 concrete enumerable signs, steps,
     or triggers. headline (3-5 words) + "items" = array of 2-4 short
     phrases (max ~6 words each).
   Vary layouts across the set — avoid two "stat" or two "quote" slides in
   a row, and don't use "list" unless the content genuinely enumerates.
3. Closing slide ("cta"): a short headline that sums up the realization
   ("Now you see it." or similar, adapted to the topic) + one line inviting
   people to follow the profile for the next pattern (never pushy/salesy)

## Cover slide
Before the hook, the carousel opens on a full-bleed image cover with a
short title over it — this is the scroll-stopper, separate from the hook
slide. You don't generate the image, but you choose its direction:
- "cover_title": 2-5 words, punchier and more visual than the hook (it sits
  over an image, not on empty space) — a striking phrase, not a full
  sentence. E.g. "The Mirror Trap", not "Why we avoid our reflection".
- "cover_style": one of "cinematic" | "anime" | "photographic" |
  "digital-art" | "painterly" — pick whichever best matches the emotional
  register of the topic (e.g. an unsettling social-pressure topic could
  suit "cinematic" or "digital-art"; a nostalgia/memory topic could suit
  "painterly" or "anime"). Vary this across different carousels/topics,
  don't default to the same style every time.
- "cover_image_prompt": a vivid, concrete visual scene (not abstract
  concepts) that evokes the topic without being a literal illustration of
  it — think film-still or book-cover, moody and metaphorical, one
  specific subject/setting/lighting. 1-2 sentences, in English, written as
  a prompt for an image generation model (describe subject, setting,
  lighting, mood — no text/words in the image itself).

Respond ONLY with valid JSON in this schema, no other text:
{
  "cover_title": "string",
  "cover_style": "cinematic|anime|photographic|digital-art|painterly",
  "cover_image_prompt": "string",
  "hook": "string",
  "slides": [
    {"layout": "standard|stat|quote|list", "headline": "string",
     "copy": "string (standard/stat only)",
     "highlight": "string (stat/quote only)",
     "items": ["string", ...] (list only)}
  ],
  "cta_headline": "string",
  "cta_copy": "string",
  "caption": "string"
}
"caption" is the Instagram post caption: it reuses the hook, adds 2-3
sentences of context grounded in the research (not just a rephrase of the
slides), and ends with 3-5 relevant hashtags mixing one broad tag (e.g.
#psychology) with more specific/niche ones (e.g. #cognitivebias,
#behavioralscience) — avoid generic spam tags (#instagood, #viral).
"""


@dataclass
class CarouselCopy:
    hook: str
    slides: list[dict]
    cta_headline: str
    cta_copy: str
    caption: str
    cover_title: str = ""
    cover_style: str = "cinematic"
    cover_image_prompt: str = ""

    @property
    def total_slides(self) -> int:
        return 3 + len(self.slides)  # cover + hook + body slides + cta

    def __post_init__(self) -> None:
        for s in self.slides:
            s.setdefault("layout", "standard")


def _get_client():
    from anthropic import Anthropic  # lazy: serve solo in produzione
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY mancante: compilala nel file .env")
    return Anthropic(api_key=api_key)


def _extract_json(message) -> dict:
    if message.stop_reason == "max_tokens":
        # Con il tool di web search le ricerche consumano lo stesso budget di
        # token della risposta finale: se il modello e' stato troncato prima
        # di chiudere il JSON, e' inutile provare a fare il parsing.
        raise RuntimeError(
            "Risposta troncata (max_tokens raggiunto prima del JSON finale): "
            "alza max_tokens in generate_carousel_copy() o riduci max_uses "
            "del web_search."
        )
    # Con il tool di web search Claude produce piu' blocchi di testo
    # (ragionamento intermedio tra una ricerca e l'altra): il JSON finale
    # e' sempre nell'ULTIMO blocco di testo, non nel primo.
    text_blocks = [b.text for b in message.content if b.type == "text"]
    if not text_blocks:
        raise RuntimeError("Nessun blocco di testo nella risposta del modello")
    raw = text_blocks[-1].strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.lower().startswith("json"):
            raw = raw.split("\n", 1)[1]
    # Claude a volte precede il JSON con una frase di transizione (frequente
    # quando ha appena usato il web search), senza blocco ```: isoliamo
    # l'oggetto JSON invece di assumere che raw inizi con "{".
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    return json.loads(raw)


def generate_carousel_copy(topic: str, n_body_slides: int = 5) -> CarouselCopy:
    """Genera la struttura testuale di un carosello per un topic, usando
    la ricerca web per ancorare il contenuto a fonti reali."""
    client = _get_client()
    kwargs = dict(
        model=MODEL,
        max_tokens=8000,
        system=PERSONA_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"Carousel topic: {topic}\n"
                f"Number of body slides required: {n_body_slides}"
            ),
        }],
    )
    try:
        message = client.messages.create(
            tools=[{"type": "web_search_20250305", "name": "web_search",
                    "max_uses": 4}],
            **kwargs,
        )
    except Exception:
        # Fallback se il tool di ricerca non e' disponibile per questo
        # account/modello: meglio generare senza ricerca che bloccarsi.
        message = client.messages.create(**kwargs)
    data = _extract_json(message)
    return CarouselCopy(
        hook=data["hook"],
        slides=data["slides"],
        cta_headline=data["cta_headline"],
        cta_copy=data["cta_copy"],
        caption=data["caption"],
        cover_title=data.get("cover_title", data["hook"]),
        cover_style=data.get("cover_style", "cinematic"),
        cover_image_prompt=data.get("cover_image_prompt", ""),
    )
