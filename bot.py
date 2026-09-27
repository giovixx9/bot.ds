import os
import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Sincronizzati {len(synced)} comandi slash")
    except Exception as e:
        print(f"Errore sync comandi: {e}")
    print(f"Bot online come {bot.user}")


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
    try:
        await member.send(f"Hai ricevuto un avviso nel server **{interaction.guild.name}**.\nMotivo: {reason}")
        dm_status = "(DM inviato)"
    except discord.Forbidden:
        dm_status = "(impossibile inviare DM, DM chiuse)"
    await interaction.response.send_message(f"{member.mention} avvisato. Motivo: {reason} {dm_status}")


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


@kick.error
@ban.error
@unban.error
@mute.error
@unmute.error
@warn.error
@purge.error
@slowmode.error
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
