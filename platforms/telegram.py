"""Adapter Telegram — pubblica sul canale via Bot API.

A differenza di Instagram/TikTok, Telegram accetta anche l'upload diretto
del file locale (multipart, max ~50 MB via Bot API): se il media è un
percorso locale non serve l'uploader, il video parte direttamente da disco.

Riusa lo stesso bot dell'approvazione (TELEGRAM_BOT_TOKEN); il canale di
destinazione è TELEGRAM_CHANNEL_ID (il bot deve esserne amministratore).
"""

from __future__ import annotations

import os

import requests

from core.models import MediaType, Platform, Post, PublishResult
from platforms.base import PlatformAdapter
from content.uploader import is_local_path

API = "https://api.telegram.org/bot{token}/{method}"


class TelegramAdapter(PlatformAdapter):
    platform = Platform.TELEGRAM

    def __init__(self):
        self.token = os.environ["TELEGRAM_BOT_TOKEN"]
        self.channel_id = os.environ["TELEGRAM_CHANNEL_ID"]

    def _call(self, method: str, data: dict, files: dict | None = None) -> dict:
        r = requests.post(API.format(token=self.token, method=method),
                          data=data, files=files, timeout=300)
        return r.json()

    def publish(self, post: Post) -> PublishResult:
        try:
            media = post.media[0] if post.media else None
            if media is None:
                resp = self._call("sendMessage",
                                  {"chat_id": self.channel_id, "text": post.text})
            else:
                method = "sendVideo" if media.type == MediaType.VIDEO else "sendPhoto"
                field = "video" if media.type == MediaType.VIDEO else "photo"
                data = {"chat_id": self.channel_id, "caption": post.text}
                if is_local_path(media.url):
                    with open(media.url, "rb") as f:
                        resp = self._call(method, data, files={field: f})
                else:
                    data[field] = media.url
                    resp = self._call(method, data)

            if not resp.get("ok"):
                return PublishResult(self.platform, ok=False, error=str(resp))
            message_id = resp["result"]["message_id"]
            return PublishResult(self.platform, ok=True, external_id=str(message_id))
        except Exception as e:  # noqa: BLE001
            return PublishResult(self.platform, ok=False, error=str(e))
