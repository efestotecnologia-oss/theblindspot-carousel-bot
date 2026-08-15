# Social Agent

Agente Python che **produce** contenuti video (script → voce → lip-sync) e li
**pubblica** su più piattaforme social tramite **API ufficiali**. Progettato per
partire con **approvazione manuale** e poi passare a **pubblicazione
completamente automatica** (cron) cambiando un flag.

## Stato

| Piattaforma | Adapter | Stato |
|---|---|---|
| Facebook Page | `platforms/meta.py` | ✅ pronto (credenziali Meta) |
| Instagram Business | `platforms/meta.py` | ✅ pronto (media singolo o carosello, URL pubblico) |
| Telegram (canale) | `platforms/telegram.py` | ✅ pronto (bot admin del canale) |
| X (Twitter) | `platforms/twitter.py` | ✅ codice pronto, credenziali da configurare |
| YouTube | `platforms/youtube.py` | ✅ codice pronto, OAuth da configurare |
| TikTok | `platforms/tiktok.py` | ⚠️ solo SELF_ONLY finché l'app non supera l'audit |

## Architettura

```
agents/     produzione: script (Claude) → voce (ElevenLabs) → video (Sync Labs + ffmpeg)
core/       modelli (Post), approvazioni, (scheduler/coda in arrivo)
platforms/  un adapter per social, interfaccia comune in base.py
content/    libreria contenuti (store locale JSON; sostituibile con Airtable/Notion)
            + uploader media (file locali → URL pubblici)
main.py     CLI / entry point
```

Aggiungere una piattaforma = un nuovo file in `platforms/` che eredita da
`PlatformAdapter`. Il resto del sistema non cambia.

## Avvio rapido

```bash
cd social-agent
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env                 # poi compila le credenziali Meta
cp content/posts.example.json content/posts.json

python main.py produce               # produce nuove bozze video (agents/)
python main.py list                  # elenca i post
python main.py preview post-001      # anteprima
python main.py approve post-001      # approva
python main.py run                   # pubblica i post approvati (con conferma)
python main.py run --auto            # pubblica senza conferma (modalità automatica)
python main.py run --dry-run --auto  # simula tutto, senza account/API
python main.py run --auto --loop --interval 900   # daemon: pubblica ogni 15 min
```

## Produzione contenuti (agents/)

`python main.py produce` esegue la pipeline completa e salva il risultato
come **bozza** nello store — niente va online senza approvazione:

1. **Script** (`agents/script_generator.py`): Claude Sonnet genera il testo
   30-60s secondo la persona del brand (tono definito una volta nel modulo).
   Argomenti: `--topic "..."` (ripetibile) o la lista `TOPICS` nel modulo.
2. **Voce** (`agents/voice_agent.py`): ElevenLabs trasforma lo script in mp3
   con la voce configurata (`ELEVENLABS_VOICE_ID`).
3. **Video** (`agents/video_editor.py`): Sync Labs sincronizza il labiale del
   footage base (`BASE_VIDEO_PATH`) col nuovo audio; ffmpeg imprime i
   sottotitoli e porta tutto a 1080x1920 (ok per Reels/Shorts/TikTok/Telegram).

Prerequisiti: `ANTHROPIC_API_KEY`, `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID`,
`SYNC_API_KEY`, `BASE_VIDEO_PATH`, un `MEDIA_UPLOADER` configurato (Sync Labs
legge i file da URL pubblici) e **ffmpeg** installato (`brew install ffmpeg`).

Le tre API di produzione sono **a pagamento/quota**: la didascalia e le
piattaforme di destinazione delle bozze si correggono nello store prima di
approvare, senza rigenerare il video.

## Caroselli Instagram (agents/carousel_*)

```bash
pip install -r requirements.txt
playwright install chromium      # una tantum: scarica Chromium headless

python main.py produce-carousel --topic "Il bias della conferma" --slides 5
python main.py preview carousel-...
python main.py approve carousel-...
python main.py run
```

Pipeline: `agents/carousel_copy.py` (Claude genera hook, slide di corpo e
CTA in formato JSON) → `agents/carousel_render.py` (ogni slide è un
template HTML/CSS in `templates/carousel/`, renderizzato in PNG 1080×1350
con Chromium headless) → upload di ogni PNG (vedi uploader sotto) → bozza
salvata come `Post` con un'immagine per slide, pubblicata come vero
carosello Instagram da `platforms/meta.py`.

Il design (`templates/carousel/style.css`) usa un cerchio ricorrente in
basso a destra — il "punto cieco" del brand: quasi pieno sulla prima
slide, si svuota progressivamente fino a diventare un anello vuoto
sull'ultima. Per cambiare tono/struttura del testo, modifica il prompt in
`agents/carousel_copy.py`; per cambiare il design, il CSS.

## Approvazione remota (Telegram)

Nella fase "con approvazione" puoi ricevere l'anteprima sul telefono e
rispondere con i pulsanti **Approva / Rifiuta**. Imposta nel `.env`:
`APPROVAL_CHANNEL=telegram`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`.

## Libreria contenuti: JSON o Airtable

Di default i post stanno in `content/posts.json`. In alternativa puoi usare
**Airtable** come calendario editoriale visuale (`CONTENT_STORE=airtable`).

Schema tabella: `PostId · Text · MediaUrls · Platforms · ScheduledAt · Status · Results`.
Il campo `MediaUrls` accetta un media per riga: `image:URL` / `video:URL`
(o solo URL, con tipo dedotto dall'estensione).

**Provarlo senza account** (dry-run): l'agente include un client Airtable finto.
```bash
cp content/airtable_fake.example.json content/airtable_fake.json
CONTENT_STORE=airtable AIRTABLE_FAKE=1 DRY_RUN=1 python main.py list
CONTENT_STORE=airtable AIRTABLE_FAKE=1 DRY_RUN=1 python main.py run --auto --dry-run
```

## Media locali → URL pubblici

Instagram/TikTok accettano solo URL pubblici. L'uploader converte i file
locali automaticamente. Nel `.env`: `MEDIA_UPLOADER=local` (copia in una
cartella del tuo web server) oppure `s3`. Se un media è già un URL, resta invariato.

## Configurazione credenziali

Vedi **[docs/SETUP_META.md](docs/SETUP_META.md)** per ottenere `FB_PAGE_ID`,
`FB_PAGE_ACCESS_TOKEN` e `IG_USER_ID`.

## Nota importante sui media

Instagram (e diversi endpoint) richiedono che immagini/video siano a un
**URL pubblico** — non accettano file locali. Per i media locali serve prima
caricarli su un hosting pubblico (uploader previsto in una fase successiva).

## Automazione (Fase finale)

Due opzioni sul server:

**Cron** (esegue e termina ogni 15 min):
```cron
*/15 * * * * cd /path/social-agent && ./.venv/bin/python main.py run --auto >> agent.log 2>&1
```

**Daemon** (processo sempre attivo, es. via systemd):
```bash
./.venv/bin/python main.py run --auto --loop --interval 900
```
