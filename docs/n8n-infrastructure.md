# Infrastruttura n8n — Ai che dolor YouTube Publisher

Ultimo aggiornamento: 12 agosto 2026

## Server
- VPS: 89.167.66.122 (Hetzner)
- Dominio pubblico: 89.167.66.122.nip.io (wildcard DNS verso lo stesso IP, usato perché Google OAuth richiede un dominio pubblico, non un IP nudo, nei redirect URI)
- Accesso: solo HTTPS via Caddy (porta 443). La porta 5678 di n8n è vincolata a 127.0.0.1 a livello Docker (non solo firewall, perché Docker bypassa ufw con le proprie regole iptables NAT) — non raggiungibile dall'esterno in nessun modo.
- TLS: certificato Let's Encrypt gestito automaticamente da Caddy (ACME), rinnovo automatico verificato, richiede la porta 80 aperta per la sfida http-01.

## n8n
- Istanza self-hosted via Docker, dati persistiti nel volume n8n_data
- URL editor: https://89.167.66.122.nip.io
- Workflow principale: "Ai che dolor - YouTube Publisher" (id: G73jNg8ZhUQl20O7)
  - Nodi: Ogni Ora Trigger → Leggi Lista Video (Google Sheets) → Trova Prossimo Video → Scarica Video da Drive → Pubblica su YouTube → Aggiorna Stato Pubblicazione
  - Testato end-to-end con successo (pubblicazione video reale confermata)

## Google Cloud
- Progetto: "n8n automation" (project id: high-life-505310-j5)
- OAuth Client: "n8n youtube" (Web application), Client ID: 293672482142-mnlthv7h9tenpv09gvnrhns1s0tmmisf.apps.googleusercontent.com
- Client Secret: conservato esclusivamente nel credential manager di n8n, non su file
- Redirect URI registrato: https://89.167.66.122.nip.io/rest/oauth2-credential/callback
- API abilitate: YouTube Data API v3, Google Sheets API, Google Drive API
- OAuth consent screen in modalità Testing — test user autorizzato: efestotecnologia@gmail.com

## Permessi cross-account
- Canale YouTube "Aichedolor" e foglio "Ai che dolor - Tracking" sono di proprietà di zerohypeyoutube@gmail.com
- efestotecnologia@gmail.com (account usato per l'OAuth n8n) ha ricevuto accesso Editor sia sul canale YouTube (via YouTube Studio → Autorizzazioni) sia sul foglio Google Sheets (via Condividi)
