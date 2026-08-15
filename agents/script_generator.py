"""Agente 1 — Generatore di script.

Prende un argomento/topic dal piano editoriale e genera uno script
pronto per la voce narrante (30-60 secondi di parlato), rispettando la
"persona" del brand definita una volta sola qui sotto.

Richiede ANTHROPIC_API_KEY nel .env.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

# Modello: Sonnet è la scelta giusta per script brevi e ripetuti.
# Non serve un modello Mythos-class (Fable 5) per questo compito:
# costerebbe molto di più senza un beneficio reale su testi così brevi.
MODEL = os.getenv("SCRIPT_MODEL", "claude-sonnet-5")

# La "persona" del brand: qui definisci UNA VOLTA tono e personalità.
# Ogni script generato erediterà queste caratteristiche.
PERSONA_SYSTEM_PROMPT = """
Scrivi script per brevi video (30-60 secondi) nel personaggio di una ragazza
che parla direttamente alla telecamera. Caratteristiche del tono:

- Informativa: ogni script deve contenere un'informazione o un consiglio
  reale, utile, verificabile — non solo chiacchiere
- Gentile e calorosa: si rivolge a chi ascolta con affetto, mai dall'alto
  al basso, mai giudicante
- Leggermente ironica: qualche battuta o un tocco di autoironia, usata con
  parsimonia, mai forzata
- Sensuale in modo soft: un tono caldo, complice, accattivante — mai
  esplicito, mai volgare. Pensa a un'attitudine "confidenziale tra amiche"
  più che a contenuti sessuali

Regole di struttura:
- Hook nei primi 3 secondi (una domanda, un'affermazione che cattura)
- Corpo centrale con l'informazione/il valore vero
- Chiusura con una call to action naturale verso il canale Telegram
  (senza essere invadente o simile a pubblicità aggressiva)
- Lunghezza: 80-130 parole (per stare in 30-60 secondi di parlato)
- Rispondi SOLO con il testo dello script, senza titoli né commenti

Non scrivere contenuti sessualmente espliciti in nessun caso.
"""

# Piano editoriale di default: usato da `python main.py produce` senza --topic
TOPICS = [
    "Un consiglio pratico che nessuno ti dice davvero",
    "Un mito comune da sfatare sul tuo argomento",
    "Una piccola abitudine quotidiana che fa la differenza",
]


def _get_client():
    from anthropic import Anthropic  # lazy: serve solo in produzione
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY mancante: compilala nel file .env")
    return Anthropic(api_key=api_key)


def generate_script(topic: str) -> str:
    """Genera un singolo script a partire da un argomento."""
    client = _get_client()
    message = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=PERSONA_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Scrivi lo script per un video sul seguente argomento: {topic}",
            }
        ],
    )
    return message.content[0].text
