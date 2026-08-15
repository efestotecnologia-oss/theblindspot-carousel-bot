"""Entry point / CLI dell'agente social.

Comandi:
  python main.py produce              produce nuovi contenuti (script → voce →
                                      video) e li salva come bozze nello store
  python main.py produce --topic "…"  produce su argomenti specifici (ripetibile)
  python main.py produce-carousel --topic "…" [--slides N]
                                      produce un carosello Instagram (copy →
                                      slide PNG) e lo salva come bozza
  python main.py list                 elenca i post nello store
  python main.py preview <id>         mostra l'anteprima di un post
  python main.py approve <id>         segna un post come APPROVED
  python main.py run [--auto]         pubblica i post approvati e "in scadenza"
                                      (senza --auto chiede conferma per ciascuno)
  python main.py run --auto --loop    modalità daemon: pubblica in automatico
                                      a intervalli regolari (per il server)

La differenza tra "con approvazione" e "completamente automatico" è
il solo flag --auto; --loop lo fa girare in continuo (alternativa al cron).
"""

from __future__ import annotations

import argparse
import logging
import os
import time

from dotenv import load_dotenv

from content.factory import ContentStore, get_store
from content.uploader import ensure_public_urls, get_uploader
from core.approvals import get_approver, preview
from core.models import Platform, PostStatus
from platforms.base import PlatformAdapter

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(os.getenv("AGENT_LOG", "agent.log"))],
)
log = logging.getLogger("social-agent")


def _build_adapters(dry_run: bool = False) -> dict[Platform, PlatformAdapter]:
    """Istanzia gli adapter disponibili.

    - dry_run: ogni piattaforma è simulata (nessuna API, nessun account).
    - altrimenti: attiva ogni adapter solo se le sue credenziali sono nel .env.
    """
    if dry_run or os.getenv("DRY_RUN") in ("1", "true", "True"):
        from platforms.dryrun import DryRunAdapter
        return {p: DryRunAdapter(p) for p in Platform}

    adapters: dict[Platform, PlatformAdapter] = {}

    def _try(label, fn):
        try:
            fn(adapters)
        except Exception as e:  # noqa: BLE001
            print(f"[warn] adapter {label} non inizializzato: {e}")

    # Meta (Facebook + Instagram)
    def _meta(a):
        from platforms.meta import FacebookAdapter, InstagramAdapter
        if os.getenv("FB_PAGE_ID"):
            a[Platform.FACEBOOK] = FacebookAdapter()
        if os.getenv("IG_USER_ID"):
            a[Platform.INSTAGRAM] = InstagramAdapter()
    _try("Meta", _meta)

    # X (Twitter)
    def _tw(a):
        if os.getenv("TWITTER_API_KEY"):
            from platforms.twitter import TwitterAdapter
            a[Platform.TWITTER] = TwitterAdapter()
    _try("X/Twitter", _tw)

    # YouTube
    def _yt(a):
        if os.getenv("YOUTUBE_TOKEN_FILE"):
            from platforms.youtube import YouTubeAdapter
            a[Platform.YOUTUBE] = YouTubeAdapter()
    _try("YouTube", _yt)

    # TikTok
    def _tk(a):
        if os.getenv("TIKTOK_ACCESS_TOKEN"):
            from platforms.tiktok import TikTokAdapter
            a[Platform.TIKTOK] = TikTokAdapter()
    _try("TikTok", _tk)

    # Telegram (canale)
    def _tg(a):
        if os.getenv("TELEGRAM_CHANNEL_ID"):
            from platforms.telegram import TelegramAdapter
            a[Platform.TELEGRAM] = TelegramAdapter()
    _try("Telegram", _tg)

    return adapters


def cmd_produce(store: ContentStore, topics: list[str] | None) -> None:
    from agents.produce import produce
    try:
        posts = produce(store, topics)
    except RuntimeError as e:
        print(f"Produzione interrotta: {e}")
        return
    print(f"\nProdotte {len(posts)} bozze:")
    for p in posts:
        print(f"  {p.id}  {p.text.splitlines()[0][:60]!r}")
    print("\nOra: python main.py preview <id> → approve <id> → run")


def cmd_produce_carousel(store: ContentStore, topics: list[str] | None,
                          n_slides: int) -> None:
    from agents.produce_carousel import produce_carousel
    try:
        posts = produce_carousel(store, topics, n_body_slides=n_slides)
    except RuntimeError as e:
        print(f"Produzione interrotta: {e}")
        return
    print(f"\nProdotti {len(posts)} caroselli:")
    for p in posts:
        print(f"  {p.id}  {len(p.media)} slide  {p.text.splitlines()[0][:60]!r}")
    print("\nOra: python main.py preview <id> → approve <id> → run")


def cmd_list(store: ContentStore) -> None:
    posts = store.all()
    if not posts:
        print("Nessun post nello store. Aggiungine in content/posts.json")
        return
    for p in posts:
        plats = ",".join(pl.value for pl in p.platforms)
        print(f"{p.id:<16} [{p.status.value:<9}] {plats:<28} {p.text[:40]!r}")


def cmd_preview(store: ContentStore, post_id: str) -> None:
    post = store.get(post_id)
    print(preview(post) if post else f"Post {post_id} non trovato.")


def cmd_approve(store: ContentStore, post_id: str) -> None:
    post = store.get(post_id)
    if not post:
        print(f"Post {post_id} non trovato.")
        return
    post.status = PostStatus.SCHEDULED if post.scheduled_at else PostStatus.APPROVED
    store.upsert(post)
    print(f"Post {post_id} → {post.status.value}")


def _publish_post(store, adapters, post, uploader, dry_run) -> bool:
    """Pubblica un post su tutte le sue piattaforme. True se almeno una riesce."""
    if not dry_run:
        for w in ensure_public_urls(post, uploader):
            log.warning("  ⚠ %s: %s", post.id, w)

    any_ok = False
    for platform in post.platforms:
        adapter = adapters.get(platform)
        if not adapter:
            log.warning("  ⚠ %s: adapter non configurato, salto.", platform.value)
            continue
        result = adapter.publish(post)
        post.results[platform.value] = result.to_dict()
        if result.ok:
            any_ok = True
            log.info("  ✅ %s: pubblicato (%s)", platform.value, result.external_id)
        else:
            log.error("  ❌ %s: %s", platform.value, result.error)

    post.status = PostStatus.PUBLISHED if any_ok else PostStatus.FAILED
    store.upsert(post)
    return any_ok


def _run_once(store, adapters, approver, auto, dry_run) -> int:
    """Un ciclo: pubblica i post approvati e in scadenza. Ritorna quanti elaborati."""
    uploader = None if dry_run else get_uploader()
    due = store.due_approved()
    if not due:
        log.info("Nessun post approvato e in scadenza.")
        return 0
    processed = 0
    for post in due:
        if not auto and not approver.request(post):
            log.info("  ⏭  %s saltato (non approvato).", post.id)
            continue
        _publish_post(store, adapters, post, uploader, dry_run)
        processed += 1
    return processed


def cmd_run(store: ContentStore, auto: bool, dry_run: bool = False,
            loop: bool = False, interval: int = 900) -> None:
    adapters = _build_adapters(dry_run=dry_run)
    if not adapters:
        log.error("Nessun adapter configurato. Compila il file .env (vedi .env.example).")
        return
    approver = get_approver()

    if not loop:
        _run_once(store, adapters, approver, auto, dry_run)
        return

    log.info("Daemon avviato: ciclo ogni %ss. Ctrl+C per fermare.", interval)
    while True:
        try:
            _run_once(store, adapters, approver, auto, dry_run)
        except Exception as e:  # noqa: BLE001
            log.exception("Errore nel ciclo di pubblicazione: %s", e)
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description="Agente di pubblicazione social")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_prod = sub.add_parser("produce")
    p_prod.add_argument("--topic", action="append", dest="topics", metavar="TOPIC",
                        help="argomento su cui produrre (ripetibile); default: "
                             "lista TOPICS in agents/script_generator.py")
    p_car = sub.add_parser("produce-carousel")
    p_car.add_argument("--topic", action="append", dest="topics", metavar="TOPIC",
                       required=True, help="argomento del carosello (ripetibile)")
    p_car.add_argument("--slides", type=int, default=5, dest="n_slides",
                       help="numero di slide di corpo (oltre a hook e CTA), default 5")
    sub.add_parser("list")
    p_prev = sub.add_parser("preview"); p_prev.add_argument("id")
    p_appr = sub.add_parser("approve"); p_appr.add_argument("id")
    p_run = sub.add_parser("run")
    p_run.add_argument("--auto", action="store_true", help="pubblica senza chiedere conferma")
    p_run.add_argument("--dry-run", action="store_true", help="simula tutto, senza API/account")
    p_run.add_argument("--loop", action="store_true", help="modalità daemon: ripete a intervalli")
    p_run.add_argument("--interval", type=int, default=900, help="secondi tra i cicli in --loop")

    args = parser.parse_args()
    store = get_store()

    if args.cmd == "produce":
        cmd_produce(store, args.topics)
    elif args.cmd == "produce-carousel":
        cmd_produce_carousel(store, args.topics, args.n_slides)
    elif args.cmd == "list":
        cmd_list(store)
    elif args.cmd == "preview":
        cmd_preview(store, args.id)
    elif args.cmd == "approve":
        cmd_approve(store, args.id)
    elif args.cmd == "run":
        cmd_run(store, auto=args.auto, dry_run=args.dry_run,
                loop=args.loop, interval=args.interval)


if __name__ == "__main__":
    main()
