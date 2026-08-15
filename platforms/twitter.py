"""Adapter X (Twitter) — API v2 per il testo, v1.1 per l'upload media.

Autenticazione: OAuth 1.0a user context (le 4 chiavi dell'app + access token
dell'account che pubblica). Richiede un piano a pagamento (Basic) per volumi utili.

Doc: https://developer.twitter.com/en/docs/twitter-api
"""

from __future__ import annotations

import os

import requests
from requests_oauthlib import OAuth1

from core.models import MediaType, Platform, Post, PublishResult
from platforms.base import PlatformAdapter

TWEETS_URL = "https://api.twitter.com/2/tweets"
MEDIA_UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"


class TwitterAdapter(PlatformAdapter):
    platform = Platform.TWITTER

    def __init__(self):
        self.auth = OAuth1(
            os.environ["TWITTER_API_KEY"],
            os.environ["TWITTER_API_SECRET"],
            os.environ["TWITTER_ACCESS_TOKEN"],
            os.environ["TWITTER_ACCESS_SECRET"],
        )

    def publish(self, post: Post) -> PublishResult:
        try:
            media_ids: list[str] = []
            for m in post.media:
                if m.type == MediaType.VIDEO:
                    # L'upload video richiede il flusso chunked INIT/APPEND/FINALIZE — TODO
                    return PublishResult(self.platform, ok=False,
                                         error="X: upload video non ancora supportato (previsto).")
                media_ids.append(self._upload_image(m.url))

            payload: dict = {"text": post.text}
            if media_ids:
                payload["media"] = {"media_ids": media_ids}

            r = requests.post(TWEETS_URL, auth=self.auth, json=payload, timeout=60)
            data = r.json()
            if r.status_code >= 300 or "data" not in data:
                return PublishResult(self.platform, ok=False, error=str(data))
            tid = data["data"]["id"]
            return PublishResult(self.platform, ok=True, external_id=tid,
                                 url=f"https://x.com/i/web/status/{tid}")
        except Exception as e:  # noqa: BLE001
            return PublishResult(self.platform, ok=False, error=str(e))

    def _upload_image(self, url: str) -> str:
        """Scarica l'immagine dall'URL pubblico e la carica su X (simple upload)."""
        img = requests.get(url, timeout=60)
        img.raise_for_status()
        up = requests.post(MEDIA_UPLOAD_URL, auth=self.auth,
                           files={"media": img.content}, timeout=120)
        up_data = up.json()
        if "media_id_string" not in up_data:
            raise RuntimeError(f"X upload media fallito: {up_data}")
        return up_data["media_id_string"]
