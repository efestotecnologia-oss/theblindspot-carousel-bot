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

Tone:
- Analytical but warm: observe without judging, like someone who notices a
  pattern in a friend and points it out gently
- Direct, never academic: no psychology-textbook jargon
- Each carousel must teach ONE true, verifiable thing, not just entertain

Carousel structure:
1. Opening slide ("hook"): a question or statement that calls out the
   reader, max 8-10 words, must stop the scroll
2. Body slides (the requested count): each with a short headline (3-6
   words) + 1-2 sentences of body copy explaining one piece of the pattern.
   Body slides must have a logical progression: from describing the
   pattern, to why it happens, to the practical implication
3. Closing slide ("cta"): a short headline that sums up the realization
   ("Now you see it." or similar, adapted to the topic) + one line inviting
   people to follow the profile for the next pattern (never pushy/salesy)

Respond ONLY with valid JSON in this schema, no other text:
{
  "hook": "string",
  "slides": [{"headline": "string", "copy": "string"}, ...],
  "cta_headline": "string",
  "cta_copy": "string",
  "caption": "string"
}
"caption" is the Instagram post caption: it reuses the hook, adds 1-2
sentences of context, and ends with 3-5 relevant hashtags.
"""


@dataclass
class CarouselCopy:
    hook: str
    slides: list[dict]
    cta_headline: str
    cta_copy: str
    caption: str

    @property
    def total_slides(self) -> int:
        return 2 + len(self.slides)  # hook + body slides + cta


def _get_client():
    from anthropic import Anthropic  # lazy: serve solo in produzione
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY mancante: compilala nel file .env")
    return Anthropic(api_key=api_key)


def generate_carousel_copy(topic: str, n_body_slides: int = 5) -> CarouselCopy:
    """Genera la struttura testuale di un carosello per un topic."""
    client = _get_client()
    message = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=PERSONA_SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                f"Argomento del carosello: {topic}\n"
                f"Numero di slide di corpo richieste: {n_body_slides}"
            ),
        }],
    )
    raw = next(b.text for b in message.content if b.type == "text").strip()
    # Claude a volte racchiude il JSON in un blocco ```json — lo ripuliamo.
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        if raw.lower().startswith("json"):
            raw = raw.split("\n", 1)[1]
    data = json.loads(raw)
    return CarouselCopy(
        hook=data["hook"],
        slides=data["slides"],
        cta_headline=data["cta_headline"],
        cta_copy=data["cta_copy"],
        caption=data["caption"],
    )
