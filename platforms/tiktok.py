"""Adapter TikTok — Content Posting API (PULL_FROM_URL).

Autenticazione: OAuth 2.0 (Bearer access token dell'utente).
Il video viene "tirato" da un URL PUBBLICO da TikTok.

⚠️ Finché l'app non supera l'audit di TikTok, i post possono essere solo
privati (SELF_ONLY). Il campo privacy è configurabile via env.

Doc: https://developers.tiktok.com/doc/content-posting-api-get-started
"""

from __future__ import annotations

import os
import time

import requests

from core.models import MediaType, Platform, Post, PublishResult
from platforms.base import PlatformAdapter

INIT_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"
STATUS_URL = "https://open.tiktokapis.com/v2/post/publish/status/fetch/"


class TikTokAdapter(PlatformAdapter):
    platform = Platform.TIKTOK

    def __init__(self):
        self.access_token = os.environ["TIKTOK_ACCESS_TOKEN"]
        self.privacy = os.getenv("TIKTOK_PRIVACY_LEVEL", "SELF_ONLY")

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8",
        }

    def publish(self, post: Post) -> PublishResult:
        videos = [m for m in post.media if m.type == MediaType.VIDEO]
        if not videos:
            return PublishResult(self.platform, ok=False, error="TikTok richiede un video.")
        try:
            payload = {
                "post_info": {
                    "title": post.text[:150],
                    "privacy_level": self.privacy,
                },
                "source_info": {
                    "source": "PULL_FROM_URL",
                    "video_url": videos[0].url,
                },
            }
            r = requests.post(INIT_URL, headers=self._headers(), json=payload, timeout=60)
            data = r.json()
            if data.get("error", {}).get("code") not in (None, "ok"):
                return PublishResult(self.platform, ok=False, error=str(data["error"]))
            publish_id = data["data"]["publish_id"]

            status = self._wait(publish_id)
            return PublishResult(self.platform, ok=True, external_id=publish_id,
                                 url=None if status != "PUBLISH_COMPLETE" else None)
        except Exception as e:  # noqa: BLE001
            return PublishResult(self.platform, ok=False, error=str(e))

    def _wait(self, publish_id: str, attempts: int = 30, delay: float = 5.0) -> str:
        for _ in range(attempts):
            r = requests.post(STATUS_URL, headers=self._headers(),
                              json={"publish_id": publish_id}, timeout=60)
            status = r.json().get("data", {}).get("status", "")
            if status in ("PUBLISH_COMPLETE", "FAILED"):
                if status == "FAILED":
                    raise RuntimeError("TikTok: pubblicazione fallita.")
                return status
            time.sleep(delay)
        raise RuntimeError("TikTok: timeout in attesa della pubblicazione.")
