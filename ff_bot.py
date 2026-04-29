import discord
from discord.ext import commands
import random
import asyncio
import os
import asyncpg

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ASSET_BASE_URL = "https://raw.githubusercontent.com/YOUR_USER/YOUR_REPO/main/assets/"
FF_CATEGORY_ID = 1498963161934467184

# ─────────────────────────────────────────────
#  DATA
# ─────────────────────────────────────────────
CLASSES = {
    "warrior":   {"name": "Warrior",          "role": "Tank",            "gif": "Warrior.gif",   "hp": 200},
    "blackmage": {"name": "Black Mage",        "role": "Mage / DPS",      "gif": "Blackmage.gif", "hp": 150},
    "whitemage": {"name": "White Mage",        "role": "Healer",          "gif": "Whitemage.gif", "hp": 170},
    "archer":    {"name": "Archer",            "role": "Ranger / DPS",    "gif": "Archer.gif",    "hp": 165},
    "thief":     {"name": "Thief",             "role": "Rogue / Support", "gif": "Thief.gif",     "hp": 160},
    "redmage":   {"name": "Red Mage",          "role": "Hybrid / Mage",   "gif": "Redmage.gif",   "hp": 175},
}

ENEMIES = {
    "garland":   {"name": "Garland",           "hp": 280, "gif": "unit_201000203_1idle_opac.gif",
                  "sig": {"name": "Chaos Slicer", "dmg": (18, 28)}, "slash_dmg": (6, 14),
                  "hard": {"hp": 450, "slash_dmg": (10, 20), "sig_dmg": (28, 42)}},
    "sephiroth": {"name": "Sephiroth",         "hp": 320, "gif": "unit_335000305_1idle_opac.gif",
                  "sig": {"name": "Octoslash",    "dmg": (22, 35)}, "slash_dmg": (7, 15),
                  "hard": {"hp": 500, "slash_dmg": (12, 22), "sig_dmg": (34, 52)}},
    "cod":       {"name": "Cloud of Darkness", "hp": 350, "gif": "unit_203000803_1idle_opac.gif",
                  "sig": {"name": "Aura Ball",    "dmg": (20, 32)}, "slash_dmg": (6, 13),
                  "hard": {"hp": 540, "slash_dmg": (11, 21), "sig_dmg": (30, 48)}},
}

# Hard mode versions — unlocked after defeating the normal version
# +50% HP, +25% damage ranges, signature moves hit harder, sig threshold raised to 40%
HARD_ENEMIES = {
    "garland+":   {"name": "Garland ☆",         "hp": 430, "gif": "unit_201000203_1idle_opac.gif",
                   "sig": {"name": "Chaos Slicer+", "dmg": (26, 40)}, "slash_dmg": (9, 20),
                   "sig_threshold": 0.4},
    "sephiroth+": {"name": "Sephiroth ☆",        "hp": 490, "gif": "unit_335000305_1idle_opac.gif",
                   "sig": {"name": "Octoslash+",    "dmg": (32, 50)}, "slash_dmg": (10, 22),
                   "sig_threshold": 0.4},
    "cod+":       {"name": "Cloud of Darkness ☆", "hp": 530, "gif": "unit_203000803_1idle_opac.gif",
                   "sig": {"name": "Aura Ball+",    "dmg": (29, 46)}, "slash_dmg": (9, 19),
                   "sig_threshold": 0.4},
}

# Merge so all battle logic can look up either dict by key
ALL_ENEMIES = {**ENEMIES, **HARD_ENEMIES}

# Per-player set of unlocked hard bosses  {user_id: {"garland+", ...}}
unlocked_hard: dict[int, set] = {}

def unlock_hard(user_id: int, normal_key: str):
    hard_key = normal_key + "+"
    if hard_key in HARD_ENEMIES:
        unlocked_hard.setdefault(user_id, set()).add(hard_key)

def is_unlocked(user_id: int, hard_key: str) -> bool:
    return hard_key in unlocked_hard.get(user_id, set())

MOVES = {
    "slash":   {"cost": 1, "type": "atk",    "dmg": (4,  10)},
    "poison":  {"cost": 3, "type": "status", "effect": "poison"},
    "regen":   {"cost": 3, "type": "status", "effect": "regen"},
    "cure":    {"cost": 4, "type": "heal",   "heal": (12, 20)},
    "fire":    {"cost": 5, "type": "atk",    "dmg": (14, 22)},
    "ice":     {"cost": 5, "type": "atk",    "dmg": (14, 22)},
    "thunder": {"cost": 5, "type": "atk",    "dmg": (14, 22)},
}

DUEL_MOVES = {
    "slash":   {"type": "atk",    "dmg": (6,  14)},
    "poison":  {"type": "status", "effect": "poison"},
    "regen":   {"type": "status", "effect": "regen"},
    "cure":    {"type": "heal",   "heal": (15, 25)},
    "fire":    {"type": "atk",    "dmg": (16, 24)},
    "ice":     {"type": "atk",    "dmg": (16, 24)},
    "thunder": {"type": "atk",    "dmg": (16, 24)},
}

ZODIAC_MAP = {
    "January":   "Capricorn ♑",  "February":  "Aquarius ♒",
    "March":     "Pisces ♓",     "April":     "Aries ♈",
    "May":       "Taurus ♉",     "June":      "Gemini ♊",
    "July":      "Cancer ♋",     "August":    "Leo ♌",
    "September": "Virgo ♍",      "October":   "Libra ♎",
    "November":  "Scorpio ♏",    "December":  "Sagittarius ♐",
}

WIN_MSGS  = [
    "The crystal glows in your honor! You are a true champion.",
    "A legend is born this day. Well fought, warrior.",
    "The darkness retreats before your light. Victory is yours!",
    "Your name shall be sung across the realm!",
]
LOSE_MSGS = [
    "You absolute dog shit. Get back up and try again.",
    "What was that?? Dog shit performance. Run it back.",
    "Dog shit. Pure dog shit. Try harder next time.",
    "You got cooked. Dog shit. Challenge them again.",
]

GIL_WIN_PVE   = 10
GIL_WIN_DUEL  = 20
GIL_LOSE_DUEL = 10
GIL_START     = 200

# ─────────────────────────────────────────────
#  DATABASE  (Railway PostgreSQL)
#  Connected via DATABASE_URL env var set automatically by Railway.
#  Tables created on startup if they don't exist.
# ─────────────────────────────────────────────
db_pool = None   # set in on_ready

async def init_db():
    global db_pool
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("⚠️  No DATABASE_URL found — player data will not persist.")
        return
    db_pool = await asyncpg.create_pool(db_url)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id     BIGINT PRIMARY KEY,
                gil         INTEGER NOT NULL DEFAULT 200,
                hard_unlocked TEXT NOT NULL DEFAULT ''
            )
        """)
    print("✅ Database connected and tables ready.")

async def db_ensure(uid: int):
    """Insert a player row if it doesn't exist yet."""
    if not db_pool: return
    async with db_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO players (user_id, gil) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            uid, GIL_START,
        )

async def db_get_gil(uid: int) -> int:
    if not db_pool: return GIL_START
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT gil FROM players WHERE user_id=$1", uid)
        return row["gil"] if row else GIL_START

async def db_add_gil(uid: int, amt: int):
    if not db_pool: return
    await db_ensure(uid)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE players SET gil = GREATEST(0, gil + $1) WHERE user_id=$2",
            amt, uid,
        )

async def db_set_gil(uid: int, amt: int):
    if not db_pool: return
    await db_ensure(uid)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE players SET gil = GREATEST(0, $1) WHERE user_id=$2",
            amt, uid,
        )

async def db_get_hard_unlocked(uid: int) -> set:
    if not db_pool: return set()
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow("SELECT hard_unlocked FROM players WHERE user_id=$1", uid)
        if not row or not row["hard_unlocked"]: return set()
        return set(row["hard_unlocked"].split(","))

async def db_unlock_hard(uid: int, enemy_key: str):
    if not db_pool: return
    unlocked = await db_get_hard_unlocked(uid)
    unlocked.add(enemy_key)
    async with db_pool.acquire() as conn:
        await conn.execute(
            "UPDATE players SET hard_unlocked=$1 WHERE user_id=$2",
            ",".join(unlocked), uid,
        )

# ─────────────────────────────────────────────
#  IN-MEMORY GIL CACHE (fallback if no DB)
# ─────────────────────────────────────────────
gil_bank: dict[int, int] = {}
def get_gil(uid):       return gil_bank.get(uid, GIL_START)
def add_gil(uid, amt):  gil_bank[uid] = max(0, gil_bank.get(uid, GIL_START) + amt)
def set_gil(uid, amt):  gil_bank[uid] = max(0, amt)

# ─────────────────────────────────────────────
#  SHARED HELPERS
# ─────────────────────────────────────────────
def hp_bar(cur, mx, n=16) -> str:
    f = round((cur / mx) * n)
    return "█" * f + "░" * (n - f)

async def pin_msg(msg: discord.Message):
    try: await msg.pin()
    except Exception: pass

async def edit_pin(msg: discord.Message, embed: discord.Embed):
    try: await msg.edit(embed=embed)
    except Exception: pass

# ─────────────────────────────────────────────
#  MISS / CRIT SYSTEM
#  Miss  : 15%  → 0 damage
#  Crit  : 15%  → 2× damage
#  Normal: 70%
# ─────────────────────────────────────────────
MISS_CHANCE = 0.15
CRIT_CHANCE = 0.15

def calc_hit(base_dmg: int, halved: bool = False) -> tuple[int, str]:
    roll = random.random()
    if roll < MISS_CHANCE:
        return 0, "miss"
    dmg = base_dmg * 2 if roll >= (1 - CRIT_CHANCE) else base_dmg
    if halved:
        dmg = dmg // 2
    outcome = "crit" if roll >= (1 - CRIT_CHANCE) else "normal"
    return dmg, outcome

def hit_line(move_name: str, atk: str, def_: str, outcome: str, dmg: int) -> str:
    if outcome == "miss":
        return f"💨 **{atk}** uses **{move_name}** — **MISSED** {def_}!"
    if outcome == "crit":
        return f"💥 **CRITICAL HIT!** **{atk}** lands **{move_name}** on {def_} for **{dmg}** damage!"
    return f"⚔ **{atk}** uses **{move_name}** on {def_} for **{dmg}** damage!"


# ─────────────────────────────────────────────
#  PvE CARD BUILDERS
#  Two separate embeds — player card + enemy card
#  Each shows its GIF large via set_image so both
#  sprites are fully visible and animated.
# ─────────────────────────────────────────────
def pve_player_card(s, title: str = "") -> discord.Embed:
    """Blue card — player sprite + HP + status + queue info."""
    status_parts = []
    if s.p_poison: status_parts.append(f"☠ Poison ({s.p_poison} turns)")
    if s.p_regen:  status_parts.append(f"♻ Regen ({s.p_regen} turns)")
    if s.p_defend: status_parts.append("🛡 Defending  *(damage halved)*")
    if s.stored:   status_parts.append(f"📦 Stored roll: +{s.stored}pt")
    status_val = "\n".join(status_parts) if status_parts else "—"

    pts_val = f"**{s.pts_left}pt** remaining" if s.pts_left else "—"
    queue_val = " → ".join(q.capitalize() for q in s.queue) if s.queue else "—"

    em = discord.Embed(
        title=title or f"⚔ {s.char_name}",
        color=0x1a3a8a,
    )
    em.set_author(name=f"{s.char_name}  ·  {s.chosen_class['name']}  ·  {s.chosen_class['role']}")
    em.set_image(url=ASSET_BASE_URL + s.chosen_class["gif"])
    em.add_field(
        name="HP",
        value=f"`{hp_bar(s.p_hp, s.p_hp_max_battle)}`\n**{s.p_hp} / {s.p_hp_max_battle}**",
        inline=True,
    )
    em.add_field(name="Status",        value=status_val, inline=True)
    em.add_field(name="Points / Queue",value=f"{pts_val}\n{queue_val}", inline=False)
    em.set_footer(text="!roll → queue moves → !execute  |  !defend to store roll & halve damage")
    return em


def pve_enemy_card(s, title: str = "") -> discord.Embed:
    """Red card — enemy sprite + HP + status + sig warning."""
    e = s.enemy
    status_parts = []
    if s.e_poison: status_parts.append(f"☠ Poison ({s.e_poison} turns)")
    if s.e_regen:  status_parts.append(f"♻ Regen ({s.e_regen} turns)")
    status_val = "\n".join(status_parts) if status_parts else "—"
    low_warn = "\n\n⚠️ **Signature move ready!**" if s.e_hp > 0 and s.e_hp / s.e_hp_max < 0.3 else ""

    em = discord.Embed(
        title=title or f"👹 {e['name']}",
        color=0x8b0000,
    )
    em.set_author(name=f"{e['name']}  ·  Signature: {e['sig']['name']}")
    em.set_image(url=ASSET_BASE_URL + e["gif"])
    em.add_field(
        name="HP",
        value=f"`{hp_bar(s.e_hp, s.e_hp_max)}`\n**{s.e_hp} / {s.e_hp_max}**",
        inline=True,
    )
    em.add_field(name="Status", value=status_val + low_warn, inline=True)
    em.set_footer(text=f"Signature activates below 30% HP")
    return em


# ─────────────────────────────────────────────
#  DUEL CARD BUILDERS
# ─────────────────────────────────────────────
def duel_card(name, class_name, gif, hp, hp_max, poison, regen, color, whose_turn: str, is_this_player: bool, footer="") -> discord.Embed:
    """One card per duelist — GIF shown large via set_image."""
    status_parts = []
    if poison: status_parts.append(f"☠ Poison ({poison} turns)")
    if regen:  status_parts.append(f"♻ Regen ({regen} turns)")
    status_val = "\n".join(status_parts) if status_parts else "—"

    turn_tag = "  🟢 YOUR TURN" if is_this_player else ""

    em = discord.Embed(color=color)
    em.set_author(name=f"{name}  ·  {class_name}{turn_tag}")
    em.set_image(url=ASSET_BASE_URL + gif)
    em.add_field(
        name="HP",
        value=f"`{hp_bar(hp, hp_max)}`\n**{hp} / {hp_max}**",
        inline=True,
    )
    em.add_field(name="Status", value=status_val, inline=True)
    if footer:
        em.set_footer(text=footer)
    return em


# ─────────────────────────────────────────────
#  PvE SESSION
# ─────────────────────────────────────────────
class GameSession:
    def __init__(self, player: discord.Member, chosen_class: dict, char_name: str, zodiac: str):
        self.player       = player
        self.chosen_class = chosen_class
        self.char_name    = char_name
        self.zodiac       = zodiac
        self.p_hp_max     = chosen_class["hp"]
        self.p_hp         = self.p_hp_max
        self.p_poison = self.p_regen = self.stored = self.pts_left = self.pts_total = 0
        self.p_defend     = False
        self.enemy        = None
        self.e_hp_max = self.e_hp = 0
        self.e_poison = self.e_regen = 0
        self.phase        = "select_enemy"
        self.queue: list  = []
        self.hard_mode: bool = False
        self.p_hp_max_battle: int = self.p_hp_max   # may be boosted in hard mode
        self.pinned_player: discord.Message | None = None   # player card pin
        self.pinned_enemy:  discord.Message | None = None   # enemy card pin

    def reset_for_battle(self, enemy_key: str, hard_mode: bool = False):
        e = ALL_ENEMIES[enemy_key]
        self.enemy     = e;  self.e_hp_max = e["hp"]; self.e_hp = self.e_hp_max
        self.e_poison  = self.e_regen = 0
        self.hard_mode = hard_mode
        # +100 HP bonus for hard mode battles
        bonus          = 100 if hard_mode else 0
        self.p_hp_max_battle = self.p_hp_max + bonus
        self.p_hp      = self.p_hp_max_battle
        self.p_poison  = self.p_regen = self.stored = 0
        self.p_defend  = False;  self.phase = "rolled";  self.queue = []
        self.pinned_player = None;  self.pinned_enemy = None

    async def refresh_pins(self, p_title="", e_title=""):
        if self.pinned_player:
            await edit_pin(self.pinned_player, pve_player_card(self, p_title))
        if self.pinned_enemy:
            await edit_pin(self.pinned_enemy,  pve_enemy_card(self, e_title))


# ─────────────────────────────────────────────
#  DUEL SESSION
# ─────────────────────────────────────────────
class DuelSession:
    def __init__(self, challenger: discord.Member, opponent: discord.Member,
                 cs: GameSession, os_: GameSession, channel: discord.TextChannel):
        self.challenger = challenger
        self.opponent   = opponent
        self.channel    = channel

        self.c_hp_max   = 400;  self.c_hp = self.c_hp_max
        self.c_poison   = self.c_regen = 0
        self.c_name     = cs.char_name;  self.c_class = cs.chosen_class["name"]
        self.c_gif      = cs.chosen_class["gif"]

        self.o_hp_max   = 400;  self.o_hp = self.o_hp_max
        self.o_poison   = self.o_regen = 0
        self.o_name     = os_.char_name; self.o_class = os_.chosen_class["name"]
        self.o_gif      = os_.chosen_class["gif"]

        self.turn       = "challenger"
        self.active     = True
        self.pinned_c:  discord.Message | None = None   # challenger card pin
        self.pinned_o:  discord.Message | None = None   # opponent card pin

    def current_player(self) -> discord.Member:
        return self.challenger if self.turn == "challenger" else self.opponent

    def swap_turn(self):
        self.turn = "opponent" if self.turn == "challenger" else "challenger"

    def c_card(self, title="") -> discord.Embed:
        is_turn = self.turn == "challenger"
        footer  = "Pick one move: !slash !fire !ice !thunder !poison !regen !cure" if is_turn else ""
        return duel_card(
            self.c_name, self.c_class, self.c_gif,
            self.c_hp, self.c_hp_max, self.c_poison, self.c_regen,
            color=0x1a3a8a, whose_turn=self.turn, is_this_player=is_turn, footer=footer,
        )

    def o_card(self, title="") -> discord.Embed:
        is_turn = self.turn == "opponent"
        footer  = "Pick one move: !slash !fire !ice !thunder !poison !regen !cure" if is_turn else ""
        return duel_card(
            self.o_name, self.o_class, self.o_gif,
            self.o_hp, self.o_hp_max, self.o_poison, self.o_regen,
            color=0x8b0000, whose_turn=self.turn, is_this_player=is_turn, footer=footer,
        )

    async def refresh_pins(self):
        if self.pinned_c: await edit_pin(self.pinned_c, self.c_card())
        if self.pinned_o: await edit_pin(self.pinned_o, self.o_card())

    def apply_move(self, move_key: str, attacker: str) -> str:
        move     = DUEL_MOVES[move_key]
        atk_name = self.c_name if attacker == "challenger" else self.o_name
        def_name = self.o_name if attacker == "challenger" else self.c_name
        if move["type"] == "atk":
            dmg = random.randint(*move["dmg"])
            if attacker == "challenger": self.o_hp = max(0, self.o_hp - dmg)
            else:                        self.c_hp = max(0, self.c_hp - dmg)
            return f"⚔ **{atk_name}** uses **{move_key.capitalize()}** on {def_name} for **{dmg}** damage!"
        elif move["type"] == "heal":
            h = random.randint(*move["heal"])
            if attacker == "challenger": self.c_hp = min(self.c_hp_max, self.c_hp + h)
            else:                        self.o_hp = min(self.o_hp_max, self.o_hp + h)
            return f"💚 **{atk_name}** uses **Cure** and restores **{h}** HP!"
        elif move["type"] == "status":
            if move["effect"] == "poison":
                if attacker == "challenger": self.o_poison = 3
                else:                        self.c_poison = 3
                return f"☠ **{atk_name}** poisons {def_name} for 3 turns!"
            elif move["effect"] == "regen":
                if attacker == "challenger": self.c_regen = 3
                else:                        self.o_regen = 3
                return f"♻ **{atk_name}** gains Regen for 3 turns!"
        return ""

    def tick_status(self) -> list[str]:
        lines = []
        for who in ("challenger", "opponent"):
            name = self.c_name if who == "challenger" else self.o_name
            if who == "challenger":
                if self.c_poison > 0:
                    self.c_hp = max(0, self.c_hp - 3); self.c_poison -= 1
                    lines.append(f"☠ {name} takes **3** poison damage!")
                if self.c_regen > 0:
                    h = random.randint(5, 10); self.c_hp = min(self.c_hp_max, self.c_hp + h); self.c_regen -= 1
                    lines.append(f"♻ {name} regenerates **{h}** HP!")
            else:
                if self.o_poison > 0:
                    self.o_hp = max(0, self.o_hp - 3); self.o_poison -= 1
                    lines.append(f"☠ {name} takes **3** poison damage!")
                if self.o_regen > 0:
                    h = random.randint(5, 10); self.o_hp = min(self.o_hp_max, self.o_hp + h); self.o_regen -= 1
                    lines.append(f"♻ {name} regenerates **{h}** HP!")
        return lines

    def is_over(self) -> str | None:
        if self.c_hp <= 0: return "opponent"
        if self.o_hp <= 0: return "challenger"
        return None


# ─────────────────────────────────────────────
#  BOT SETUP
# ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

active_sessions: dict[int, GameSession] = {}
player_channels: dict[int, int]         = {}
active_duels:    dict[int, DuelSession] = {}
pending_duels:   dict[int, dict]        = {}


# ─────────────────────────────────────────────
#  !FF
# ─────────────────────────────────────────────
@bot.command(name="FF")
async def start_ff(ctx: commands.Context):
    if ctx.author.id in player_channels:
        ch = bot.get_channel(player_channels[ctx.author.id])
        if ch:
            await ctx.send(f"{ctx.author.mention} You already have an active game: {ch.mention}"); return

    guild    = ctx.guild
    category = guild.get_channel(FF_CATEGORY_ID)
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=True, send_messages=False, add_reactions=False),
        ctx.author:         discord.PermissionOverwrite(view_channel=True, send_messages=True,  add_reactions=True),
        guild.me:           discord.PermissionOverwrite(view_channel=True, send_messages=True,  manage_channels=True),
    }
    channel_name = f"ff-{ctx.author.name.lower().replace(' ', '-')}"
    game_channel = await guild.create_text_channel(
        name=channel_name, category=category, overwrites=overwrites,
        topic=f"Final Fantasy RPG — {ctx.author.display_name}'s adventure",
    )
    player_channels[ctx.author.id] = game_channel.id
    await db_ensure(ctx.author.id)
    await ctx.send(f"✨ {ctx.author.mention} Your adventure awaits: {game_channel.mention}")
    await _send_class_select(game_channel)


async def _send_class_select(channel: discord.TextChannel):
    em = discord.Embed(title="⚔ Choose Your Class", description="Type `!class <name>` to select.", color=0x2a55c0)
    for key, c in CLASSES.items():
        em.add_field(name=f"`!class {key}` — {c['name']}", value=f"Role: {c['role']} | HP: {c['hp']}", inline=False)
    em.set_footer(text="e.g.  !class warrior")
    await channel.send(embed=em)


# ─────────────────────────────────────────────
#  CHARACTER CREATION
# ─────────────────────────────────────────────
@bot.command(name="class")
async def choose_class(ctx: commands.Context, class_key: str):
    if not _is_game_channel(ctx): return
    class_key = class_key.lower()
    if class_key not in CLASSES:
        await ctx.send(f"Unknown class. Choose from: {', '.join(CLASSES.keys())}"); return
    chosen = CLASSES[class_key]
    active_sessions[ctx.channel.id] = GameSession(ctx.author, chosen, "", "")
    em = discord.Embed(title=f"🌟 Class: {chosen['name']}", description=f"Role: **{chosen['role']}** | HP: **{chosen['hp']}**", color=0x2a55c0)
    em.set_image(url=ASSET_BASE_URL + chosen["gif"])
    em.add_field(name="Next", value="Enter your name: `!name YourName`", inline=False)
    await ctx.send(embed=em)


@bot.command(name="name")
async def set_name(ctx: commands.Context, *, char_name: str):
    if not _is_game_channel(ctx) or ctx.channel.id not in active_sessions: return
    if len(char_name) > 12:
        await ctx.send("Name must be 12 characters or fewer."); return
    active_sessions[ctx.channel.id].char_name = char_name
    em = discord.Embed(title=f"📜 Name: {char_name}", description="Now choose your birth month.", color=0x2a55c0)
    em.add_field(name="Type `!zodiac <month>`", value="\n".join(f"`{m}` → {z}" for m, z in ZODIAC_MAP.items()), inline=False)
    await ctx.send(embed=em)


@bot.command(name="zodiac")
async def set_zodiac(ctx: commands.Context, *, month: str):
    if not _is_game_channel(ctx) or ctx.channel.id not in active_sessions: return
    month = month.capitalize()
    if month not in ZODIAC_MAP:
        await ctx.send("Unknown month. Use a full month name, e.g. `!zodiac March`"); return
    s = active_sessions[ctx.channel.id]
    s.zodiac = f"{month} — {ZODIAC_MAP[month]}"
    em = discord.Embed(title="✨ Character Created!", color=0xf0d060)
    em.set_image(url=ASSET_BASE_URL + s.chosen_class["gif"])
    em.add_field(name="Name",   value=s.char_name,              inline=True)
    em.add_field(name="Class",  value=s.chosen_class["name"],   inline=True)
    em.add_field(name="Zodiac", value=s.zodiac,                 inline=True)
    em.add_field(name="Gil",    value=f"💰 {await db_get_gil(ctx.author.id)} gil", inline=True)
    em.set_footer(text="!fight to battle  |  !ffduel @user to challenge  |  !gil for balance")
    await ctx.send(embed=em)


# ─────────────────────────────────────────────
#  PvE BATTLE
# ─────────────────────────────────────────────
@bot.command(name="fight")
async def fight(ctx: commands.Context):
    if not _is_game_channel(ctx) or ctx.channel.id not in active_sessions: return
    em = discord.Embed(title="👹 Choose Your Opponent", color=0x2a55c0)
    # Normal bosses — always available
    for key, e in ENEMIES.items():
        em.add_field(
            name=f"`!battle {key}` — {e['name']}",
            value=f"HP: {e['hp']} | Signature: **{e['sig']['name']}** *(below 30% HP)*",
            inline=False,
        )
    # Hard mode bosses — show if unlocked
    unlocked = unlocked_hard.get(ctx.author.id, set())
    if unlocked:
        em.add_field(name="​", value="**🔓 Hard Mode Unlocked:**", inline=False)
        for key in unlocked:
            e = HARD_ENEMIES[key]
            thresh = int(e.get("sig_threshold", 0.4) * 100)
            em.add_field(
                name=f"`!battle {key}` — {e['name']} ☆",
                value=f"HP: {e['hp']} | Signature: **{e['sig']['name']}** *(below {thresh}% HP)* | You get **+100 HP**",
                inline=False,
            )
    else:
        em.add_field(name="​", value="🔒 Defeat each boss to unlock their **Hard Mode** version!", inline=False)
    await ctx.send(embed=em)


@bot.command(name="battle")
async def battle(ctx: commands.Context, enemy_key: str):
    if not _is_game_channel(ctx) or ctx.channel.id not in active_sessions: return
    enemy_key = enemy_key.lower()
    s = active_sessions[ctx.channel.id]
    is_hard = enemy_key.endswith("+")
    if enemy_key not in ALL_ENEMIES:
        await ctx.send(f"Unknown enemy. Use `!fight` to see available opponents."); return
    if is_hard and not is_unlocked(ctx.author.id, enemy_key):
        base = enemy_key.replace("+", "")
        await ctx.send(f"🔒 **{ALL_ENEMIES[enemy_key]['name']}** is locked! Defeat **{ENEMIES[base]['name']}** first."); return
    s.reset_for_battle(enemy_key, hard_mode=is_hard)

    # Send player card first, enemy card second — both pinned
    mode_tag = "  🔴 HARD MODE" if s.hard_mode else ""
    await ctx.send(f"═══════════════  ⚔ BATTLE START{mode_tag}  ═══════════════")
    p_msg = await ctx.send(embed=pve_player_card(s))
    e_msg = await ctx.send(embed=pve_enemy_card(s))
    await pin_msg(p_msg)
    await pin_msg(e_msg)
    s.pinned_player = p_msg
    s.pinned_enemy  = e_msg

    await ctx.send("🎲 Type `!roll` to roll your dice!")


@bot.command(name="roll")
async def roll_dice(ctx: commands.Context):
    s = _get_pve(ctx)
    if not s: return
    base = random.randint(1, 6); total = base + s.stored; s.stored = 0
    s.pts_left = s.pts_total = total
    faces = ["⚀","⚁","⚂","⚃","⚄","⚅"]
    note  = f" (+{total-base} stored) = **{total}**" if total > base else ""
    await s.refresh_pins()
    await ctx.send(
        f"{faces[base-1]} **{ctx.author.display_name}** rolled **{base}**{note}! **{s.pts_left}pt** to spend.\n"
        f"Moves: `!slash(1)` `!poison(3)` `!regen(3)` `!cure(4)` `!fire(5)` `!ice(5)` `!thunder(5)`\n"
        f"Queue moves then `!execute` — or `!defend` to store roll & halve damage."
    )


@bot.command(name="defend")
async def defend(ctx: commands.Context):
    s = _get_pve(ctx)
    if not s: return
    base = random.randint(1, 6); s.stored += base; s.p_defend = True
    faces = ["⚀","⚁","⚂","⚃","⚄","⚅"]
    await ctx.send(f"🛡 {faces[base-1]} **Defend**! Rolled **{base}** stored for next turn. Damage halved.")
    await s.refresh_pins()
    await _enemy_turn(ctx, s)


async def _queue_move(ctx: commands.Context, move_key: str):
    s = _get_pve(ctx)
    if not s: return
    move = MOVES[move_key]
    if s.pts_left < move["cost"]:
        await ctx.send(f"Not enough points for **{move_key.capitalize()}** (costs {move['cost']}pt, have {s.pts_left}pt)."); return
    s.pts_left -= move["cost"]; s.queue.append(move_key)
    await s.refresh_pins()
    await ctx.send(f"✅ **{move_key.capitalize()}** queued. **{s.pts_left}pt** left. Type `!execute` when ready.")


@bot.command(name="execute")
async def execute(ctx: commands.Context):
    s = _get_pve(ctx)
    if not s or not s.queue:
        await ctx.send("Nothing queued! Add moves then `!execute`."); return
    lines = []
    for mk in s.queue:
        m = MOVES[mk]
        if m["type"] == "atk":
            raw = random.randint(*m["dmg"])
            if s.hard_mode:
                dmg, outcome = calc_hit(raw)
            else:
                dmg, outcome = raw, "normal"
            if dmg > 0: s.e_hp = max(0, s.e_hp - dmg)
            lines.append(hit_line(mk.capitalize(), s.char_name, s.enemy['name'], outcome, dmg))
        elif m["type"] == "heal":
            h = random.randint(*m["heal"]); s.p_hp = min(s.p_hp_max_battle, s.p_hp + h)
            lines.append(f"💚 **Cure** restores **{h}** HP!")
        elif m["type"] == "status":
            if m["effect"] == "poison": s.e_poison = 3; lines.append(f"☠ **Poison** inflicted on {s.enemy['name']}!")
            elif m["effect"] == "regen": s.p_regen = 3; lines.append("♻ **Regen** granted!")
    s.queue = []
    await ctx.send("\n".join(lines))
    if s.e_hp <= 0:
        await s.refresh_pins("🏆 Victory!", "💀 Defeated")
        await _end_pve(ctx, s, won=True); return
    await _enemy_turn(ctx, s)


async def _enemy_turn(ctx: commands.Context, s: GameSession):
    tick = []
    if s.p_poison > 0: s.p_hp = max(0, s.p_hp - 3); s.p_poison -= 1; tick.append("☠ Poison deals **3** damage to you!")
    if s.p_regen  > 0:
        h = random.randint(5, 10); s.p_hp = min(s.p_hp_max_battle, s.p_hp + h); s.p_regen -= 1
        tick.append(f"♻ Regen restores **{h}** HP!")
    if tick: await ctx.send("\n".join(tick))
    if s.p_hp <= 0:
        await s.refresh_pins("💀 Defeated", "👹 Wins!")
        await _end_pve(ctx, s, won=False); return

    e = s.enemy; e_roll = random.randint(1, 6); e_pts = e_roll
    faces = ["⚀","⚁","⚂","⚃","⚄","⚅"]
    lines = [f"👹 **{e['name']}** rolls {faces[e_roll-1]} (**{e_roll}pt**)"]

    sig_thresh = s.enemy.get("sig_threshold", 0.3)
    if s.e_hp / s.e_hp_max < sig_thresh:
        sig = e["sig"]
        sig_range = e["hard"]["sig_dmg"] if s.hard_mode else sig["dmg"]
        raw = random.randint(*sig_range)
        if s.hard_mode:
            dmg, outcome = calc_hit(raw, halved=s.p_defend)
        else:
            dmg = raw // 2 if s.p_defend else raw
            outcome = "normal"
        if dmg > 0: s.p_hp = max(0, s.p_hp - dmg)
        halved_tag = " *(halved)*" if s.p_defend and dmg > 0 else ""
        if outcome == "miss":
            lines.append(f"💨 **{e['name']}** uses **{sig['name']}** — but it **MISSED**!")
        elif outcome == "crit":
            lines.append(f"💥 **CRITICAL!** **{e['name']}** uses **{sig['name']}** for **{dmg}** damage!{halved_tag}")
        else:
            lines.append(f"💥 **{e['name']}** uses **{sig['name']}** for **{dmg}** damage!{halved_tag}")
        e_pts = max(0, e_pts - 6)

    actions = []; att = 0
    while e_pts > 0 and att < 20:
        att += 1
        affordable = [(k, m) for k, m in MOVES.items() if m["cost"] <= e_pts]
        if not affordable: break
        mk, m = random.choice(affordable)
        if m["type"] == "atk":
            slash_range = e["hard"]["slash_dmg"] if (s.hard_mode and mk == "slash") else (e["slash_dmg"] if mk == "slash" else m["dmg"])
            raw = random.randint(*slash_range)
            if s.hard_mode:
                dmg, outcome = calc_hit(raw, halved=s.p_defend)
            else:
                dmg = raw // 2 if s.p_defend else raw
                outcome = "normal"
            if dmg > 0: s.p_hp = max(0, s.p_hp - dmg)
            tag = " 💥CRIT" if outcome == "crit" else (" 💨MISS" if outcome == "miss" else "")
            actions.append(f"**{mk.capitalize()}**{tag} ({dmg} dmg)")
        elif m["type"] == "heal":
            h = random.randint(*m["heal"]); s.e_hp = min(s.e_hp_max, s.e_hp + h); actions.append(f"**Cure** (+{h} HP)")
        elif m["type"] == "status":
            if m["effect"] == "poison" and s.p_poison == 0: s.p_poison = 3; actions.append("**Poison**")
            elif m["effect"] == "regen" and s.e_regen == 0: s.e_regen = 3; actions.append("**Regen**")
            else:
                slash_range = e["hard"]["slash_dmg"] if s.hard_mode else e["slash_dmg"]
                raw = random.randint(*slash_range)
                if s.hard_mode:
                    dmg, outcome = calc_hit(raw, halved=s.p_defend)
                else:
                    dmg = raw // 2 if s.p_defend else raw
                    outcome = "normal"
                if dmg > 0: s.p_hp = max(0, s.p_hp - dmg)
                tag = " 💥CRIT" if outcome == "crit" else (" 💨MISS" if outcome == "miss" else "")
                actions.append(f"**Slash**{tag} ({dmg} dmg)")
        e_pts -= m["cost"]
    if actions: lines.append(f"👹 {e['name']} uses: " + ", ".join(actions))

    if s.e_poison > 0: s.e_hp = max(0, s.e_hp - 3); s.e_poison -= 1; lines.append(f"☠ {e['name']} takes **3** poison damage!")
    if s.e_regen  > 0:
        h = random.randint(5, 10); s.e_hp = min(s.e_hp_max, s.e_hp + h); s.e_regen -= 1
        lines.append(f"♻ {e['name']} regenerates **{h}** HP!")

    s.p_defend = False
    await ctx.send("\n".join(lines))

    if s.p_hp <= 0:
        await s.refresh_pins("💀 Defeated", "👹 Wins!")
        await _end_pve(ctx, s, won=False); return
    if s.e_hp <= 0:
        await s.refresh_pins("🏆 Victory!", "💀 Defeated")
        await _end_pve(ctx, s, won=True); return

    await s.refresh_pins()
    await ctx.send("🎲 Your turn! Type `!roll`.")


async def _end_pve(ctx: commands.Context, s: GameSession, won: bool):
    if won:
        add_gil(ctx.author.id, GIL_WIN_PVE)
        # Determine if this was a normal or hard fight
        enemy_key = next((k for k, v in ALL_ENEMIES.items() if v is s.enemy), None)
        is_hard   = s.hard_mode
        hard_key  = (enemy_key + "+") if not is_hard and enemy_key else None

        # Unlock hard mode if normal boss was defeated
        newly_unlocked = False
        if not is_hard and enemy_key:
            if not is_unlocked(ctx.author.id, enemy_key + "+"):
                unlock_hard(ctx.author.id, enemy_key)
                newly_unlocked = True

        unlock_line = (
            f"\n\n🔓 **{s.enemy['name']} ☆ (Hard Mode)** is now unlocked! "
            f"Type `!battle {hard_key}` to challenge a stronger version with +100 HP for you!"
            if newly_unlocked else
            (f"\n\n⚔ Hard mode already unlocked! Try `!battle {hard_key}` for an even greater challenge."
             if hard_key and is_unlocked(ctx.author.id, hard_key) else "")
        )
        hard_clear = "\n\n🌟 **Hard Mode cleared!** You are a true legend." if is_hard else ""

        gil_bonus = GIL_WIN_PVE * 2 if is_hard else GIL_WIN_PVE
        if is_hard: add_gil(ctx.author.id, GIL_WIN_PVE)  # extra gil for hard mode

        em = discord.Embed(title="🏆 VICTORY!",
            description=(
                f"**Congratulations, {s.char_name}!**\n\n{random.choice(WIN_MSGS)}"
                f"\n\n💰 +{gil_bonus} gil! Balance: **{get_gil(ctx.author.id)} gil**"
                + unlock_line + hard_clear
            ),
            color=0x50e090)
        em.set_footer(text="!fight to see all opponents  |  !ffduel @user to challenge someone")
    else:
        lose_bal = await db_get_gil(ctx.author.id)
        em = discord.Embed(title="💀 DEFEATED",
            description=f"**{random.choice(LOSE_MSGS)}**\n\n💰 Balance: **{lose_bal} gil**",
            color=0xe05050)
        em.set_footer(text="!fight to try again.")
    await ctx.send(embed=em)
    s.p_hp = s.p_hp_max; s.p_hp_max_battle = s.p_hp_max
    s.p_poison = s.p_regen = s.stored = 0
    s.p_defend = False; s.queue = []; s.phase = "rolled"; s.hard_mode = False
    s.pinned_player = None; s.pinned_enemy = None


# ─────────────────────────────────────────────
#  DUEL SYSTEM
# ─────────────────────────────────────────────
@bot.command(name="ffduel")
async def ffduel(ctx: commands.Context, opponent: discord.Member):
    if not _is_game_channel(ctx):
        await ctx.send("Use this in your FF Arena channel!"); return
    if opponent.id == ctx.author.id:
        await ctx.send("You can't duel yourself!"); return

    c_session = active_sessions.get(ctx.channel.id)
    if not c_session or not c_session.char_name:
        await ctx.send("Finish character creation first (`!class`, `!name`, `!zodiac`)!"); return

    opp_ch_id = player_channels.get(opponent.id)
    if not opp_ch_id:
        await ctx.send(f"**{opponent.display_name}** hasn't started FF Arena yet!"); return

    o_session = active_sessions.get(opp_ch_id)
    if not o_session or not o_session.char_name:
        await ctx.send(f"**{opponent.display_name}** hasn't finished character creation yet!"); return

    if ctx.channel.id in active_duels:
        await ctx.send("There's already an active duel in this channel!"); return
    if ctx.author.id in pending_duels:
        await ctx.send("You already have a pending challenge out!"); return

    pending_duels[ctx.author.id] = {
        "opponent": opponent, "challenger": ctx.author,
        "c_session": c_session, "o_session": o_session, "channel": ctx.channel,
    }

    em = discord.Embed(title="⚔ Duel Challenge!",
        description=(
            f"{opponent.mention} — **{c_session.char_name}** [{c_session.chosen_class['name']}] challenges you!\n\n"
            f"Go to your channel and type:\n"
            f"`!duelaccept {ctx.author.mention}` to accept\n"
            f"`!dueldecline {ctx.author.mention}` to decline\n\n"
            f"⏱ You have **60 seconds** to respond."
        ), color=0x8b0000)
    em.set_footer(text=f"💰 Winner +{GIL_WIN_DUEL} gil | Loser -{GIL_LOSE_DUEL} gil")
    await ctx.send(embed=em)

    await asyncio.sleep(60)
    if ctx.author.id in pending_duels:
        del pending_duels[ctx.author.id]
        await ctx.send(f"⏱ Duel challenge to {opponent.mention} expired.")


@bot.command(name="duelaccept")
async def duel_accept(ctx: commands.Context, challenger: discord.Member):
    if not _is_game_channel(ctx): return
    data = pending_duels.get(challenger.id)
    if not data or data["opponent"].id != ctx.author.id:
        await ctx.send("No pending challenge from that player."); return
    del pending_duels[challenger.id]

    c_channel = data["channel"]
    await c_channel.set_permissions(ctx.author, send_messages=True, view_channel=True)

    duel = DuelSession(data["challenger"], ctx.author, data["c_session"], data["o_session"], c_channel)
    active_duels[c_channel.id] = duel

    # Send challenger card + opponent card — both pinned, both showing their GIF large
    await c_channel.send("═══════════════  ⚔ DUEL BEGINS  ═══════════════")
    c_msg = await c_channel.send(embed=duel.c_card())
    o_msg = await c_channel.send(embed=duel.o_card())
    await pin_msg(c_msg)
    await pin_msg(o_msg)
    duel.pinned_c = c_msg
    duel.pinned_o = o_msg

    await c_channel.send(
        f"💰 Stakes: Winner **+{GIL_WIN_DUEL} gil** | Loser **-{GIL_LOSE_DUEL} gil**\n"
        f"{duel.challenger.mention} goes first — pick one move:\n"
        f"`!slash` `!fire` `!ice` `!thunder` `!poison` `!regen` `!cure`"
    )
    await ctx.send(f"✅ Duel accepted! Head to {c_channel.mention} to fight!")


@bot.command(name="dueldecline")
async def duel_decline(ctx: commands.Context, challenger: discord.Member):
    data = pending_duels.get(challenger.id)
    if data and data["opponent"].id == ctx.author.id:
        del pending_duels[challenger.id]
        await data["channel"].send(f"❌ {ctx.author.display_name} declined the duel challenge.")
        await ctx.send("❌ Duel declined.")


async def _handle_duel_move(ctx: commands.Context, move_key: str) -> bool:
    duel = active_duels.get(ctx.channel.id)
    if not duel or not duel.active: return False

    if ctx.author.id != duel.current_player().id:
        await ctx.send(f"It's not your turn! Waiting for **{duel.current_player().display_name}**."); return True

    attacker = "challenger" if ctx.author.id == duel.challenger.id else "opponent"
    log = duel.apply_move(move_key, attacker)
    await ctx.send(log)

    winner_side = duel.is_over()
    if winner_side:
        await duel.refresh_pins()
        await _end_duel(ctx, duel, winner_side); return True

    if duel.turn == "opponent":
        tick = duel.tick_status()
        if tick: await ctx.send("\n".join(tick))
        winner_side = duel.is_over()
        if winner_side:
            await duel.refresh_pins()
            await _end_duel(ctx, duel, winner_side); return True

    duel.swap_turn()
    await duel.refresh_pins()
    return True


async def _end_duel(ctx: commands.Context, duel: DuelSession, winner_side: str):
    duel.active = False
    winner = duel.challenger if winner_side == "challenger" else duel.opponent
    loser  = duel.opponent   if winner_side == "challenger" else duel.challenger
    w_name = duel.c_name     if winner_side == "challenger" else duel.o_name
    l_name = duel.o_name     if winner_side == "challenger" else duel.c_name

    await db_add_gil(winner.id,  GIL_WIN_DUEL)
    await db_add_gil(loser.id,  -GIL_LOSE_DUEL)
    winner_bal = await db_get_gil(winner.id)
    loser_bal  = await db_get_gil(loser.id)

    em = discord.Embed(title="🏆 DUEL OVER!",
        description=(
            f"**{w_name}** defeats **{l_name}**!\n\n"
            f"💰 {winner.mention} gains **{GIL_WIN_DUEL} gil** → Balance: **{winner_bal} gil**\n"
            f"💸 {loser.mention} loses **{GIL_LOSE_DUEL} gil** → Balance: **{loser_bal} gil**"
        ), color=0xf0d060)
    await ctx.send(embed=em)

    try: await duel.channel.set_permissions(duel.opponent, overwrite=None)
    except Exception: pass
    del active_duels[duel.channel.id]


# Move commands — duel first, fall back to PvE
@bot.command(name="slash")
async def d_slash(ctx):
    if not await _handle_duel_move(ctx, "slash"): await _queue_move(ctx, "slash")

@bot.command(name="poison")
async def d_poison(ctx):
    if not await _handle_duel_move(ctx, "poison"): await _queue_move(ctx, "poison")

@bot.command(name="regen")
async def d_regen(ctx):
    if not await _handle_duel_move(ctx, "regen"): await _queue_move(ctx, "regen")

@bot.command(name="cure")
async def d_cure(ctx):
    if not await _handle_duel_move(ctx, "cure"): await _queue_move(ctx, "cure")

@bot.command(name="fire")
async def d_fire(ctx):
    if not await _handle_duel_move(ctx, "fire"): await _queue_move(ctx, "fire")

@bot.command(name="ice")
async def d_ice(ctx):
    if not await _handle_duel_move(ctx, "ice"): await _queue_move(ctx, "ice")

@bot.command(name="thunder")
async def d_thunder(ctx):
    if not await _handle_duel_move(ctx, "thunder"): await _queue_move(ctx, "thunder")


# ─────────────────────────────────────────────
#  !gil
# ─────────────────────────────────────────────
@bot.command(name="gil")
async def show_gil(ctx: commands.Context):
    if not _is_game_channel(ctx): return
    s    = active_sessions.get(ctx.channel.id)
    name = s.char_name if s else ctx.author.display_name
    bal  = await db_get_gil(ctx.author.id)
    em   = discord.Embed(title="💰 Gil Balance",
        description=f"**{name}** has **{bal} gil**", color=0xf0d060)
    em.set_footer(text=f"PvE win: +{GIL_WIN_PVE} gil  |  Duel win: +{GIL_WIN_DUEL} gil  |  Duel loss: -{GIL_LOSE_DUEL} gil")
    await ctx.send(embed=em)


# ─────────────────────────────────────────────
#  !stop — abort current PvE battle, return to enemy select
# ─────────────────────────────────────────────
@bot.command(name="stop")
async def stop_battle(ctx: commands.Context):
    if not _is_game_channel(ctx): return
    s = active_sessions.get(ctx.channel.id)
    if not s:
        await ctx.send("No active session found."); return
    if ctx.author.id != s.player.id:
        await ctx.send("Only the channel owner can stop the battle."); return

    # Reset all battle state cleanly
    s.enemy        = None
    s.e_hp         = s.e_hp_max = 0
    s.e_poison     = s.e_regen = 0
    s.p_hp         = s.p_hp_max
    s.p_poison     = s.p_regen = s.stored = s.pts_left = s.pts_total = 0
    s.p_defend     = False
    s.queue        = []
    s.hard_mode    = False
    s.phase        = "select_enemy"
    s.pinned_player = None
    s.pinned_enemy  = None

    em = discord.Embed(
        title="⚔ Battle Stopped",
        description="Returning to enemy select. Type `!fight` to choose your next opponent.",
        color=0x2a55c0,
    )
    await ctx.send(embed=em)


# ─────────────────────────────────────────────
#  !endgame
# ─────────────────────────────────────────────
@bot.command(name="endgame")
async def endgame(ctx: commands.Context):
    if not _is_game_channel(ctx): return
    await ctx.send("👋 Thanks for playing! This channel closes in 10 seconds.")
    await asyncio.sleep(10)
    cid = ctx.channel.id
    for uid, ch in list(player_channels.items()):
        if ch == cid: del player_channels[uid]; break
    active_sessions.pop(cid, None)
    active_duels.pop(cid, None)
    await ctx.channel.delete()


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def _is_game_channel(ctx: commands.Context) -> bool:
    return ctx.channel.id in active_sessions or ctx.channel.id in player_channels.values()

def _get_pve(ctx: commands.Context) -> GameSession | None:
    if ctx.channel.id in active_duels: return None
    s = active_sessions.get(ctx.channel.id)
    if not s or s.player.id != ctx.author.id: return None
    return s


@bot.event
async def on_ready():
    await init_db()
    print(f"✅ {bot.user} is online and ready!")

bot.run(BOT_TOKEN)

