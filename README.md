# Bot Discord di moderazione

## Comandi (slash)
- `/kick` `/ban` `/unban` — gestione utenti
- `/mute` `/unmute` — timeout temporaneo
- `/warn` — avviso via DM + conferma nel canale
- `/purge` — elimina messaggi in blocco
- `/slowmode` — imposta slowmode del canale

Tutti i comandi richiedono il permesso "Modera membri" su chi li usa.

## Setup

1. Crea l'applicazione su https://discord.com/developers/applications, sezione **Bot**, copia il token.
2. Attiva in "Privileged Gateway Intents": **Server Members Intent** e **Message Content Intent**.
3. Invita il bot nel server con permessi: Kick Members, Ban Members, Moderate Members, Manage Messages, Manage Channels.
4. Imposta la variabile d'ambiente `DISCORD_TOKEN` col token del bot (non scriverlo nel codice).
5. Installa le dipendenze:
