"""Livello di approvazione (Fase 1: "prima con approvazione, poi automatico").

Interfaccia comune `Approver` con due implementazioni:
- ConsoleApprover  -> chiede conferma dal terminale.
- TelegramApprover -> manda l'anteprima sul telefono con pulsanti
                      Approva/Rifiuta e attende la risposta.

Selezione via env APPROVAL_CHANNEL = console | telegram.
In modalità completamente automatica (`run --auto`) l'approvazione è saltata.
"""

from __future__ import annotations

import os
import time
from abc import ABC, abstractmethod

import requests

from core.models import Post


def preview(post: Post) -> str:
    plats = ", ".join(p.value for p in post.platforms)
    media = "\n".join(f"    - [{m.type.value}] {m.url}" for m in post.media) or "    (nessun media)"
    when = post.scheduled_at.isoformat() if post.scheduled_at else "subito"
    return (
        f"\n─── ANTEPRIMA POST {post.id} ───\n"
        f"  Piattaforme: {plats}\n"
        f"  Quando:      {when}\n"
        f"  Testo:\n    {post.text}\n"
        f"  Media:\n{media}\n"
        f"───────────────────────────────"
    )


class Approver(ABC):
    @abstractmethod
    def request(self, post: Post) -> bool:
        """Mostra l'anteprima e restituisce True se approvato."""
        raise NotImplementedError


class ConsoleApprover(Approver):
    def request(self, post: Post) -> bool:
        print(preview(post))
        answer = input("Pubblicare questo post? [s/N] ").strip().lower()
        return answer in ("s", "si", "sì", "y", "yes")


class TelegramApprover(Approver):
    """Invia l'anteprima su Telegram con pulsanti e attende la scelta.

    Serve un bot (BotFather) e la chat_id del destinatario.
    """

    API = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, token: str, chat_id: str, timeout: int = 3600):
        self.token = token
        self.chat_id = chat_id
        self.timeout = timeout  # secondi max di attesa della risposta

    def _call(self, method: str, **params) -> dict:
        r = requests.post(self.API.format(token=self.token, method=method),
                          json=params, timeout=40)
        return r.json()

    def request(self, post: Post) -> bool:
        # Salta gli update vecchi per non leggere risposte stantie
        updates = self._call("getUpdates", timeout=0)
        offset = 0
        for u in updates.get("result", []):
            offset = max(offset, u["update_id"] + 1)

        keyboard = {"inline_keyboard": [[
            {"text": "✅ Approva", "callback_data": f"approve:{post.id}"},
            {"text": "❌ Rifiuta", "callback_data": f"reject:{post.id}"},
        ]]}
        sent = self._call("sendMessage", chat_id=self.chat_id,
                          text=f"Post da approvare:\n{preview(post)}",
                          reply_markup=keyboard)
        if not sent.get("ok"):
            raise RuntimeError(f"Telegram sendMessage fallito: {sent}")

        deadline = time.time() + self.timeout
        while time.time() < deadline:
            resp = self._call("getUpdates", offset=offset, timeout=30)
            for u in resp.get("result", []):
                offset = u["update_id"] + 1
                cb = u.get("callback_query")
                if not cb:
                    continue
                data = cb.get("data", "")
                if data.endswith(f":{post.id}"):
                    self._call("answerCallbackQuery", callback_query_id=cb["id"])
                    approved = data.startswith("approve:")
                    self._call("sendMessage", chat_id=self.chat_id,
                               text=("✅ Approvato: " if approved else "❌ Rifiutato: ") + post.id)
                    return approved
        return False  # timeout = non approvato


def get_approver() -> Approver:
    channel = os.getenv("APPROVAL_CHANNEL", "console").lower()
    if channel == "telegram":
        return TelegramApprover(
            os.environ["TELEGRAM_BOT_TOKEN"],
            os.environ["TELEGRAM_CHAT_ID"],
            int(os.getenv("TELEGRAM_APPROVAL_TIMEOUT", "3600")),
        )
    return ConsoleApprover()
