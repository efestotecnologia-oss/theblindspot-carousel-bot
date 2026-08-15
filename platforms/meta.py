"""Adapter Meta: Facebook Page + Instagram Business, via Graph API.

Una sola app Meta copre entrambe le piattaforme. Servono:
- FACEBOOK: PAGE_ID + PAGE_ACCESS_TOKEN (token long-lived della Pagina)
- INSTAGRAM: IG_USER_ID (account IG Business collegato alla Pagina) + lo stesso token

Doc: https://developers.facebook.com/docs/graph-api  |  .../instagram-api/guides/content-publishing
"""

from __future__ import annotations

import os
import time

import requests

from core.models import MediaType, Platform, Post, PublishResult
from platforms.base import PlatformAdapter

GRAPH_VERSION = os.getenv("GRAPH_API_VERSION", "v21.0")
GRAPH = f"https://graph.facebook.com/{GRAPH_VERSION}"


class _GraphMixin:
    def _post(self, path: str, params: dict) -> dict:
        r = requests.post(f"{GRAPH}/{path}", data={**params, "access_token": self.token}, timeout=60)
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        return data

    def _get(self, path: str, params: dict) -> dict:
        r = requests.get(f"{GRAPH}/{path}", params={**params, "access_token": self.token}, timeout=60)
        data = r.json()
        if "error" in data:
            raise RuntimeError(data["error"].get("message", str(data["error"])))
        return data


class FacebookAdapter(_GraphMixin, PlatformAdapter):
    platform = Platform.FACEBOOK

    def __init__(self, page_id: str | None = None, token: str | None = None):
        self.page_id = page_id or os.environ["FB_PAGE_ID"]
        self.token = token or os.environ["FB_PAGE_ACCESS_TOKEN"]

    def publish(self, post: Post) -> PublishResult:
        try:
            images = [m for m in post.media if m.type == MediaType.IMAGE]
            videos = [m for m in post.media if m.type == MediaType.VIDEO]

            if videos:
                # Video su Pagina (per i Reels serve l'API resumable dedicata — TODO)
                res = self._post(f"{self.page_id}/videos", {
                    "file_url": videos[0].url,
                    "description": post.text,
                })
                pid = res.get("id", "")
            elif len(images) == 1:
                res = self._post(f"{self.page_id}/photos", {
                    "url": images[0].url,
                    "caption": post.text,
                })
                pid = res.get("post_id") or res.get("id", "")
            elif len(images) > 1:
                # Post multi-foto: carica le foto come non pubblicate, poi le allega al feed
                media_ids = []
                for img in images:
                    up = self._post(f"{self.page_id}/photos", {"url": img.url, "published": "false"})
                    media_ids.append(up["id"])
                attached = {f"attached_media[{i}]": f'{{"media_fbid":"{mid}"}}'
                            for i, mid in enumerate(media_ids)}
                res = self._post(f"{self.page_id}/feed", {"message": post.text, **attached})
                pid = res.get("id", "")
            else:
                # Solo testo
                res = self._post(f"{self.page_id}/feed", {"message": post.text})
                pid = res.get("id", "")

            return PublishResult(self.platform, ok=True, external_id=pid,
                                 url=f"https://facebook.com/{pid}")
        except Exception as e:  # noqa: BLE001 — errori API incapsulati per la coda
            return PublishResult(self.platform, ok=False, error=str(e))


class InstagramAdapter(_GraphMixin, PlatformAdapter):
    platform = Platform.INSTAGRAM

    def __init__(self, ig_user_id: str | None = None, token: str | None = None):
        self.ig_user_id = ig_user_id or os.environ["IG_USER_ID"]
        self.token = token or os.environ["FB_PAGE_ACCESS_TOKEN"]

    def publish(self, post: Post) -> PublishResult:
        # Instagram richiede almeno un media, con URL PUBBLICO.
        if not post.media:
            return PublishResult(self.platform, ok=False,
                                 error="Instagram richiede almeno un'immagine o un video (con URL pubblico).")
        try:
            images = [m for m in post.media if m.type == MediaType.IMAGE]
            if len(images) > 1:
                creation_id = self._create_carousel_container(images, post.text)
            else:
                media = post.media[0]
                if media.type == MediaType.VIDEO:
                    container = self._post(f"{self.ig_user_id}/media", {
                        "media_type": "REELS",
                        "video_url": media.url,
                        "caption": post.text,
                    })
                else:
                    container = self._post(f"{self.ig_user_id}/media", {
                        "image_url": media.url,
                        "caption": post.text,
                    })
                creation_id = container["id"]
                # I video vanno "processati": attendiamo lo stato FINISHED prima di pubblicare.
                self._wait_ready(creation_id)

            res = self._post(f"{self.ig_user_id}/media_publish", {"creation_id": creation_id})
            pid = res.get("id", "")
            return PublishResult(self.platform, ok=True, external_id=pid)
        except Exception as e:  # noqa: BLE001
            return PublishResult(self.platform, ok=False, error=str(e))

    def _create_carousel_container(self, images: list, caption: str) -> str:
        """Crea un container CAROUSEL: un container per ogni immagine
        (is_carousel_item=true), poi il container padre con i figli.
        Instagram supporta da 2 a 10 elementi per carosello.
        """
        if len(images) > 10:
            raise RuntimeError(
                f"Instagram accetta al massimo 10 immagini per carosello ({len(images)} fornite)."
            )
        item_ids = []
        for img in images:
            item = self._post(f"{self.ig_user_id}/media", {
                "image_url": img.url,
                "is_carousel_item": "true",
            })
            self._wait_ready(item["id"])
            item_ids.append(item["id"])

        parent = self._post(f"{self.ig_user_id}/media", {
            "media_type": "CAROUSEL",
            "children": ",".join(item_ids),
            "caption": caption,
        })
        # Anche il container padre va atteso: pubblicarlo subito dopo la
        # creazione (senza controllare status_code) restituisce spesso
        # "Media ID is not available" perché non è ancora elaborato.
        self._wait_ready(parent["id"])
        return parent["id"]

    def _wait_ready(self, creation_id: str, attempts: int = 30, delay: float = 5.0) -> None:
        for _ in range(attempts):
            status = self._get(creation_id, {"fields": "status_code"})
            code = status.get("status_code")
            if code == "FINISHED":
                return
            if code == "ERROR":
                raise RuntimeError("Instagram: elaborazione media fallita (status ERROR).")
            time.sleep(delay)
        raise RuntimeError("Instagram: timeout in attesa dell'elaborazione del media.")
