## Hosting (serve un processo sempre attivo, non va bene GitHub Actions)
Opzioni gratuite/economiche compatibili con setup da telefono (dashboard web, nessun terminale richiesto):
- **Railway.app** — deploy da repo GitHub, imposti `DISCORD_TOKEN` nelle variabili d'ambiente.
- **Render.com** — stesso principio, piano free con "sleep" se inattivo (da evitare per un bot sempre online, meglio piano a pagamento minimo).
- **VPS economico** (es. Oracle Cloud free tier) se vuoi controllo completo.

Consigliato: Railway, collegando il repo GitHub e settando `DISCORD_TOKEN` da pannello.
