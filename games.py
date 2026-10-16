import random
import time

import discord
from discord import app_commands
from discord.ext import commands

NO_PING = discord.AllowedMentions.none()

# ---------------------------------------------------------------- TRIS

WIN_LINES = [
    (0, 1, 2), (3, 4, 5), (6, 7, 8),
    (0, 3, 6), (1, 4, 7), (2, 5, 8),
    (0, 4, 8), (2, 4, 6),
]


def tris_winner(board):
    for a, b, c in WIN_LINES:
        if board[a] and board[a] == board[b] == board[c]:
            return board[a]
    if all(board):
        return "draw"
    return None


def tris_ai_move(board):
    free = [i for i, v in enumerate(board) if v is None]
    for mark in ("O", "X"):  # prima vinci, poi blocca
        for i in free:
            test = board[:]
            test[i] = mark
            if tris_winner(test) == mark:
                return i
    if 4 in free:
        return 4
    return random.choice(free)


class TrisButton(discord.ui.Button):
    def __init__(self, idx: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="\u200b", row=idx // 3)
        self.idx = idx

    async def callback(self, interaction: discord.Interaction):
        await self.view.play(interaction, self.idx)


class TrisView(discord.ui.View):
    def __init__(self, cog, p1: discord.Member, p2: discord.Member | None):
        super().__init__(timeout=180)
        self.cog = cog
        self.p1 = p1
        self.p2 = p2  # None = bot
        self.board = [None] * 9
        self.turn = 0  # 0 = p1 (X), 1 = p2 (O)
        self.message = None
        for i in range(9):
            self.add_item(TrisButton(i))

    def p2_name(self):
        return self.p2.mention if self.p2 else "gxbot"

    def header(self):
        cur = self.p1.mention if self.turn == 0 else self.p2_name()
        return f"❌ {self.p1.mention} vs ⭕ {self.p2_name()}\nTurno di: {cur}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        expected = self.p1 if self.turn == 0 else self.p2
        if interaction.user != expected:
            await interaction.response.send_message("Non è il tuo turno.", ephemeral=True)
            return False
        return True

    def set_cell(self, idx: int, mark: str):
        self.board[idx] = mark
        btn = self.children[idx]
        btn.label = "X" if mark == "X" else "O"
        btn.style = discord.ButtonStyle.danger if mark == "X" else discord.ButtonStyle.primary
        btn.disabled = True

    def finish(self, res: str) -> str:
        for c in self.children:
            c.disabled = True
        self.stop()
        if res == "draw":
            return f"🤝 Pareggio!\n❌ {self.p1.mention} vs ⭕ {self.p2_name()}"
        winner = self.p1 if res == "X" else self.p2
        if winner:
            self.cog.add_win(winner.guild.id, winner.id)
            return f"🏆 Vince {winner.mention}!\n❌ {self.p1.mention} vs ⭕ {self.p2_name()}"
        return f"🤖 Vince gxbot!\n❌ {self.p1.mention} vs ⭕ {self.p2_name()}"

    async def play(self, interaction: discord.Interaction, idx: int):
        self.set_cell(idx, "X" if self.turn == 0 else "O")
        res = tris_winner(self.board)
        if not res and self.p2 is None:
            self.set_cell(tris_ai_move(self.board), "O")
            res = tris_winner(self.board)
        elif not res:
            self.turn = 1 - self.turn
        if res:
            await interaction.response.edit_message(content=self.finish(res), view=self, allowed_mentions=NO_PING)
        else:
            await interaction.response.edit_message(content=self.header(), view=self, allowed_mentions=NO_PING)

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⏰ Partita scaduta.", view=self)
            except discord.HTTPException:
                pass


# ---------------------------------------------------------------- BLACKJACK

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["A", "2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K"]


def new_deck():
    deck = [(r, s) for r in RANKS for s in SUITS]
    random.shuffle(deck)
    return deck


def hand_value(hand):
    total, aces = 0, 0
    for r, _ in hand:
        if r == "A":
            total += 11
            aces += 1
        elif r in ("J", "Q", "K"):
            total += 10
        else:
            total += int(r)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def fmt_hand(hand):
    return " ".join(f"`{r}{s}`" for r, s in hand)


class BlackjackView(discord.ui.View):
    def __init__(self, cog, player: discord.Member):
        super().__init__(timeout=120)
        self.cog = cog
        self.player = player
        self.deck = new_deck()
        self.p_hand = [self.deck.pop(), self.deck.pop()]
        self.d_hand = [self.deck.pop(), self.deck.pop()]
        self.message = None

    def text(self, reveal=False, footer=""):
        d = fmt_hand(self.d_hand) if reveal else f"`{self.d_hand[0][0]}{self.d_hand[0][1]}` `??`"
        d_val = hand_value(self.d_hand) if reveal else "?"
        return (
            f"🃏 **Blackjack** — {self.player.mention}\n"
            f"Tu: {fmt_hand(self.p_hand)} = **{hand_value(self.p_hand)}**\n"
            f"Banco: {d} = **{d_val}**\n{footer}"
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user != self.player:
            await interaction.response.send_message("Non è la tua partita.", ephemeral=True)
            return False
        return True

    async def end(self, interaction: discord.Interaction, footer: str, win: bool = False):
        for c in self.children:
            c.disabled = True
        self.stop()
        if win:
            self.cog.add_win(self.player.guild.id, self.player.id)
        await interaction.response.edit_message(
            content=self.text(reveal=True, footer=footer), view=self, allowed_mentions=NO_PING
        )

    @discord.ui.button(label="Carta", style=discord.ButtonStyle.success, emoji="➕")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.p_hand.append(self.deck.pop())
        v = hand_value(self.p_hand)
        if v > 21:
            await self.end(interaction, "💥 Sballato! Hai perso.")
        elif v == 21:
            await self.stand.callback(interaction)
        else:
            await interaction.response.edit_message(content=self.text(), view=self, allowed_mentions=NO_PING)

    @discord.ui.button(label="Stai", style=discord.ButtonStyle.danger, emoji="✋")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button = None):
        while hand_value(self.d_hand) < 17:
            self.d_hand.append(self.deck.pop())
        p, d = hand_value(self.p_hand), hand_value(self.d_hand)
        if d > 21 or p > d:
            await self.end(interaction, "🏆 Hai vinto!", win=True)
        elif p == d:
            await self.end(interaction, "🤝 Pareggio.")
        else:
            await self.end(interaction, "😔 Ha vinto il banco.")

    async def on_timeout(self):
        for c in self.children:
            c.disabled = True
        if self.message:
            try:
                await self.message.edit(content="⏰ Partita scaduta.", view=self)
            except discord.HTTPException:
                pass


# ---------------------------------------------------------------- COG

BALL_ANSWERS = [
    "Sì, assolutamente.", "È certo.", "Senza dubbio.", "Molto probabile.",
    "Direi di sì.", "Non è chiaro, riprova.", "Meglio non dirtelo ora.",
    "Concentrati e richiedi.", "Non contarci.", "La mia risposta è no.",
    "Molto dubbioso.", "Assolutamente no.",
]

RPS = {"sasso": "🪨", "carta": "📄", "forbici": "✂️"}
RPS_BEATS = {"sasso": "forbici", "carta": "sasso", "forbici": "carta"}

GUESS_TIMEOUT = 600  # secondi


class Games(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # {guild_id: {user_id: vittorie}} — si azzera al riavvio
        self.scores: dict[int, dict[int, int]] = {}
        # {channel_id: (numero, start_ts, starter_id)}
        self.guess_games: dict[int, tuple[int, float, int]] = {}

    def add_win(self, guild_id: int, user_id: int):
        g = self.scores.setdefault(guild_id, {})
        g[user_id] = g.get(user_id, 0) + 1

    @app_commands.command(name="moneta", description="Lancia una moneta")
    async def moneta(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🪙 {random.choice(['Testa', 'Croce'])}!")

    @app_commands.command(name="dado", description="Tira un dado")
    @app_commands.describe(facce="Numero di facce (default 6)", quanti="Quanti dadi (default 1, max 10)")
    async def dado(self, interaction: discord.Interaction, facce: app_commands.Range[int, 2, 1000] = 6,
                   quanti: app_commands.Range[int, 1, 10] = 1):
        rolls = [random.randint(1, facce) for _ in range(quanti)]
        if quanti == 1:
            await interaction.response.send_message(f"🎲 d{facce}: **{rolls[0]}**")
        else:
            await interaction.response.send_message(f"🎲 {quanti}d{facce}: {rolls} = **{sum(rolls)}**")

    @app_commands.command(name="8ball", description="Fai una domanda alla palla magica")
    @app_commands.describe(domanda="La tua domanda")
    async def eight_ball(self, interaction: discord.Interaction, domanda: str):
        await interaction.response.send_message(f"🎱 {domanda}\n**{random.choice(BALL_ANSWERS)}**")

    @app_commands.command(name="sasso", description="Sasso carta forbici contro il bot")
    @app_commands.describe(scelta="La tua mossa")
    @app_commands.choices(scelta=[app_commands.Choice(name=f"{RPS[k]} {k}", value=k) for k in RPS])
    async def sasso(self, interaction: discord.Interaction, scelta: app_commands.Choice[str]):
        mine = scelta.value
        bot_move = random.choice(list(RPS))
        if mine == bot_move:
            res = "🤝 Pareggio!"
        elif RPS_BEATS[mine] == bot_move:
            res = "🏆 Hai vinto!"
            self.add_win(interaction.guild.id, interaction.user.id)
        else:
            res = "😔 Hai perso."
        await interaction.response.send_message(f"{RPS[mine]} vs {RPS[bot_move]} — {res}")

    @app_commands.command(name="tris", description="Gioca a tris contro un utente o contro il bot")
    @app_commands.describe(avversario="Utente da sfidare (vuoto = gioca contro il bot)")
    async def tris(self, interaction: discord.Interaction, avversario: discord.Member | None = None):
        if avversario and (avversario.bot or avversario == interaction.user):
            await interaction.response.send_message("Avversario non valido.", ephemeral=True)
            return
        view = TrisView(self, interaction.user, avversario)
        await interaction.response.send_message(view.header(), view=view, allowed_mentions=discord.AllowedMentions(users=True))
        view.message = await interaction.original_response()

    @app_commands.command(name="blackjack", description="Gioca a blackjack contro il banco")
    async def blackjack(self, interaction: discord.Interaction):
        view = BlackjackView(self, interaction.user)
        if hand_value(view.p_hand) == 21:
            for c in view.children:
                c.disabled = True
            self.add_win(interaction.guild.id, interaction.user.id)
            await interaction.response.send_message(
                view.text(reveal=True, footer="🎉 Blackjack! Hai vinto!"), view=view, allowed_mentions=NO_PING
            )
            return
        await interaction.response.send_message(view.text(), view=view, allowed_mentions=NO_PING)
        view.message = await interaction.original_response()

    @app_commands.command(name="indovina", description="Avvia 'Indovina il numero' (1-100) nel canale")
    async def indovina(self, interaction: discord.Interaction):
        cid = interaction.channel.id
        game = self.guess_games.get(cid)
        if game and time.time() - game[1] < GUESS_TIMEOUT:
            await interaction.response.send_message("C'è già una partita in corso in questo canale.", ephemeral=True)
            return
        self.guess_games[cid] = (random.randint(1, 100), time.time(), interaction.user.id)
        await interaction.response.send_message(
            "🔢 Ho pensato un numero tra **1 e 100**. Scrivi i tuoi tentativi in chat! "
            "(scade tra 10 minuti, `/indovina_stop` per annullare)"
        )

    @app_commands.command(name="indovina_stop", description="Annulla la partita di 'Indovina il numero'")
    async def indovina_stop(self, interaction: discord.Interaction):
        game = self.guess_games.get(interaction.channel.id)
        if not game:
            await interaction.response.send_message("Nessuna partita in corso.", ephemeral=True)
            return
        if interaction.user.id != game[2] and not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("Solo chi l'ha avviata o un moderatore può annullarla.", ephemeral=True)
            return
        del self.guess_games[interaction.channel.id]
        await interaction.response.send_message(f"Partita annullata. Il numero era **{game[0]}**.")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        game = self.guess_games.get(message.channel.id)
        if not game:
            return
        number, started, _ = game
        if time.time() - started > GUESS_TIMEOUT:
            del self.guess_games[message.channel.id]
            return
        text = message.content.strip()
        if not text.isdigit():
            return
        guess = int(text)
        if guess == number:
            del self.guess_games[message.channel.id]
            self.add_win(message.guild.id, message.author.id)
            await message.reply(f"🎉 {message.author.mention} ha indovinato! Il numero era **{number}**.")
        elif guess < number:
            await message.add_reaction("⬆️")
        else:
            await message.add_reaction("⬇️")

    @app_commands.command(name="classifica", description="Classifica vittorie ai giochi del server")
    async def classifica(self, interaction: discord.Interaction):
        board = self.scores.get(interaction.guild.id, {})
        if not board:
            await interaction.response.send_message("Nessuna vittoria registrata ancora.")
            return
        top = sorted(board.items(), key=lambda x: x[1], reverse=True)[:10]
        medals = ["🥇", "🥈", "🥉"]
        lines = [f"{medals[i] if i < 3 else f'{i + 1}.'} <@{uid}> — {w}" for i, (uid, w) in enumerate(top)]
        await interaction.response.send_message("🏆 **Classifica giochi**\n" + "\n".join(lines), allowed_mentions=NO_PING)


async def setup(bot: commands.Bot):
    await bot.add_cog(Games(bot))
