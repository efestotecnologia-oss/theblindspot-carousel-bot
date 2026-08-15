"""Store dei contenuti su Airtable.

Airtable diventa il "calendario editoriale" visuale: ogni riga (record) è un
post, con colonne per testo, media, piattaforme, data e stato di approvazione.

Espone la STESSA interfaccia di JSONStore (all/get/upsert/due_approved), quindi
il resto dell'agente non cambia.

Per poterlo testare SENZA un account Airtable reale, il mapping è isolato in
`AirtableStore` e la comunicazione passa per un "client" intercambiabile:
- `AirtableApiClient`  -> vere API REST di Airtable (richiede token).
- `FakeAirtableClient` -> simulazione in-memory su file JSON (per dry-run/test).

Schema tabella Airtable atteso (nomi colonne configurabili in cima al file):
  PostId (testo) · Text (testo lungo) · MediaUrls (testo, un media per riga:
  "image:URL" / "video:URL", oppure solo URL con tipo dedotto dall'estensione) ·
  Platforms (multi-select o testo: facebook,instagram,...) · ScheduledAt (data ISO) ·
  Status (single-select: draft/approved/scheduled/published/failed) · Results (testo, JSON).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Protocol

import requests

from core.models import Media, MediaType, Platform, Post, PostStatus

# --- nomi delle colonne Airtable (adattali se usi nomi diversi) ---
F_ID = "PostId"
F_TEXT = "Text"
F_MEDIA = "MediaUrls"
F_PLATFORMS = "Platforms"
F_SCHEDULED = "ScheduledAt"
F_STATUS = "Status"
F_RESULTS = "Results"

_VIDEO_EXT = (".mp4", ".mov", ".webm", ".m4v", ".avi")


# ======================================================================
# Client: astrazione minima sulle API Airtable (record = {"id", "fields"})
# ======================================================================
class AirtableClient(Protocol):
    def list_records(self) -> list[dict]: ...
    def create_record(self, fields: dict) -> dict: ...
    def update_record(self, record_id: str, fields: dict) -> dict: ...


class AirtableApiClient:
    """Client reale verso le API REST di Airtable."""

    def __init__(self, token: str, base_id: str, table: str):
        self.base = f"https://api.airtable.com/v0/{base_id}/{table}"
        self.headers = {"Authorization": f"Bearer {token}"}

    def list_records(self) -> list[dict]:
        records, offset = [], None
        while True:
            params = {"pageSize": 100}
            if offset:
                params["offset"] = offset
            r = requests.get(self.base, headers=self.headers, params=params, timeout=60)
            r.raise_for_status()
            data = r.json()
            records.extend(data.get("records", []))
            offset = data.get("offset")
            if not offset:
                return records

    def create_record(self, fields: dict) -> dict:
        r = requests.post(self.base, headers=self.headers, json={"fields": fields}, timeout=60)
        r.raise_for_status()
        return r.json()

    def update_record(self, record_id: str, fields: dict) -> dict:
        r = requests.patch(f"{self.base}/{record_id}", headers=self.headers,
                           json={"fields": fields}, timeout=60)
        r.raise_for_status()
        return r.json()


class FakeAirtableClient:
    """Simulazione in-memory delle API Airtable, persistita su file JSON.

    Serve a testare l'AirtableStore in dry-run, senza account. La struttura dei
    record ({"id", "fields"}) è la stessa restituita dalle vere API.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("[]", encoding="utf-8")

    def _load(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8") or "[]")

    def _save(self, records: list[dict]) -> None:
        self.path.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")

    def list_records(self) -> list[dict]:
        return self._load()

    def create_record(self, fields: dict) -> dict:
        records = self._load()
        rec = {"id": f"recFAKE{len(records):04d}", "fields": fields}
        records.append(rec)
        self._save(records)
        return rec

    def update_record(self, record_id: str, fields: dict) -> dict:
        records = self._load()
        for rec in records:
            if rec["id"] == record_id:
                rec["fields"].update(fields)
                self._save(records)
                return rec
        raise KeyError(f"record {record_id} inesistente")


# ======================================================================
# Mapping record Airtable <-> Post
# ======================================================================
def _infer_type(url: str) -> MediaType:
    return MediaType.VIDEO if url.lower().split("?")[0].endswith(_VIDEO_EXT) else MediaType.IMAGE


def _line_to_media(line: str) -> Media:
    if line.startswith("video:"):
        return Media(url=line[len("video:"):].strip(), type=MediaType.VIDEO)
    if line.startswith("image:"):
        return Media(url=line[len("image:"):].strip(), type=MediaType.IMAGE)
    return Media(url=line, type=_infer_type(line))


def _parse_media(value) -> list[Media]:
    if not value:
        return []
    if isinstance(value, list):  # es. campo Attachments di Airtable
        out = []
        for it in value:
            if isinstance(it, dict) and "url" in it:
                out.append(Media(url=it["url"], type=_infer_type(it["url"])))
            elif isinstance(it, str):
                out.append(_line_to_media(it.strip()))
        return out
    return [_line_to_media(x.strip()) for x in re.split(r"[\n,]", str(value)) if x.strip()]


def _parse_platforms(value) -> list[Platform]:
    if not value:
        return []
    items = value if isinstance(value, list) else re.split(r"[\n,]", str(value))
    return [Platform(x.strip().lower()) for x in items if x and x.strip()]


def record_to_post(record: dict) -> Post:
    f = record.get("fields", {})
    results = f.get(F_RESULTS)
    return Post(
        id=str(f.get(F_ID) or record["id"]),
        text=f.get(F_TEXT, ""),
        media=_parse_media(f.get(F_MEDIA)),
        platforms=_parse_platforms(f.get(F_PLATFORMS)),
        scheduled_at=(datetime.fromisoformat(f[F_SCHEDULED]) if f.get(F_SCHEDULED) else None),
        status=PostStatus(f.get(F_STATUS, "draft")),
        results=json.loads(results) if results else {},
    )


def post_to_fields(post: Post) -> dict:
    return {
        F_ID: post.id,
        F_TEXT: post.text,
        F_MEDIA: "\n".join(f"{m.type.value}:{m.url}" for m in post.media),
        F_PLATFORMS: ",".join(p.value for p in post.platforms),
        F_SCHEDULED: post.scheduled_at.isoformat() if post.scheduled_at else "",
        F_STATUS: post.status.value,
        F_RESULTS: json.dumps(post.results, ensure_ascii=False) if post.results else "",
    }


# ======================================================================
# Store
# ======================================================================
class AirtableStore:
    def __init__(self, client: AirtableClient):
        self.client = client

    def _records(self) -> list[dict]:
        return self.client.list_records()

    def all(self) -> list[Post]:
        return [record_to_post(r) for r in self._records()]

    def get(self, post_id: str) -> Post | None:
        return next((p for p in self.all() if p.id == post_id), None)

    def _record_id_for(self, post_id: str) -> str | None:
        for r in self._records():
            if str(r.get("fields", {}).get(F_ID) or r["id"]) == post_id:
                return r["id"]
        return None

    def upsert(self, post: Post) -> None:
        fields = post_to_fields(post)
        rec_id = self._record_id_for(post.id)
        if rec_id:
            self.client.update_record(rec_id, fields)
        else:
            self.client.create_record(fields)

    def due_approved(self) -> list[Post]:
        return [p for p in self.all()
                if p.status in (PostStatus.APPROVED, PostStatus.SCHEDULED) and p.is_due()]
