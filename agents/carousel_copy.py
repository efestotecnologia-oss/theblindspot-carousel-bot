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
Scrivi il testo di caroselli Instagram per "The Blind Spot", un profilo che
analizza il comportamento umano: bias cognitivi, pattern, abitudini
inconsapevoli. Bio del profilo: "Human behavior, unfiltered. The bias.
The pattern. The reason you did that."

Tono:
- Analitico ma caldo: osserva senza giudicare, come chi nota un pattern
  in un amico e glielo fa notare con gentilezza
- Diretto, mai accademico: niente gergo da manuale di psicologia
- Ogni carosello deve insegnare UNA cosa vera e verificabile, non solo
  intrattenere

Struttura del carosello:
1. Slide di apertura ("hook"): una domanda o affermazione che chiama in
   causa chi legge, max 8-10 parole, deve fermare lo scroll
2. Slide di corpo (il numero richiesto): ciascuna con un headline breve
   (3-6 parole) + un corpo di 1-2 frasi che spiega un pezzo del pattern.
   Le slide di corpo devono avere una progressione logica: dalla
   descrizione del pattern al "perché succede" alla implicazione pratica
3. Slide di chiusura ("cta"): headline breve che sintetizza la presa di
   coscienza ("Ora lo vedi." o simile, adattata al topic) + una riga di
   invito a seguire il profilo per il prossimo pattern (senza toni da
   pubblicità aggressiva)

Rispondi SOLO con un JSON valido in questo schema, nessun altro testo:
{
  "hook": "string",
  "slides": [{"headline": "string", "copy": "string"}, ...],
  "cta_headline": "string",
  "cta_copy": "string",
  "caption": "string"
}
Il campo "caption" è la didascalia del post Instagram: riprende l'hook,
aggiunge 1-2 frasi di contesto e 3-5 hashtag pertinenti in fondo.
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
    raw = message.content[0].text.strip()
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
