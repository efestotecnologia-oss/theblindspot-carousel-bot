# Setup Meta (Facebook + Instagram)

Questa è la parte "lavoro iniziale attento": configurare l'app Meta e ottenere i
token. Va fatta **una sola volta**. Una app copre sia Facebook che Instagram.

## Prerequisiti (dovresti già averli)
- Una **Pagina Facebook**.
- Un account **Instagram Business** o **Creator** collegato alla Pagina.
- Un profilo su [Meta for Developers](https://developers.facebook.com/).

## 1. Crea l'app Meta
1. Vai su https://developers.facebook.com/apps → **Create App**.
2. Tipo app: **Business**. (È quello che dà lo *Standard Access* automatico — vedi §2.)
3. Aggiungi i prodotti: **Instagram** e **Facebook Login for Business**.

> ⚠️ In fase di configurazione del prodotto Instagram scegli
> **"Instagram API with Facebook Login"**, non *"…with Instagram Login"*.
> È la variante per gli account IG Business **collegati a una Pagina Facebook** —
> la nostra — ed è l'unica che espone gli endpoint usati dall'agente
> (publishing sulla Pagina + cancellazione media IG, vedi Troubleshooting B).
> Sceglierla è una decisione **strutturale**: cambiarla dopo significa rifare
> app, permessi e token da zero.

> ℹ️ *Nota terminologica:* la doc Meta ha rinominato l'insieme in **Instagram
> Platform**; il vecchio nome "Instagram Graph API" ricorre ancora in guide e
> articoli di terze parti (e nei commenti di `platforms/meta.py`) ma indica la
> stessa cosa.

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

> ⚠️ **L'ordine dei passi conta.** Lo scambio in *long-lived* va fatto sul **User
> token**, **prima** di chiamare `/me/accounts`. Se chiami `/me/accounts` con un
> User token short-lived ottieni un Page token che **scade in poche ore**: è
> l'errore che costringe a rifare tutto. La catena corretta è
> **User short-lived → User long-lived → Page token**.

### Passo 1 — User token short-lived con TUTTI i permessi
1. Apri il **Graph API Explorer**: https://developers.facebook.com/tools/explorer
2. Seleziona la tua app, tipo token **User Token**, e **spunta esplicitamente
   ogni permesso della tabella §2** (non fidarti del set proposto di default).
3. *Generate Access Token* e autorizza nella finestra Facebook.

> ⚠️ Se la finestra si chiude subito senza chiederti nulla, Facebook ti sta
> restituendo il **consenso già memorizzato** — senza i permessi nuovi. Vedi
> Troubleshooting §A per come revocarlo, e per l'alternativa via OAuth flow
> (dove gli scope sono espliciti nell'URL e non ci si può dimenticare una spunta).

### Passo 2 — User token long-lived (60 giorni)
```
GET /oauth/access_token?grant_type=fb_exchange_token
    &client_id=APP_ID&client_secret=APP_SECRET&fb_exchange_token=USER_TOKEN_SHORT
```

### Passo 3 — Page token (non scadente)
```
GET /me/accounts?access_token=USER_TOKEN_LONG
```
Nella risposta trovi `id` (= **FB_PAGE_ID**) e `access_token` (= il **Page
token**). Derivato da uno User token long-lived, il Page token **non ha
scadenza** (`expires_at: 0`) finché il consenso resta valido.

### Passo 4 — verifica il token prima di usarlo
```
GET /debug_token?input_token=PAGE_TOKEN&access_token=APP_ID|APP_SECRET
```
Controlla `type: PAGE`, `is_valid: true`, `expires_at: 0` e che `scopes`
contenga **tutti** i permessi della tabella §2. Sono 30 secondi che evitano
un'ora di debug sugli errori `(#200)` / `(#10)`.

### IG_USER_ID
```
GET /{FB_PAGE_ID}?fields=instagram_business_account&access_token=PAGE_TOKEN
```
Il campo `instagram_business_account.id` è il tuo **IG_USER_ID**.

## 4. Compila `.env`
```
FB_PAGE_ID=...................
FB_PAGE_ACCESS_TOKEN=.........   # il PAGE token del Passo 3 (non lo User token!)
IG_USER_ID=...................
GRAPH_API_VERSION=v26.0          # opzionale; senza, il codice usa un default più vecchio
```

## 5. Test
```bash
python main.py approve post-001
python main.py run
```

## Rinnovo token
Il Page token ottenuto al Passo 3 non ha una scadenza a calendario, ma **decade**
se revochi il consenso all'app, cambi la password Facebook o perdi il ruolo di
admin sulla Pagina. In quel caso si rifà la catena del §3 da capo.

> ⚠️ Lo stesso vale se devi **aggiungere un permesso**: gli scope di un Page token
> sono ereditati dallo User token e **non** si possono aggiungere a posteriori.
> Si rigenera tutta la catena (§3), non solo l'ultimo passo. Vedi Troubleshooting §A.

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

**Passi 1-4 — rifai la catena del §3**, con questi due accorgimenti:

- **Spunta ogni permesso della tabella §2**, incluso
  `instagram_manage_contents` se vuoi risolvere insieme anche il caso B.
  Rigenerare due volte per due permessi dimenticati è la trappola classica.
- Se la finestra di autorizzazione Facebook si chiude subito senza chiederti
  nulla, ti sta ridando il **consenso già memorizzato** (senza i permessi nuovi):
  revocalo da **Impostazioni Facebook → App e siti web → [la tua app] → Rimuovi**,
  poi ripeti.

*Alternativa al Graph API Explorer (OAuth diretto).* Il vantaggio è che gli scope
sono **espliciti nell'URL**, quindi non puoi dimenticare una spunta — che è
esattamente il modo in cui nasce l'errore `(#200)`. Apri in browser:

```
https://www.facebook.com/v26.0/dialog/oauth
  ?client_id=APP_ID
  &redirect_uri=https://localhost/
  &response_type=code
  &scope=pages_show_list,pages_read_engagement,pages_manage_posts,instagram_basic,instagram_content_publish,instagram_manage_contents,business_management
```

e scambia il `code` dell'URL di ritorno:

```
GET /oauth/access_token?client_id=APP_ID&client_secret=APP_SECRET
    &redirect_uri=https://localhost/&code=IL_CODE
```

Da qui prosegui col Passo 2 del §3 (`fb_exchange_token`).

**Verifica finale prima di rimettere il token in `.env`:** il `/debug_token` del
Passo 4 deve mostrare `pages_manage_posts` dentro `scopes` e `type: PAGE`.

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
La cura è la stessa del caso A: rigenerare la catena token (§3) aggiungendo
`instagram_manage_contents` agli scope del **Passo 1**.

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
La versione usata si imposta con `GRAPH_API_VERSION` in `.env` (§4), senza
toccare il codice. **Il `.env` di sviluppo è già su `v26.0`**, che è la versione
corrente — quindi in pratica gira quella.

Attenzione però al **fallback**: `platforms/meta.py` ha come default `v21.0`. Se
la variabile manca (deploy nuovo, CI, container senza `.env` completo) l'agente
scivola silenziosamente su una versione vecchia. `v21.0` è tuttora supportata —
Meta mantiene ogni versione ~2 anni dal rilascio — quindi non è un bug urgente,
ma vale la pena allineare il default prima o poi, soprattutto per Instagram, dove
la piattaforma è in migrazione da *Instagram Graph API* a *Instagram Platform*.

---

## Checklist rapida "il publishing non funziona"
1. `GET /debug_token` → il token ha **davvero** gli scope che ti aspetti?
2. `type` è `PAGE` (non `USER`) per `FB_PAGE_ACCESS_TOKEN`?
3. `is_valid: true` e `expires_at: 0`?
4. L'utente che ha generato il token è admin **sia dell'app che della Pagina**?
5. L'errore cita un permesso mancante? → rigenera la catena (§A), **non** aprire
   un'App Review.
6. L'IG è un account **professional** (Business *o* Creator — per il publishing
   Meta li tratta allo stesso modo) collegato alla Pagina?
   (`GET /{FB_PAGE_ID}?fields=instagram_business_account`)
7. Hai superato i **limiti di pubblicazione**? Instagram consente **100 post via
   API ogni 24h** (un carosello conta come 1 post) e **max 10 elementi** per
   carosello — quest'ultimo è già controllato in `_create_carousel_container`.
