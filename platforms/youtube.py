"""Adapter YouTube — upload video via YouTube Data API v3.

Autenticazione: OAuth 2.0. Serve un token utente autorizzato sul canale.
Il primo post con YouTube su questo Post usa `text`: la PRIMA riga diventa il
titolo, il resto la descrizione.

Le librerie google-* sono importate in modo "lazy" così l'agente funziona
(dry-run e altre piattaforme) anche se non sono installate.

Doc: https://developers.google.com/youtube/v3/docs/videos/insert
"""

from __future__ import annotations

import os
import tempfile

import requests

from core.models import MediaType, Platform, Post, PublishResult
from platforms.base import PlatformAdapter

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


class YouTubeAdapter(PlatformAdapter):
    platform = Platform.YOUTUBE

    def __init__(self):
        # token OAuth salvato (generato una tantum dal flusso di autorizzazione)
        self.token_file = os.environ["YOUTUBE_TOKEN_FILE"]
        self.privacy = os.getenv("YOUTUBE_PRIVACY_STATUS", "private")

    def _service(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
        return build("youtube", "v3", credentials=creds)

    def publish(self, post: Post) -> PublishResult:
        videos = [m for m in post.media if m.type == MediaType.VIDEO]
        if not videos:
            return PublishResult(self.platform, ok=False,
                                 error="YouTube richiede un video.")
        try:
            from googleapiclient.http import MediaFileUpload

            title, _, description = post.text.partition("\n")
            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=True) as tmp:
                self._download(videos[0].url, tmp.name)
                body = {
                    "snippet": {"title": title[:100] or "Nuovo video", "description": description},
                    "status": {"privacyStatus": self.privacy},
                }
                media = MediaFileUpload(tmp.name, chunksize=-1, resumable=True)
                request = self._service().videos().insert(
                    part="snippet,status", body=body, media_body=media)
                response = request.execute()

            vid = response["id"]
            return PublishResult(self.platform, ok=True, external_id=vid,
                                 url=f"https://youtu.be/{vid}")
        except Exception as e:  # noqa: BLE001
            return PublishResult(self.platform, ok=False, error=str(e))

    @staticmethod
    def _download(url: str, dest: str) -> None:
        with requests.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
