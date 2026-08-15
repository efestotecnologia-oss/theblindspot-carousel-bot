"""Uploader media: trasforma file LOCALI in URL PUBBLICI.

Instagram e TikTok non accettano upload diretti di file: vogliono un URL
pubblico. Questo modulo carica un file locale su un hosting e restituisce
l'URL raggiungibile.

Implementazioni (scelte via env MEDIA_UPLOADER):
- "local":  copia il file in una cartella servita dal tuo web server e
            costruisce l'URL pubblico (ideale dato che hai già un server).
- "s3":     carica su un bucket S3 / S3-compatibile (richiede boto3).
- "github": copia il file in una cartella del repo git, fa commit+push e
            restituisce l'URL raw.githubusercontent.com. Pensato per la
            Routine cloud: niente server/bucket da gestire, il repo
            pubblico stesso fa da hosting delle immagini.
- assente: nessun uploader (i media devono già essere URL pubblici).

È "pluggable": aggiungere Cloudinary/altro = una nuova classe con `upload()`.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from core.models import Media, Post


def is_local_path(url: str) -> bool:
    """True se `url` è un percorso di file locale (non http/https)."""
    return not url.lower().startswith(("http://", "https://"))


class MediaUploader(ABC):
    @abstractmethod
    def upload(self, local_path: str) -> str:
        """Carica il file e restituisce l'URL pubblico."""
        raise NotImplementedError


class LocalPublicDirUploader(MediaUploader):
    """Copia il file in una cartella pubblica servita dal tuo web server.

    Es.: public_dir=/var/www/media, base_url=https://tuosito.com/media
    -> un file finisce in /var/www/media/<hash>-<nome> ed è pubblicato a
       https://tuosito.com/media/<hash>-<nome>
    """

    def __init__(self, public_dir: str, base_url: str):
        self.public_dir = Path(public_dir)
        self.base_url = base_url.rstrip("/")
        self.public_dir.mkdir(parents=True, exist_ok=True)

    def upload(self, local_path: str) -> str:
        src = Path(local_path)
        if not src.exists():
            raise FileNotFoundError(f"File media non trovato: {local_path}")
        digest = hashlib.sha1(src.read_bytes()).hexdigest()[:12]
        name = f"{digest}-{src.name}"
        dest = self.public_dir / name
        if not dest.exists():
            shutil.copy2(src, dest)
        return f"{self.base_url}/{name}"


class S3Uploader(MediaUploader):
    """Carica su S3 (o compatibile). boto3 importato in modo lazy."""

    def __init__(self, bucket: str, prefix: str = "", base_url: str | None = None,
                 region: str | None = None):
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.base_url = base_url.rstrip("/") if base_url else None
        self.region = region

    def upload(self, local_path: str) -> str:
        import boto3  # lazy
        src = Path(local_path)
        digest = hashlib.sha1(src.read_bytes()).hexdigest()[:12]
        key = "/".join(p for p in (self.prefix, f"{digest}-{src.name}") if p)
        boto3.client("s3", region_name=self.region).upload_file(str(src), self.bucket, key)
        if self.base_url:
            return f"{self.base_url}/{key}"
        region = self.region or "us-east-1"
        return f"https://{self.bucket}.s3.{region}.amazonaws.com/{key}"


class GitHubRawUploader(MediaUploader):
    """Copia il file in una cartella del repo git, fa commit+push e
    restituisce l'URL raw.githubusercontent.com.

    Presuppone che il processo giri già dentro il checkout del repo (vero
    per la Routine cloud) e che `git push` funzioni senza intervento
    (credenziali già configurate nell'ambiente di esecuzione).
    """

    def __init__(self, repo: str, branch: str = "main", subdir: str = "public/carousels",
                 repo_root: str | None = None):
        self.repo = repo  # "owner/nome-repo"
        self.branch = branch
        self.repo_root = Path(repo_root) if repo_root else Path.cwd()
        self.dest_dir = self.repo_root / subdir
        self.subdir = subdir.strip("/")
        self.dest_dir.mkdir(parents=True, exist_ok=True)

    def upload(self, local_path: str) -> str:
        import subprocess

        src = Path(local_path)
        if not src.exists():
            raise FileNotFoundError(f"File media non trovato: {local_path}")
        digest = hashlib.sha1(src.read_bytes()).hexdigest()[:12]
        name = f"{digest}-{src.name}"
        dest = self.dest_dir / name
        rel_path = f"{self.subdir}/{name}"

        if not dest.exists():
            shutil.copy2(src, dest)
            subprocess.run(["git", "add", rel_path], cwd=self.repo_root, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"carousel: aggiungi {name}"],
                cwd=self.repo_root, check=True,
            )
            subprocess.run(["git", "push", "origin", self.branch],
                          cwd=self.repo_root, check=True)

        return f"https://raw.githubusercontent.com/{self.repo}/{self.branch}/{rel_path}"


def get_uploader() -> MediaUploader | None:
    """Costruisce l'uploader configurato via env, o None se non configurato."""
    kind = os.getenv("MEDIA_UPLOADER", "").lower()
    if kind == "local":
        return LocalPublicDirUploader(os.environ["MEDIA_LOCAL_DIR"],
                                      os.environ["MEDIA_BASE_URL"])
    if kind == "s3":
        return S3Uploader(os.environ["MEDIA_S3_BUCKET"],
                          os.getenv("MEDIA_S3_PREFIX", ""),
                          os.getenv("MEDIA_BASE_URL"),
                          os.getenv("MEDIA_S3_REGION"))
    if kind == "github":
        return GitHubRawUploader(os.environ["MEDIA_GITHUB_REPO"],
                                 os.getenv("MEDIA_GITHUB_BRANCH", "main"),
                                 os.getenv("MEDIA_GITHUB_DIR", "public/carousels"))
    return None


def ensure_public_urls(post: Post, uploader: MediaUploader | None) -> list[str]:
    """Sostituisce i media locali con URL pubblici (in-place).

    Restituisce l'elenco degli avvisi (media locali senza uploader).
    """
    warnings: list[str] = []
    new_media: list[Media] = []
    for m in post.media:
        if is_local_path(m.url):
            if uploader is None:
                warnings.append(
                    f"media locale '{m.url}' ma nessun uploader configurato "
                    "(Instagram/TikTok lo rifiuteranno)."
                )
                new_media.append(m)
            else:
                new_media.append(Media(url=uploader.upload(m.url), type=m.type))
        else:
            new_media.append(m)
    post.media = new_media
    return warnings
