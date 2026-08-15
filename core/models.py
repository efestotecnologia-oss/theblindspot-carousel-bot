"""Modelli dati condivisi da tutto l'agente.

Un `Post` è l'unità di contenuto "prestabilito" che l'agente pubblica.
Non dipende da nessuna piattaforma specifica: sono gli adapter in
`platforms/` a tradurlo nelle chiamate API di ciascun social.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional


class Platform(str, Enum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    TELEGRAM = "telegram"


class MediaType(str, Enum):
    IMAGE = "image"
    VIDEO = "video"


class PostStatus(str, Enum):
    DRAFT = "draft"            # bozza, non ancora approvata
    APPROVED = "approved"      # approvata, pronta per la pubblicazione pianificata
    PUBLISHED = "published"    # pubblicata con successo (su almeno una piattaforma)
    FAILED = "failed"          # errore in pubblicazione
    SCHEDULED = "scheduled"    # approvata + con data futura


@dataclass
class Media:
    """Un media allegato al post.

    IMPORTANTE: Instagram (e alcuni endpoint) richiedono un URL PUBBLICO,
    non accettano upload di file locali. Per i media locali serve prima
    caricarli su un hosting pubblico (vedi TODO uploader).
    """
    url: str
    type: MediaType = MediaType.IMAGE

    def to_dict(self) -> dict:
        return {"url": self.url, "type": self.type.value}

    @classmethod
    def from_dict(cls, d: dict) -> "Media":
        return cls(url=d["url"], type=MediaType(d.get("type", "image")))


@dataclass
class Post:
    id: str
    text: str = ""                       # didascalia / messaggio
    media: list[Media] = field(default_factory=list)
    platforms: list[Platform] = field(default_factory=list)
    scheduled_at: Optional[datetime] = None
    status: PostStatus = PostStatus.DRAFT
    # esito per piattaforma: { "facebook": {"ok": true, "id": "..."} }
    results: dict = field(default_factory=dict)

    def is_due(self, now: Optional[datetime] = None) -> bool:
        """True se è ora di pubblicarlo (nessuna data = subito)."""
        if self.scheduled_at is None:
            return True
        return (now or datetime.now()) >= self.scheduled_at

    def to_dict(self) -> dict:
        d = asdict(self)
        d["media"] = [m.to_dict() for m in self.media]
        d["platforms"] = [p.value for p in self.platforms]
        d["status"] = self.status.value
        d["scheduled_at"] = self.scheduled_at.isoformat() if self.scheduled_at else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Post":
        return cls(
            id=d["id"],
            text=d.get("text", ""),
            media=[Media.from_dict(m) for m in d.get("media", [])],
            platforms=[Platform(p) for p in d.get("platforms", [])],
            scheduled_at=(
                datetime.fromisoformat(d["scheduled_at"])
                if d.get("scheduled_at") else None
            ),
            status=PostStatus(d.get("status", "draft")),
            results=d.get("results", {}),
        )


@dataclass
class PublishResult:
    """Esito della pubblicazione su una singola piattaforma."""
    platform: Platform
    ok: bool
    external_id: Optional[str] = None   # id del post creato sul social
    url: Optional[str] = None           # link pubblico al post, se disponibile
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "external_id": self.external_id,
            "url": self.url,
            "error": self.error,
        }
