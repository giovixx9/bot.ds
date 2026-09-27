import os
import re
import time
import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta, datetime, timezone

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Avvisi in memoria: {guild_id: {member_id: [ {reason, moderator, timestamp} ]}}
# NB: si azzerano ad ogni riavvio del bot (nessun database collegato).
warns_store: dict[int, dict[int, list[dict]]] = {}

# Auto-moderazione: attiva di default su ogni server. {guild_id: bool}
automod_enabled: dict[int, bool] = {}

# Traccia i timestamp degli ultimi messaggi per rilevare lo spam: {(guild_id, user_id): [timestamps]}
spam_tracker: dict[tuple, list] = {}
# Conta quante volte un utente è stato beccato a spammare: {(guild_id, user_id): count}
spam_offenses: dict[tuple, int] = {}
SPAM_MAX_MESSAGES = 5      # messaggi
SPAM_INTERVAL_SECONDS = 6  # in questo intervallo di tempo
SPAM_TIMEOUT_MINUTES = 5
SPAM_KICK_AFTER = 2        # numero di volte prima del kick

# Conta le parolacce rilevate per utente: {(guild_id, user_id): count}
badword_offenses: dict[tuple, int] = {}
BADWORD_MUTE_AFTER = 2   # alla 2a volta: mute
BADWORD_KICK_AFTER = 3   # alla 3a volta: kick
BADWORD_TIMEOUT_MINUTES = 5

LINK_PATTERN = re.compile(r"(https?://\S+|discord\.gg/\S+|www\.\S+)", re.IGNORECASE)

BAD_WORDS = {
    "cazzo", "stronzo", "stronza", "merda", "puttana", "troia",
    "bastardo", "coglione", "vaffanculo", "figadituamadre",
}


def is_automod_on(guild_id: int) -> bool:
    return automod_enabled.get(guild_id, True)


def contains_bad_word(text: str) -> bool:
    lowered = text.lower()
    words = re.findall(r"[a-zàèéìòù]+", lowered)
    return any(w in BAD_WORDS for w in words)


def get_warns(guild_id: int, member_id: int) -> list[dict]:
    return warns_store.setdefault(guild_id, {}).setdefault(member_id, [])


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Sincronizzati {len(synced)} comandi slash")
    except Exception as e:
        print(f"Errore sync comandi: {e}")
    print(f"Bot online come {bot.user}")


async def handle_automod(message: discord.Message) -> bool:
    """Ritorna True se il messaggio è stato rimosso dall'automod."""
    if not message.guild or not is_automod_on(message.guild.id):
        return False
    if message.author.guild_permissions.manage_messages:
        return False  # i moderatori non sono soggetti all'automod

    content = message.content or ""

    # Anti-link
    if LINK_PATTERN.search(content):
        try:
            await message.delete()
        except discord.NotFound:
            pass
        await message.channel.send(
            f"{message.author.mention}, i link non sono permessi in questo server.",
            delete_after=6,
        )
        try:
            await message.author.send(
                f"Il tuo messaggio nel server **{message.guild.name}** è stato rimosso: i link non sono permessi."
            )
        except discord.Forbidden:
            pass
        return True

    # Filtro parolacce
    if contains_bad_word(content):
        try:
            await message.delete()
        except discord.NotFound:
            pass

        key = (message.guild.id, message.author.id)
        badword_offenses[key] = badword_offenses.get(key, 0) + 1
        offenses = badword_offenses[key]

        if offenses >= BADWORD_KICK_AFTER:
            badword_offenses[key] = 0
            try:
                await message.author.send(
                    f"Sei stato espulso dal server **{message.guild.name}** per linguaggio ripetuto non appropriato."
                )
            except discord.Forbidden:
                pass
            try:
                await message.author.kick(reason="Linguaggio inappropriato ripetuto (automod)")
                await message.channel.send(f"{message.author.mention} espulso per linguaggio ripetuto.", delete_after=8)
            except discord.Forbidden:
                pass
        elif offenses >= BADWORD_MUTE_AFTER:
            try:
                await message.author.send(
                    f"Sei stato silenziato {BADWORD_TIMEOUT_MINUTES} minuti nel server **{message.guild.name}** "
                    "per linguaggio ripetuto non appropriato. Alla prossima volta verrai espulso."
                )
            except discord.Forbidden:
                pass
            try:
                await message.author.timeout(timedelta(minutes=BADWORD_TIMEOUT_MINUTES), reason="Linguaggio inappropriato ripetuto (automod)")
                await message.channel.send(
                    f"{message.author.mention} silenziato {BADWORD_TIMEOUT_MINUTES} minuti per linguaggio ripetuto "
                    "(prossima volta: espulsione).",
                    delete_after=8,
                )
            except discord.Forbidden:
                pass
        else:
            await message.channel.send(
                f"{message.author.mention}, linguaggio non appropriato, il messaggio è stato rimosso.",
                delete_after=6,
            )
            try:
                await message.author.send(
                    f"Il tuo messaggio nel server **{message.guild.name}** è stato rimosso: linguaggio non appropriato. "
                    "Se continui verrai silenziato e poi espulso."
                )
            except discord.Forbidden:
                pass
        return True

    # Anti-spam (troppi messaggi in poco tempo)
    key = (message.guild.id, message.author.id)
    now = time.time()
    timestamps = [t for t in spam_tracker.get(key, []) if now - t < SPAM_INTERVAL_SECONDS]
    timestamps.append(now)
    spam_tracker[key] = timestamps

    if len(timestamps) > SPAM_MAX_MESSAGES:
        spam_tracker[key] = []
        try:
            await message.delete()
        except discord.NotFound:
            pass

        spam_offenses[key] = spam_offenses.get(key, 0) + 1
        offenses = spam_offenses[key]

        try:
            if offenses >= SPAM_KICK_AFTER:
                spam_offenses[key] = 0
                try:
                    await message.author.send(
                        f"Sei stato espulso dal server **{message.guild.name}** per spam ripetuto."
                    )
                except discord.Forbidden:
                    pass
                await message.author.kick(reason="Spam ripetuto rilevato dall'automod")
                await message.channel.send(
                    f"{message.author.mention} espulso per spam ripetuto.",
                    delete_after=8,
                )
            else:
                try:
                    await message.author.send(
                        f"Sei stato silenziato {SPAM_TIMEOUT_MINUTES} minuti nel server **{message.guild.name}** per spam. "
                        "Alla prossima volta verrai espulso."
                    )
                except discord.Forbidden:
                    pass
                await message.author.timeout(timedelta(minutes=SPAM_TIMEOUT_MINUTES), reason="Spam rilevato dall'automod")
                await message.channel.send(
                    f"{message.author.mention} silenziato {SPAM_TIMEOUT_MINUTES} minuti per spam "
                    f"(prossima volta: espulsione).",
                    delete_after=8,
                )
        except discord.Forbidden:
            pass
        return True

    return False


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    if await handle_automod(message):
        return

    if bot.user in message.mentions:
        await message.reply(
            "Ciao! Sono gxbot, bot di moderazione. Scrivi `/` per vedere tutti i comandi disponibili."
        )
    await bot.process_commands(message)


def has_mod_perms():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id == interaction.guild.owner_id:
            return True
        return interaction.user.guild_permissions.moderate_members
    return app_commands.check(predicate)


@bot.tree.command(name="automod", description="Attiva o disattiva l'auto-moderazione (anti-spam/link/parolacce)")
@app_commands.describe(stato="on per attivare, off per disattivare")
@app_commands.choices(stato=[
    app_commands.Choice(name="on", value="on"),
    app_commands.Choice(name="off", value="off"),
])
@has_mod_perms()
async def automod(interaction: discord.Interaction, stato: app_commands.Choice[str]):
    automod_enabled[interaction.guild.id] = (stato.value == "on")
    emoji = "✅" if stato.value == "on" else "🚫"
    await interaction.response.send_message(f"{emoji} Auto-moderazione {'attivata' if stato.value == 'on' else 'disattivata'}.")


@bot.tree.command(name="kick", description="Espelle un utente dal server")
@app_commands.describe(member="Utente da espellere", reason="Motivo")
@has_mod_perms()
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Nessun motivo specificato"):
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("Non puoi espellere questo utente (ruolo pari o superiore al tuo).", ephemeral=True)
        return
    await member.kick(reason=reason)
    await interaction.response.send_message(f"{member.mention} espulso. Motivo: {reason}")


@bot.tree.command(name="ban", description="Banna un utente dal server")
@app_commands.describe(member="Utente da bannare", reason="Motivo", delete_days="Giorni di messaggi da eliminare (0-7)")
@has_mod_perms()
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Nessun motivo specificato", delete_days: int = 0):
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("Non puoi bannare questo utente (ruolo pari o superiore al tuo).", ephemeral=True)
        return
    delete_days = max(0, min(delete_days, 7))
    await member.ban(reason=reason, delete_message_days=delete_days)
    await interaction.response.send_message(f"{member.mention} bannato. Motivo: {reason}")


@bot.tree.command(name="unban", description="Rimuove il ban a un utente (usa ID)")
@app_commands.describe(user_id="ID Discord dell'utente")
@has_mod_perms()
async def unban(interaction: discord.Interaction, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        await interaction.response.send_message(f"Ban rimosso per {user}.")
    except (ValueError, discord.NotFound):
        await interaction.response.send_message("ID non valido o utente non trovato tra i bannati.", ephemeral=True)


@bot.tree.command(name="mute", description="Silenzia (timeout) un utente per un certo numero di minuti")
@app_commands.describe(member="Utente da silenziare", minutes="Durata in minuti", reason="Motivo")
@has_mod_perms()
async def mute(interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str = "Nessun motivo specificato"):
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("Non puoi silenziare questo utente (ruolo pari o superiore al tuo).", ephemeral=True)
        return
    duration = timedelta(minutes=minutes)
    await member.timeout(duration, reason=reason)
    await interaction.response.send_message(f"{member.mention} silenziato per {minutes} minuti. Motivo: {reason}")


@bot.tree.command(name="unmute", description="Rimuove il timeout a un utente")
@app_commands.describe(member="Utente da riattivare")
@has_mod_perms()
async def unmute(interaction: discord.Interaction, member: discord.Member):
    await member.timeout(None)
    await interaction.response.send_message(f"Timeout rimosso per {member.mention}.")


@bot.tree.command(name="warn", description="Invia un avviso a un utente (via DM + log nel canale)")
@app_commands.describe(member="Utente da avvisare", reason="Motivo")
@has_mod_perms()
async def warn(interaction: discord.Interaction, member: discord.Member, reason: str):
    entry = {
        "reason": reason,
        "moderator": str(interaction.user),
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    get_warns(interaction.guild.id, member.id).append(entry)

    try:
        await member.send(f"Hai ricevuto un avviso nel server **{interaction.guild.name}**.\nMotivo: {reason}")
        dm_status = "(DM inviato)"
    except discord.Forbidden:
        dm_status = "(impossibile inviare DM, DM chiuse)"
    count = len(get_warns(interaction.guild.id, member.id))
    await interaction.response.send_message(f"{member.mention} avvisato ({count} totali). Motivo: {reason} {dm_status}")


@bot.tree.command(name="warnings", description="Mostra gli avvisi di un utente")
@app_commands.describe(member="Utente da controllare")
@has_mod_perms()
async def warnings_cmd(interaction: discord.Interaction, member: discord.Member):
    entries = get_warns(interaction.guild.id, member.id)
    if not entries:
        await interaction.response.send_message(f"{member.mention} non ha avvisi.", ephemeral=True)
        return
    lines = [f"{i+1}. [{e['timestamp']}] {e['reason']} — da {e['moderator']}" for i, e in enumerate(entries)]
    await interaction.response.send_message(f"Avvisi di {member.mention} ({len(entries)}):\n" + "\n".join(lines), ephemeral=True)


@bot.tree.command(name="clearwarnings", description="Cancella tutti gli avvisi di un utente")
@app_commands.describe(member="Utente da ripulire")
@has_mod_perms()
async def clearwarnings(interaction: discord.Interaction, member: discord.Member):
    warns_store.setdefault(interaction.guild.id, {})[member.id] = []
    await interaction.response.send_message(f"Avvisi di {member.mention} cancellati.")


@bot.tree.command(name="purge", description="Elimina un numero di messaggi dal canale")
@app_commands.describe(amount="Numero di messaggi da eliminare (max 100)")
@has_mod_perms()
async def purge(interaction: discord.Interaction, amount: int):
    amount = max(1, min(amount, 100))
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"Eliminati {len(deleted)} messaggi.", ephemeral=True)


@bot.tree.command(name="slowmode", description="Imposta lo slowmode del canale in secondi")
@app_commands.describe(seconds="Secondi di slowmode (0 per disattivare, max 21600)")
@has_mod_perms()
async def slowmode(interaction: discord.Interaction, seconds: int):
    seconds = max(0, min(seconds, 21600))
    await interaction.channel.edit(slowmode_delay=seconds)
    if seconds == 0:
        await interaction.response.send_message("Slowmode disattivato.")
    else:
        await interaction.response.send_message(f"Slowmode impostato a {seconds} secondi.")


@bot.tree.command(name="lock", description="Blocca il canale (impedisce ai membri di scrivere)")
@app_commands.describe(reason="Motivo")
@has_mod_perms()
async def lock(interaction: discord.Interaction, reason: str = "Nessun motivo specificato"):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = False
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite, reason=reason)
    await interaction.response.send_message(f"🔒 Canale bloccato. Motivo: {reason}")


@bot.tree.command(name="unlock", description="Sblocca il canale")
@has_mod_perms()
async def unlock(interaction: discord.Interaction):
    overwrite = interaction.channel.overwrites_for(interaction.guild.default_role)
    overwrite.send_messages = None
    await interaction.channel.set_permissions(interaction.guild.default_role, overwrite=overwrite)
    await interaction.response.send_message("🔓 Canale sbloccato.")


@bot.tree.command(name="nick", description="Cambia il nickname di un utente")
@app_commands.describe(member="Utente", nickname="Nuovo nickname (vuoto per rimuoverlo)")
@has_mod_perms()
async def nick(interaction: discord.Interaction, member: discord.Member, nickname: str = ""):
    await member.edit(nick=nickname or None)
    if nickname:
        await interaction.response.send_message(f"Nickname di {member.mention} cambiato in **{nickname}**.")
    else:
        await interaction.response.send_message(f"Nickname di {member.mention} rimosso.")


@bot.tree.command(name="userinfo", description="Mostra informazioni su un utente")
@app_commands.describe(member="Utente (default: te stesso)")
async def userinfo(interaction: discord.Interaction, member: discord.Member = None):
    member = member or interaction.user
    embed = discord.Embed(title=str(member), color=discord.Color.blurple())
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="ID", value=member.id, inline=True)
    embed.add_field(name="Nickname", value=member.nick or "—", inline=True)
    embed.add_field(name="Account creato", value=member.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Entrato nel server", value=member.joined_at.strftime("%Y-%m-%d") if member.joined_at else "—", inline=True)
    roles = [r.mention for r in member.roles if r.name != "@everyone"]
    embed.add_field(name=f"Ruoli ({len(roles)})", value=", ".join(roles) if roles else "—", inline=False)
    n_warns = len(get_warns(interaction.guild.id, member.id))
    embed.add_field(name="Avvisi", value=str(n_warns), inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="serverinfo", description="Mostra informazioni sul server")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=guild.name, color=discord.Color.blurple())
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    embed.add_field(name="ID", value=guild.id, inline=True)
    embed.add_field(name="Proprietario", value=str(guild.owner), inline=True)
    embed.add_field(name="Creato il", value=guild.created_at.strftime("%Y-%m-%d"), inline=True)
    embed.add_field(name="Membri", value=guild.member_count, inline=True)
    embed.add_field(name="Canali testuali", value=len(guild.text_channels), inline=True)
    embed.add_field(name="Canali vocali", value=len(guild.voice_channels), inline=True)
    embed.add_field(name="Ruoli", value=len(guild.roles), inline=True)
    await interaction.response.send_message(embed=embed)


@kick.error
@automod.error
@ban.error
@unban.error
@mute.error
@unmute.error
@warn.error
@warnings_cmd.error
@clearwarnings.error
@purge.error
@slowmode.error
@lock.error
@unlock.error
@nick.error
async def on_mod_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("Non hai i permessi per usare questo comando.", ephemeral=True)
    else:
        if interaction.response.is_done():
            await interaction.followup.send(f"Errore: {error}", ephemeral=True)
        else:
            await interaction.response.send_message(f"Errore: {error}", ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Imposta la variabile d'ambiente DISCORD_TOKEN con il token del bot.")
    bot.run(TOKEN)
