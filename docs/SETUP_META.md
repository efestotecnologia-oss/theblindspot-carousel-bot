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

## 2. Permessi necessari (in App Review)
Per pubblicare servono questi permessi, che vanno richiesti in **App Review**
(in modalità sviluppo funzionano solo con utenti/ruoli di test):
- `pages_manage_posts` — pubblicare sulla Pagina
- `pages_read_engagement`
- `instagram_basic`
- `instagram_content_publish` — pubblicare su Instagram
- `business_management`

> ⚠️ L'App Review può richiedere alcuni giorni. Finché sei in *Development mode*
> puoi testare tutto usando il tuo utente amministratore come tester.

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
