# Setup Meta (Facebook + Instagram)

Questa è la parte "lavoro iniziale attento": configurare l'app Meta e ottenere i
token. Va fatta **una sola volta**. Una app copre sia Facebook che Instagram.

## Prerequisiti (dovresti già averli)
- Una **Pagina Facebook**.
- Un account **Instagram Business** o **Creator** collegato alla Pagina.
- Un profilo su [Meta for Developers](https://developers.facebook.com/).

## 1. Crea l'app Meta
1. Vai su https://developers.facebook.com/apps → **Create App**.
2. Tipo app: **Business**.
3. Aggiungi il prodotto **Instagram Graph API** e **Facebook Login** (o *Pages API*).

## 2. Permessi necessari

| Permesso | A cosa serve |
|---|---|
| `pages_show_list` | elencare le Pagine di cui sei admin (`/me/accounts`) |
| `pages_read_engagement` | leggere la Pagina (dipendenza di `pages_manage_posts`) |
| `pages_manage_posts` | **creare / modificare / eliminare post sulla Pagina** |
| `instagram_basic` | leggere l'account IG Business |
| `instagram_content_publish` | pubblicare su Instagram |
| `instagram_manage_contents` | **eliminare** media IG (solo se ti serve, vedi Troubleshooting B) |
| `business_management` | accesso agli asset via Business Manager |

### Standard Access vs Advanced Access — quando serve davvero l'App Review
Questa è la parte che genera più confusione. Meta distingue due livelli:

- **Standard Access** — il permesso funziona **solo** per utenti che hanno un
  **ruolo sull'app** (Amministratore / Sviluppatore / Tester). È **concesso
  automaticamente** alle app di tipo *Business* per tutti i permessi: **non
  serve App Review**.
- **Advanced Access** — il permesso funziona per *qualunque* utente. Richiede
  **App Review** + Business Verification.

**Conseguenza pratica per questo progetto:** stiamo pubblicando su una Pagina di
cui *noi stessi* siamo admin, con un utente che è admin dell'app. Quindi
**Standard Access basta e l'App Review NON è necessaria.** Se ricevi un errore di
permesso, quasi sempre il problema è che il token è stato generato *senza aver
spuntato quel permesso*, non che manchi l'App Review.

> ℹ️ L'App Review (con screencast del flusso end-to-end) diventa obbligatoria solo
> il giorno in cui l'agente dovrà pubblicare su Pagine di **terzi**.

Fonti: [Graph API — Access Levels](https://developers.facebook.com/docs/graph-api/overview/access-levels),
[Permessi — `pages_manage_posts`](https://developers.facebook.com/docs/permissions/reference/pages_manage_posts)

## 3. Ottieni i token e gli ID

### Access token e Page token
1. Apri il **Graph API Explorer**: https://developers.facebook.com/tools/explorer
2. Seleziona la tua app e genera un **User Access Token** con i permessi sopra.
3. Recupera il token della Pagina:
   ```
   GET /me/accounts
   ```
   Nella risposta trovi `id` (= FB_PAGE_ID) e `access_token` (token della Pagina).

### Trasforma il token in "long-lived" (60 giorni)
```
GET /oauth/access_token?grant_type=fb_exchange_token
    &client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=SHORT_TOKEN
```
Usa il token utente long-lived per rifare `GET /me/accounts` e ottenere un
**Page token long-lived** (non scade finché il token utente è valido).

### IG_USER_ID
```
GET /{FB_PAGE_ID}?fields=instagram_business_account&access_token=PAGE_TOKEN
```
Il campo `instagram_business_account.id` è il tuo **IG_USER_ID**.

## 4. Compila `.env`
```
FB_PAGE_ID=...................
FB_PAGE_ACCESS_TOKEN=.........   # il PAGE token long-lived
IG_USER_ID=...................
```

## 5. Test
```bash
python main.py approve post-001
python main.py run
```

## Rinnovo token
I Page token long-lived durano finché il token utente sottostante è valido.
In una fase successiva aggiungeremo il **refresh automatico** del token nello
scheduler, così l'agente resta autonomo senza interventi manuali.

---

# Troubleshooting (casi reali riscontrati)

## A) Facebook: `(#200) The permission(s) pages_manage_posts are not available`

Messaggio completo:

```
(#200) The permission(s) pages_manage_posts are not available.
It could because either they are deprecated or need to be approved by App Review.
```

### Diagnosi
Il messaggio è **fuorviante**: suggerisce deprecazione o App Review, ma nel nostro
caso nessuna delle due. Prima di tutto ispeziona il token:

```
GET /debug_token?input_token=IL_TUO_PAGE_TOKEN&access_token=APP_ID|APP_SECRET
```

Guarda il campo `scopes`. Nel nostro caso conteneva:

```
business_management, instagram_basic, instagram_content_publish,
pages_read_engagement, pages_show_list, public_profile
```

`pages_manage_posts` **non c'era**. Il token era per il resto sano: `type: PAGE`,
`is_valid: true`, `expires_at: 0` (non scade). Quindi il problema non è la
scadenza né l'App Review (vedi §2: con Standard Access non serve) — è che il
**User token da cui il Page token è stato derivato non aveva quello scope**.

> ⚠️ Punto chiave: gli scope di un Page token sono **ereditati** dal User token
> usato per chiamare `/me/accounts`. Non puoi "aggiungere" un permesso a un Page
> token esistente: devi **rigenerare tutta la catena**.

### Soluzione: rigenerare la catena token

**Passo 0 — verifica i prerequisiti**
- Sei **Amministratore dell'app** su https://developers.facebook.com/apps → *App Roles*.
- Sei **Amministratore della Pagina** (o hai il task *Manage Page*) su Business Manager.
- In *App Review → Permissions and Features*, `pages_manage_posts` risulta almeno
  in **Standard Access** (per le app Business è così di default).

**Passo 1 — User token short-lived con TUTTI gli scope**

Apri il [Graph API Explorer](https://developers.facebook.com/tools/explorer),
seleziona l'app, `User Token`, e **spunta esplicitamente ogni permesso**:

```
pages_show_list, pages_read_engagement, pages_manage_posts,
instagram_basic, instagram_content_publish, business_management
```

Poi *Generate Access Token* e **ri-autorizza nella finestra Facebook**. Se la
finestra si chiude subito senza chiederti nulla, Facebook ti sta ridando il
consenso già memorizzato: revocalo prima da
**Impostazioni Facebook → App e siti web → [la tua app] → Rimuovi**, poi ripeti.

*Alternativa senza Explorer (OAuth diretto):* apri in browser

```
https://www.facebook.com/v26.0/dialog/oauth
  ?client_id=APP_ID
  &redirect_uri=https://localhost/
  &response_type=code
  &scope=pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish,business_management
```

e scambia il `code` dell'URL di ritorno:

```
GET /oauth/access_token?client_id=APP_ID&client_secret=APP_SECRET
    &redirect_uri=https://localhost/&code=IL_CODE
```

Il vantaggio dell'OAuth flow è che gli scope sono **espliciti nell'URL**: è
l'errore più comune dell'Explorer, dove basta una spunta dimenticata.

**Passo 2 — User token long-lived (60 giorni)**
```
GET /oauth/access_token?grant_type=fb_exchange_token
    &client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=USER_TOKEN_SHORT
```

**Passo 3 — Page token long-lived (non scadente)**
```
GET /me/accounts?access_token=USER_TOKEN_LONG
```
Il Page token derivato da uno User token long-lived **non ha scadenza**
(`expires_at: 0`) finché non revochi il consenso o cambi la password.

**Passo 4 — verifica PRIMA di rimettere il token in `.env`**
```
GET /debug_token?input_token=NUOVO_PAGE_TOKEN&access_token=APP_ID|APP_SECRET
```
Controlla che `scopes` contenga ora `pages_manage_posts` e che `type` sia `PAGE`.
Solo allora aggiorna `FB_PAGE_ACCESS_TOKEN` in `.env`.

### E `pages_manage_engagement`?
Serve **solo** per gestire commenti, like e reazioni sui post della Pagina. Per
pubblicare (che è tutto ciò che fa `FacebookAdapter` oggi) **non è necessario**.
Aggiungilo agli scope solo quando implementeremo la moderazione dei commenti —
tenerlo fuori ora significa una richiesta di consenso più snella.

---

## B) Instagram: `(#10) Insufficient permissions to access this data` cancellando un media

### La cancellazione via API **è supportata** (contrariamente a quanto ipotizzato)
La documentazione ufficiale
([IG Media](https://developers.facebook.com/docs/instagram-platform/reference/instagram-media/))
documenta l'endpoint:

```
DELETE https://graph.facebook.com/<API_VERSION>/<IG_MEDIA_ID>?access_token=<TOKEN>
```

Quindi **non** è vero che bisogna per forza cancellare a mano dall'app. Le
condizioni però sono precise, ed è lì che si inciampa.

### Perché falliva
Servono **due** permessi: `instagram_basic` **e `instagram_manage_contents`**.
Il nostro token ha il primo ma **non il secondo** — da cui il generico `(#10)`.
La cura è la stessa del caso A: rigenerare la catena token aggiungendo
`instagram_manage_contents` agli scope del Passo 1.

### Vincoli documentati
- Funziona **solo** con *Instagram API with Facebook Login* (la nostra
  configurazione: app Business + Pagina FB collegata). **Non** con *Instagram API
  with Instagram Login*.
- Sono cancellabili: post non-ad, Storie, Reels e **caroselli interi**.
- **Non** si può cancellare un singolo elemento dentro un carosello: va
  eliminato l'intero album passando l'ID del **container padre** del carosello.
- I **live video** non sono cancellabili.
- I post **sponsorizzati (ad)** non sono cancellabili via questo endpoint.
- ⚠️ L'operazione è **irreversibile**.

### Punti da verificare sul campo (non confermati)
- La doc parla di *Facebook User access token*, mentre l'agente usa ovunque il
  **Page token**. È plausibile che il Page token basti (come per il publishing),
  ma **non l'ho potuto confermare sulla doc**: al primo tentativo di DELETE prova
  prima col Page token e, se ridà `(#10)` **con gli scope corretti già presenti**,
  riprova con lo User token long-lived.
- Il livello di accesso di `instagram_manage_contents` (Standard vs Advanced) non
  è risultato consultabile: la pagina
  `developers.facebook.com/docs/permissions/reference/instagram_manage_contents`
  restituisce **404**. Per analogia con §2 ci si aspetta Standard Access
  sufficiente per la nostra Pagina, ma **è da verificare provando**.

### In alternativa
Finché il token non è rigenerato, la cancellazione va fatta **manualmente
dall'app Instagram**. È una soluzione temporanea, non un limite dell'API.

---

## Nota sulla versione Graph API
Il codice usa `GRAPH_API_VERSION` (default `v21.0`, vedi `platforms/meta.py`).
La versione corrente è `v26.0`. Le versioni Meta restano supportate ~2 anni dal
rilascio, quindi `v21.0` è ancora valida, ma conviene allinearsi a una versione
recente quando si toccano gli endpoint — soprattutto per Instagram, dove la
piattaforma è in migrazione da *Instagram Graph API* a *Instagram Platform*.
Si cambia da `.env` senza toccare il codice:

```
GRAPH_API_VERSION=v26.0
```

---

## Checklist rapida "il publishing non funziona"
1. `GET /debug_token` → il token ha **davvero** gli scope che ti aspetti?
2. `type` è `PAGE` (non `USER`) per `FB_PAGE_ACCESS_TOKEN`?
3. `is_valid: true` e `expires_at: 0`?
4. L'utente che ha generato il token è admin **sia dell'app che della Pagina**?
5. L'errore cita un permesso mancante? → rigenera la catena (§A), **non** aprire
   un'App Review.
6. L'IG è un account **Business/Creator** collegato alla Pagina?
   (`GET /{FB_PAGE_ID}?fields=instagram_business_account`)
