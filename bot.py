import os
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


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    if bot.user in message.mentions:
        await message.reply(
            "Ciao! Sono gxbot, bot di moderazione. Scrivi `/` per vedere tutti i comandi disponibili."
        )
    await bot.process_commands(message)


def has_mod_perms():
    async def predicate(interaction: discord.Interaction) -> bool:
        return interaction.user.guild_permissions.moderate_members
    return app_commands.check(predicate)


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
