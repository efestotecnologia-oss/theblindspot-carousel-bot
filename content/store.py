"""Store dei contenuti — versione locale a file JSON.

È volutamente semplice e "pluggable": in futuro basta scrivere un altro
store con gli stessi metodi (es. AirtableStore, NotionStore, SheetsStore)
per spostare la libreria contenuti su uno strumento visuale, senza
toccare il resto del sistema.
"""

from __future__ import annotations

import json
from pathlib import Path

from core.models import Post, PostStatus

DEFAULT_PATH = Path(__file__).parent / "posts.json"


class JSONStore:
    def __init__(self, path: Path | str = DEFAULT_PATH):
        self.path = Path(path)
        if not self.path.exists():
            self.path.write_text("[]", encoding="utf-8")

    def _load_raw(self) -> list[dict]:
        return json.loads(self.path.read_text(encoding="utf-8") or "[]")

    def _save_raw(self, rows: list[dict]) -> None:
        self.path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    def all(self) -> list[Post]:
        return [Post.from_dict(r) for r in self._load_raw()]

    def get(self, post_id: str) -> Post | None:
        return next((p for p in self.all() if p.id == post_id), None)

    def upsert(self, post: Post) -> None:
        rows = self._load_raw()
        rows = [r for r in rows if r["id"] != post.id]
        rows.append(post.to_dict())
        self._save_raw(rows)

    def due_approved(self) -> list[Post]:
        """Post approvati e la cui data di pubblicazione è arrivata."""
        return [p for p in self.all()
                if p.status in (PostStatus.APPROVED, PostStatus.SCHEDULED) and p.is_due()]
