"""Selettore dello store dei contenuti.

Configurabile via env CONTENT_STORE:
- "json"     (default) -> file locale content/posts.json
- "airtable"           -> Airtable. Con AIRTABLE_FAKE=1 usa il client finto
                          (in-memory su file) per testare in dry-run senza account.
"""

from __future__ import annotations

import os
from typing import Protocol

from core.models import Post


class ContentStore(Protocol):
    def all(self) -> list[Post]: ...
    def get(self, post_id: str) -> Post | None: ...
    def upsert(self, post: Post) -> None: ...
    def due_approved(self) -> list[Post]: ...


def get_store() -> ContentStore:
    kind = os.getenv("CONTENT_STORE", "json").lower()

    if kind == "airtable":
        from content.airtable_store import (
            AirtableApiClient, AirtableStore, FakeAirtableClient,
        )
        if os.getenv("AIRTABLE_FAKE") in ("1", "true", "True"):
            client = FakeAirtableClient(
                os.getenv("AIRTABLE_FAKE_FILE", "content/airtable_fake.json"))
        else:
            client = AirtableApiClient(
                os.environ["AIRTABLE_TOKEN"],
                os.environ["AIRTABLE_BASE_ID"],
                os.getenv("AIRTABLE_TABLE", "Posts"),
            )
        return AirtableStore(client)

    from content.store import JSONStore
    return JSONStore()
