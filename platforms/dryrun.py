"""Adapter di simulazione (dry-run).

Non chiama nessuna API: stampa cosa *verrebbe* pubblicato e restituisce
sempre successo. Serve a sviluppare e testare l'intera pipeline
(coda, approvazione, stati, scheduler) SENZA account reali.

Si attiva impostando DRY_RUN=1 nell'ambiente o con `main.py run --dry-run`.
"""

from __future__ import annotations

import uuid

from core.models import Platform, Post, PublishResult
from platforms.base import PlatformAdapter


class DryRunAdapter(PlatformAdapter):
    def __init__(self, platform: Platform):
        self.platform = platform

    def publish(self, post: Post) -> PublishResult:
        media = ", ".join(f"{m.type.value}:{m.url}" for m in post.media) or "nessun media"
        print(f"    [DRY-RUN {self.platform.value}] testo={post.text[:60]!r} media=({media})")
        fake_id = f"dryrun-{self.platform.value}-{uuid.uuid4().hex[:8]}"
        return PublishResult(self.platform, ok=True, external_id=fake_id,
                             url=f"https://example.com/{fake_id}")
