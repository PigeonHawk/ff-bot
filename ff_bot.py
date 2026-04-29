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
ASSET_BASE_URL = "https://raw.githubusercontent.com/PigeonHawk/ff-bot/main/"
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

WIN_MSGS = [
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
MISS_CHANCE   = 0.15
CRIT_CHANCE   = 0.15

# ─────────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────────
db_pool = None

async def init_db():
    global db_pool
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("WARNING: No DATABASE_URL — data will not persist.")
        return
    db_pool = await asyncpg.create_pool(db_url)
    async with db_pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                user_id      BIGINT PRIMARY KEY,
                gil          INTEGER NOT NULL DEFAULT 200,
                hard_unlocked TEXT NOT NULL DEFAULT ''
            )
        """)
    print("Database connected and tables ready.")

async def db_ensure(uid: int):
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
            "UPDATE players SET gil = GREATEST(0, gil + $1) WHERE user_id=$2", amt, uid)

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
            ",".join(unlocked), uid)

# ─────────────────────────────────────────────
#  HELPERS
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

def calc_hit(base_dmg: int, halved: bool = False):
    roll = random.random()
    if roll < MISS_CHANCE:
        return 0, "miss"
    dmg = base_dmg * 2 if roll >= (1 - CRIT_CHANCE) else base_dmg
    if halved: dmg = dmg // 2
    outcome = "crit" if roll >= (1 - CRIT_CHANCE) else "normal"
    return dmg, outcome

def hit_line(move_name, atk, def_, outcome, dmg) -> str:
    if outcome == "miss":
        return f"💨 **{atk}** uses **{move_name}** — **MISSED** {def_}!"
    if outcome == "crit":
        return f"💥 **CRITICAL HIT!** **{atk}** lands **{move_name}** on {def_} for **{dmg}** damage!"
    return f"⚔ **{atk}** uses **{move_name}** on {def_} for **{dmg}** damage!"

# ─────────────────────────────────────────────
#  CARD BUILDERS
# ─────────────────────────────────────────────
def pve_player_card(s, title="") -> discord.Embed:
    status_parts = []
    if s.p_poison: status_parts.append(f"☠ Poison ({s.p_poison} turns)")
    if s.p_regen:  status_parts.append(f"♻ Regen ({s.p_regen} turns)")
    if s.p_defend: status_parts.append("🛡 Defending")
    if s.stored:   status_parts.append(f"📦 Stored +{s.stored}pt")
    status_val = "\n".join(status_parts) if status_parts else "—"
    pts_line   = f"\n\n🎲 **{s.pts_left}pt** remaining" if s.pts_left else ""
    queue_line = f"\n📋 **{' → '.join(q.capitalize() for q in s.queue)}**" if s.queue else ""
    em = discord.Embed(title=title or f"⚔ {s.char_name}", color=0x1a3a8a)
    em.set_author(name=f"{s.char_name}  ·  {s.chosen_class['name']}  ·  {s.chosen_class['role']}")
    em.set_image(url=ASSET_BASE_URL + s.chosen_class["gif"])
    em.add_field(name="HP", value=f"`{hp_bar(s.p_hp, s.p_hp_max)}`\n**{s.p_hp} / {s.p_hp_max}**", inline=True)
    em.add_field(name="Status", value=status_val + pts_line + queue_line, inline=True)
    em.set_footer(text="Buttons below — Roll dice, pick moves, then Execute")
    return em

def pve_enemy_card(s, title="") -> discord.Embed:
    e = s.enemy
    status_parts = []
    if s.e_poison: status_parts.append(f"☠ Poison ({s.e_poison} turns)")
    if s.e_regen:  status_parts.append(f"♻ Regen ({s.e_regen} turns)")
    status_val = "\n".join(status_parts) if status_parts else "—"
    low_warn = "\n\n⚠️ **Signature move ready!**" if s.e_hp > 0 and s.e_hp / s.e_hp_max < 0.3 else ""
    em = discord.Embed(title=title or f"👹 {e['name']}", color=0x8b0000)
    em.set_author(name=f"{e['name']}  ·  Signature: {e['sig']['name']}")
    em.set_image(url=ASSET_BASE_URL + e["gif"])
    em.add_field(name="HP", value=f"`{hp_bar(s.e_hp, s.e_hp_max)}`\n**{s.e_hp} / {s.e_hp_max}**", inline=True)
    em.add_field(name="Status", value=status_val + low_warn, inline=True)
    em.set_footer(text="Signature activates below 30% HP")
    return em

def duel_card(name, class_name, gif, hp, hp_max, poison, regen, color, is_turn) -> discord.Embed:
    status_parts = []
    if poison: status_parts.append(f"☠ Poison ({poison} turns)")
    if regen:  status_parts.append(f"♻ Regen ({regen} turns)")
    status_val = "\n".join(status_parts) if status_parts else "—"
    turn_tag = "  🟢 YOUR TURN" if is_turn else ""
    em = discord.Embed(color=color)
    em.set_author(name=f"{name}  ·  {class_name}{turn_tag}")
    em.set_image(url=ASSET_BASE_URL + gif)
    em.add_field(name="HP", value=f"`{hp_bar(hp, hp_max)}`\n**{hp} / {hp_max}**", inline=True)
    em.add_field(name="Status", value=status_val, inline=True)
    return em

# ─────────────────────────────────────────────
#  PvE SESSION
# ─────────────────────────────────────────────
class GameSession:
    def __init__(self, player, chosen_class, char_name, zodiac):
        self.player        = player
        self.chosen_class  = chosen_class
        self.char_name     = char_name
        self.zodiac        = zodiac
        self.p_hp_max      = chosen_class["hp"]
        self.p_hp          = self.p_hp_max
        self.p_poison = self.p_regen = self.stored = self.pts_left = self.pts_total = 0
        self.p_defend      = False
        self.enemy         = None
        self.e_hp_max = self.e_hp = 0
        self.e_poison = self.e_regen = 0
        self.hard_mode     = False
        self.unlocked_hard = set()
        self.queue         = []
        self.phase         = "select_enemy"
        self.pinned_player = None
        self.pinned_enemy  = None

    def reset_for_battle(self, enemy_key, hard=False):
        e = ENEMIES[enemy_key]
        self.enemy     = e
        self.hard_mode = hard
        self.e_hp_max  = e["hard"]["hp"] if hard else e["hp"]
        self.e_hp      = self.e_hp_max
        self.e_poison  = self.e_regen = 0
        self.p_hp_max  = self.chosen_class["hp"] + (50 if hard else 0)
        self.p_hp      = self.p_hp_max
        self.p_poison  = self.p_regen = self.stored = 0
        self.p_defend  = False
        self.queue     = []
        self.phase     = "battle"
        self.pinned_player = None
        self.pinned_enemy  = None

    async def refresh_pins(self, p_title="", e_title=""):
        if self.pinned_player:
            await edit_pin(self.pinned_player, pve_player_card(self, p_title))
        if self.pinned_enemy:
            await edit_pin(self.pinned_enemy, pve_enemy_card(self, e_title))

# ─────────────────────────────────────────────
#  DUEL SESSION
# ─────────────────────────────────────────────
class DuelSession:
    def __init__(self, challenger, opponent, cs, os_, channel):
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
        self.pinned_c   = None
        self.pinned_o   = None

    def current_player(self):
        return self.challenger if self.turn == "challenger" else self.opponent

    def swap_turn(self):
        self.turn = "opponent" if self.turn == "challenger" else "challenger"

    async def refresh_pins(self):
        if self.pinned_c:
            await edit_pin(self.pinned_c, duel_card(
                self.c_name, self.c_class, self.c_gif,
                self.c_hp, self.c_hp_max, self.c_poison, self.c_regen,
                0x1a3a8a, self.turn == "challenger"))
        if self.pinned_o:
            await edit_pin(self.pinned_o, duel_card(
                self.o_name, self.o_class, self.o_gif,
                self.o_hp, self.o_hp_max, self.o_poison, self.o_regen,
                0x8b0000, self.turn == "opponent"))

    def apply_move(self, move_key, attacker) -> str:
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

    def tick_status(self):
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

    def is_over(self):
        if self.c_hp <= 0: return "opponent"
        if self.o_hp <= 0: return "challenger"
        return None

# ─────────────────────────────────────────────
#  ENEMY TURN LOGIC
# ─────────────────────────────────────────────
async def run_enemy_turn(channel, s: GameSession):
    tick = []
    if s.p_poison > 0:
        s.p_hp = max(0, s.p_hp - 3); s.p_poison -= 1
        tick.append("☠ Poison deals **3** damage to you!")
    if s.p_regen > 0:
        h = random.randint(5, 10); s.p_hp = min(s.p_hp_max, s.p_hp + h); s.p_regen -= 1
        tick.append(f"♻ Regen restores **{h}** HP!")
    if tick: await channel.send("\n".join(tick))
    if s.p_hp <= 0:
        await s.refresh_pins("💀 Defeated", "👹 Wins!")
        await end_pve(channel, s, won=False); return

    e      = s.enemy
    e_roll = random.randint(1, 6); e_pts = e_roll
    faces  = ["⚀","⚁","⚂","⚃","⚄","⚅"]
    lines  = [f"👹 **{e['name']}** rolls {faces[e_roll-1]} (**{e_roll}pt**)"]

    if s.e_hp / s.e_hp_max < 0.3:
        sig = e["sig"]
        sig_range = e["hard"]["sig_dmg"] if s.hard_mode else sig["dmg"]
        raw = random.randint(*sig_range)
        if s.hard_mode: dmg, outcome = calc_hit(raw, halved=s.p_defend)
        else:
            dmg = raw // 2 if s.p_defend else raw
            outcome = "normal"
        if dmg > 0: s.p_hp = max(0, s.p_hp - dmg)
        halved_tag = " *(halved)*" if s.p_defend and dmg > 0 else ""
        if outcome == "miss":   lines.append(f"💨 **{e['name']}** uses **{sig['name']}** — MISSED!")
        elif outcome == "crit": lines.append(f"💥 **CRITICAL!** **{e['name']}** uses **{sig['name']}** for **{dmg}** damage!{halved_tag}")
        else:                   lines.append(f"💥 **{e['name']}** uses **{sig['name']}** for **{dmg}** damage!{halved_tag}")
        e_pts = max(0, e_pts - 6)

    actions = []; att = 0
    while e_pts > 0 and att < 20:
        att += 1
        affordable = [(k, m) for k, m in MOVES.items() if m["cost"] <= e_pts]
        if not affordable: break
        mk, m = random.choice(affordable)
        if m["type"] == "atk":
            slash_r = e["hard"]["slash_dmg"] if (s.hard_mode and mk == "slash") else (e["slash_dmg"] if mk == "slash" else m["dmg"])
            raw = random.randint(*slash_r)
            if s.hard_mode: dmg, outcome = calc_hit(raw, halved=s.p_defend)
            else:
                dmg = raw // 2 if s.p_defend else raw
                outcome = "normal"
            if dmg > 0: s.p_hp = max(0, s.p_hp - dmg)
            tag = " 💥CRIT" if outcome == "crit" else (" 💨MISS" if outcome == "miss" else "")
            actions.append(f"**{mk.capitalize()}**{tag} ({dmg} dmg)")
        elif m["type"] == "heal":
            h = random.randint(*m["heal"]); s.e_hp = min(s.e_hp_max, s.e_hp + h)
            actions.append(f"**Cure** (+{h} HP)")
        elif m["type"] == "status":
            if m["effect"] == "poison" and s.p_poison == 0:
                s.p_poison = 3; actions.append("**Poison**")
            elif m["effect"] == "regen" and s.e_regen == 0:
                s.e_regen = 3; actions.append("**Regen**")
            else:
                slash_r = e["hard"]["slash_dmg"] if s.hard_mode else e["slash_dmg"]
                raw = random.randint(*slash_r)
                if s.hard_mode: dmg, outcome = calc_hit(raw, halved=s.p_defend)
                else:
                    dmg = raw // 2 if s.p_defend else raw
                    outcome = "normal"
                if dmg > 0: s.p_hp = max(0, s.p_hp - dmg)
                tag = " 💥CRIT" if outcome == "crit" else (" 💨MISS" if outcome == "miss" else "")
                actions.append(f"**Slash**{tag} ({dmg} dmg)")
        e_pts -= m["cost"]

    if actions: lines.append(f"👹 {e['name']} uses: " + ", ".join(actions))

    if s.e_poison > 0:
        s.e_hp = max(0, s.e_hp - 3); s.e_poison -= 1
        lines.append(f"☠ {e['name']} takes **3** poison damage!")
    if s.e_regen > 0:
        h = random.randint(5, 10); s.e_hp = min(s.e_hp_max, s.e_hp + h); s.e_regen -= 1
        lines.append(f"♻ {e['name']} regenerates **{h}** HP!")

    s.p_defend = False
    await channel.send("\n".join(lines))
    await s.refresh_pins()

    if s.p_hp <= 0:
        await s.refresh_pins("💀 Defeated", "👹 Wins!")
        await end_pve(channel, s, won=False); return
    if s.e_hp <= 0:
        await s.refresh_pins("🏆 Victory!", "💀 Defeated")
        await end_pve(channel, s, won=True); return

    await channel.send("Your turn! What will you do?", view=RollAgainView(s))


class RollAgainView(discord.ui.View):
    """Sent after enemy turn completes — Roll Again | Status | Stop."""
    def __init__(self, session: GameSession):
        super().__init__(timeout=300)
        self.session = session

    @discord.ui.button(label="🎲 Roll Again", style=discord.ButtonStyle.primary, row=0)
    async def roll_again_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.session
        if interaction.user.id != s.player.id:
            await interaction.response.send_message("This is not your battle!", ephemeral=True); return
        base  = random.randint(1, 6); total = base + s.stored; s.stored = 0
        s.pts_left = s.pts_total = total
        faces = ["⚀","⚁","⚂","⚃","⚄","⚅"]
        note  = f" (+{total - base} stored) = **{total}**" if total > base else ""
        self.stop()
        await interaction.response.send_message(
            f"{faces[base-1]} **{interaction.user.display_name}** rolled **{base}**{note}!\n**{s.pts_left}pt** to spend — pick your moves:",
            view=MoveView(s)
        )
        await s.refresh_pins()

    @discord.ui.button(label="📊 Status", style=discord.ButtonStyle.secondary, row=0)
    async def status_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.session
        if interaction.user.id != s.player.id:
            await interaction.response.send_message("This is not your battle!", ephemeral=True); return
        await interaction.response.send_message(
            embeds=[pve_player_card(s), pve_enemy_card(s)],
            ephemeral=True
        )

    @discord.ui.button(label="🛑 Stop Battle", style=discord.ButtonStyle.danger, row=1)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.session
        if interaction.user.id != s.player.id:
            await interaction.response.send_message("This is not your battle!", ephemeral=True); return
        self.stop()
        s.phase = "select_enemy"; s.enemy = None; s.queue = []; s.pinned_player = None; s.pinned_enemy = None
        s.unlocked_hard = await db_get_hard_unlocked(interaction.user.id)
        em = discord.Embed(title="⚔ Battle Stopped", description="Choose your next opponent.", color=0x2a55c0)
        await interaction.response.send_message(embed=em, view=FightMenuView(s))


async def end_pve(channel, s: GameSession, won: bool):
    uid = s.player.id
    if won:
        gil_bonus = GIL_WIN_PVE * 2 if s.hard_mode else GIL_WIN_PVE
        await db_add_gil(uid, gil_bonus)
        hard_msg = ""
        if not s.hard_mode:
            enemy_key = next(k for k, v in ENEMIES.items() if v is s.enemy)
            s.unlocked_hard = await db_get_hard_unlocked(uid)
            if enemy_key not in s.unlocked_hard:
                await db_unlock_hard(uid, enemy_key)
                s.unlocked_hard.add(enemy_key)
                hard_msg = f"\n\n🔴 **HARD MODE UNLOCKED:** {s.enemy['name']} (Hard)!\nType `!fight` to see it."
        mode_tag = " *(Hard Mode)*" if s.hard_mode else ""
        new_bal  = await db_get_gil(uid)
        em = discord.Embed(title="🏆 VICTORY!",
            description=f"**Congratulations, {s.char_name}!**{mode_tag}\n\n{random.choice(WIN_MSGS)}\n\n💰 +{gil_bonus} gil! Balance: **{new_bal} gil**{hard_msg}",
            color=0x50e090)
    else:
        lose_bal = await db_get_gil(uid)
        em = discord.Embed(title="💀 DEFEATED",
            description=f"**{random.choice(LOSE_MSGS)}**\n\n💰 Balance: **{lose_bal} gil**",
            color=0xe05050)
    s.phase        = "select_enemy"
    s.pinned_player = None
    s.pinned_enemy  = None
    s.unlocked_hard = await db_get_hard_unlocked(uid)
    await channel.send(embed=em, view=FightMenuView(s))

async def end_duel(channel, duel: DuelSession, winner_side: str):
    duel.active = False
    winner = duel.challenger if winner_side == "challenger" else duel.opponent
    loser  = duel.opponent   if winner_side == "challenger" else duel.challenger
    w_name = duel.c_name     if winner_side == "challenger" else duel.o_name
    l_name = duel.o_name     if winner_side == "challenger" else duel.c_name
    await db_add_gil(winner.id,  GIL_WIN_DUEL)
    await db_add_gil(loser.id,  -GIL_LOSE_DUEL)
    wb = await db_get_gil(winner.id); lb = await db_get_gil(loser.id)
    em = discord.Embed(title="🏆 DUEL OVER!",
        description=(
            f"**{w_name}** defeats **{l_name}**!\n\n"
            f"💰 {winner.mention} gains **{GIL_WIN_DUEL} gil** → Balance: **{wb} gil**\n"
            f"💸 {loser.mention} loses **{GIL_LOSE_DUEL} gil** → Balance: **{lb} gil**"
        ), color=0xf0d060)
    await channel.send(embed=em)
    try: await duel.channel.set_permissions(duel.opponent, overwrite=None)
    except Exception: pass
    if channel.id in active_duels: del active_duels[channel.id]

# ─────────────────────────────────────────────
#  VIEWS
# ─────────────────────────────────────────────
class FightMenuView(discord.ui.View):
    def __init__(self, session: GameSession):
        super().__init__(timeout=300)
        self.session = session
        for key, e in ENEMIES.items():
            btn = discord.ui.Button(label=f"⚔ {e['name']}", style=discord.ButtonStyle.danger, custom_id=f"fight_{key}")
            btn.callback = self._make_cb(key, False)
            self.add_item(btn)
            if key in session.unlocked_hard:
                hbtn = discord.ui.Button(label=f"🔴 {e['name']} (Hard)", style=discord.ButtonStyle.danger, custom_id=f"fight_{key}_hard")
                hbtn.callback = self._make_cb(key, True)
                self.add_item(hbtn)

    def _make_cb(self, key, hard):
        async def cb(interaction: discord.Interaction):
            s = self.session
            if interaction.user.id != s.player.id:
                await interaction.response.send_message("This is not your battle!", ephemeral=True); return
            self.stop()
            s.reset_for_battle(key, hard=hard)
            mode_tag = "  🔴 HARD MODE" if hard else ""
            await interaction.response.send_message(f"═══════  ⚔ BATTLE START{mode_tag}  ═══════")
            ch = interaction.channel
            p_msg = await ch.send(embed=pve_player_card(s))
            e_msg = await ch.send(embed=pve_enemy_card(s))
            await pin_msg(p_msg); await pin_msg(e_msg)
            s.pinned_player = p_msg; s.pinned_enemy = e_msg
            await ch.send("Your turn! What will you do?", view=RollView(s))
        return cb


class RollView(discord.ui.View):
    """Row 0: Roll | Status   Row 1: Stop"""
    def __init__(self, session: GameSession):
        super().__init__(timeout=300)
        self.session = session

    @discord.ui.button(label="🎲 Roll Dice", style=discord.ButtonStyle.primary, row=0)
    async def roll_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.session
        if interaction.user.id != s.player.id:
            await interaction.response.send_message("This is not your battle!", ephemeral=True); return
        base  = random.randint(1, 6); total = base + s.stored; s.stored = 0
        s.pts_left = s.pts_total = total
        faces = ["⚀","⚁","⚂","⚃","⚄","⚅"]
        note  = f" (+{total - base} stored) = **{total}**" if total > base else ""
        self.stop()
        await interaction.response.send_message(
            f"{faces[base-1]} **{interaction.user.display_name}** rolled **{base}**{note}!\n**{s.pts_left}pt** to spend — pick your moves:",
            view=MoveView(s)
        )
        await s.refresh_pins()

    @discord.ui.button(label="📊 Status", style=discord.ButtonStyle.secondary, row=0)
    async def status_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.session
        if interaction.user.id != s.player.id:
            await interaction.response.send_message("This is not your battle!", ephemeral=True); return
        await interaction.response.send_message(
            embeds=[pve_player_card(s), pve_enemy_card(s)],
            ephemeral=True
        )

    @discord.ui.button(label="🛑 Stop Battle", style=discord.ButtonStyle.danger, row=1)
    async def stop_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        s = self.session
        if interaction.user.id != s.player.id:
            await interaction.response.send_message("This is not your battle!", ephemeral=True); return
        self.stop()
        s.phase = "select_enemy"; s.enemy = None; s.queue = []; s.pinned_player = None; s.pinned_enemy = None
        s.unlocked_hard = await db_get_hard_unlocked(interaction.user.id)
        em = discord.Embed(title="⚔ Battle Stopped", description="Choose your next opponent.", color=0x2a55c0)
        await interaction.response.send_message(embed=em, view=FightMenuView(s))


class MoveView(discord.ui.View):
    MOVE_DEFS = [
        ("⚔ Slash  (1pt)",    "slash",   discord.ButtonStyle.secondary, 1),
        ("☠ Poison  (3pt)",   "poison",  discord.ButtonStyle.secondary, 3),
        ("♻ Regen  (3pt)",    "regen",   discord.ButtonStyle.success,   3),
        ("💚 Cure  (4pt)",     "cure",    discord.ButtonStyle.success,   4),
        ("🔥 Fire  (5pt)",     "fire",    discord.ButtonStyle.danger,    5),
        ("❄ Ice  (5pt)",      "ice",     discord.ButtonStyle.danger,    5),
        ("⚡ Thunder  (5pt)",  "thunder", discord.ButtonStyle.danger,    5),
    ]

    def __init__(self, session: GameSession):
        super().__init__(timeout=300)
        self.session = session
        self._rebuild()

    def _rebuild(self):
        self.clear_items()
        s = self.session
        # Row 0 + 1: move buttons (max 5 per row)
        for i, (label, key, style, cost) in enumerate(self.MOVE_DEFS):
            row = 0 if i < 4 else 1
            btn = discord.ui.Button(label=label, style=style, disabled=s.pts_left < cost, custom_id=f"mv_{key}", row=row)
            btn.callback = self._make_move_cb(key, cost)
            self.add_item(btn)
        # Row 2: Execute | Status | Roll Again
        exec_btn = discord.ui.Button(
            label=f"✅ Execute ({len(s.queue)} queued)" if s.queue else "✅ Execute",
            style=discord.ButtonStyle.primary,
            disabled=not s.queue,
            custom_id="mv_execute",
            row=2
        )
        exec_btn.callback = self._execute_cb
        self.add_item(exec_btn)

        defend_btn = discord.ui.Button(
            label="🛡 Defend  (store roll + halve damage)",
            style=discord.ButtonStyle.secondary,
            custom_id="mv_defend",
            row=2
        )
        defend_btn.callback = self._defend_cb
        self.add_item(defend_btn)

        status_btn = discord.ui.Button(
            label="📊 Status",
            style=discord.ButtonStyle.secondary,
            custom_id="mv_status",
            row=2
        )
        status_btn.callback = self._status_cb
        self.add_item(status_btn)

    def _make_move_cb(self, key, cost):
        async def cb(interaction: discord.Interaction):
            s = self.session
            if interaction.user.id != s.player.id:
                await interaction.response.send_message("This is not your battle!", ephemeral=True); return
            if s.pts_left < cost:
                await interaction.response.send_message(f"Not enough points!", ephemeral=True); return
            s.pts_left -= cost; s.queue.append(key)
            await s.refresh_pins()
            self._rebuild()
            queue_str = " → ".join(q.capitalize() for q in s.queue)
            await interaction.response.edit_message(
                content=f"✅ **{key.capitalize()}** queued! Queue: **{queue_str}** | **{s.pts_left}pt** left — pick more or Execute:",
                view=self
            )
        return cb

    async def _defend_cb(self, interaction: discord.Interaction):
        s = self.session
        if interaction.user.id != s.player.id:
            await interaction.response.send_message("This is not your battle!", ephemeral=True); return
        # Cancel any queued moves — defending ends the turn
        s.queue = []
        base = random.randint(1, 6); s.stored += base; s.p_defend = True
        faces = ["⚀","⚁","⚂","⚃","⚄","⚅"]
        self.stop()
        await interaction.response.edit_message(
            content=(
                f"🛡 {faces[base-1]} **Defend!** Rolled **{base}** — stored for next turn. Damage halved this turn.\n"
                f"📦 Stored roll: **{s.stored}pt** carries into your next dice roll."
            ),
            view=None
        )
        await s.refresh_pins()
        await run_enemy_turn(interaction.channel, s)

    async def _status_cb(self, interaction: discord.Interaction):
        s = self.session
        if interaction.user.id != s.player.id:
            await interaction.response.send_message("This is not your battle!", ephemeral=True); return
        await interaction.response.send_message(
            embeds=[pve_player_card(s), pve_enemy_card(s)],
            ephemeral=True
        )

    async def _execute_cb(self, interaction: discord.Interaction):
        s = self.session
        if interaction.user.id != s.player.id:
            await interaction.response.send_message("This is not your battle!", ephemeral=True); return
        if not s.queue:
            await interaction.response.send_message("Nothing queued!", ephemeral=True); return
        self.stop()
        lines = []
        for mk in s.queue:
            m = MOVES[mk]
            if m["type"] == "atk":
                raw = random.randint(*m["dmg"])
                dmg, outcome = calc_hit(raw) if s.hard_mode else (raw, "normal")
                if dmg > 0: s.e_hp = max(0, s.e_hp - dmg)
                lines.append(hit_line(mk.capitalize(), s.char_name, s.enemy["name"], outcome, dmg))
            elif m["type"] == "heal":
                h = random.randint(*m["heal"]); s.p_hp = min(s.p_hp_max, s.p_hp + h)
                lines.append(f"💚 **Cure** restores **{h}** HP!")
            elif m["type"] == "status":
                if m["effect"] == "poison": s.e_poison = 3; lines.append(f"☠ **Poison** inflicted on {s.enemy['name']}!")
                elif m["effect"] == "regen": s.p_regen = 3; lines.append("♻ **Regen** granted!")
        s.queue = []
        await interaction.response.edit_message(content="\n".join(lines), view=None)
        await s.refresh_pins()
        if s.e_hp <= 0:
            await s.refresh_pins("🏆 Victory!", "💀 Defeated")
            await end_pve(interaction.channel, s, won=True); return
        await run_enemy_turn(interaction.channel, s)


class DuelMoveView(discord.ui.View):
    DUEL_DEFS = [
        ("⚔ Slash",    "slash",   discord.ButtonStyle.secondary),
        ("☠ Poison",   "poison",  discord.ButtonStyle.secondary),
        ("♻ Regen",    "regen",   discord.ButtonStyle.success),
        ("💚 Cure",     "cure",    discord.ButtonStyle.success),
        ("🔥 Fire",     "fire",    discord.ButtonStyle.danger),
        ("❄ Ice",      "ice",     discord.ButtonStyle.danger),
        ("⚡ Thunder",  "thunder", discord.ButtonStyle.danger),
    ]

    def __init__(self, duel: DuelSession):
        super().__init__(timeout=300)
        self.duel = duel
        for label, key, style in self.DUEL_DEFS:
            btn = discord.ui.Button(label=label, style=style, custom_id=f"duel_{key}")
            btn.callback = self._make_cb(key)
            self.add_item(btn)

    def _make_cb(self, move_key):
        async def cb(interaction: discord.Interaction):
            duel = self.duel
            if not duel.active:
                await interaction.response.send_message("This duel is over!", ephemeral=True); return
            if interaction.user.id != duel.current_player().id:
                await interaction.response.send_message(
                    f"It's not your turn! Waiting for **{duel.current_player().display_name}**.", ephemeral=True); return
            attacker = "challenger" if interaction.user.id == duel.challenger.id else "opponent"
            log = duel.apply_move(move_key, attacker)
            self.stop()
            await interaction.response.edit_message(content=log, view=None)
            await duel.refresh_pins()
            winner_side = duel.is_over()
            if winner_side:
                await end_duel(interaction.channel, duel, winner_side); return
            if duel.turn == "opponent":
                tick = duel.tick_status()
                if tick: await interaction.channel.send("\n".join(tick))
                await duel.refresh_pins()
                winner_side = duel.is_over()
                if winner_side:
                    await end_duel(interaction.channel, duel, winner_side); return
            duel.swap_turn()
            await duel.refresh_pins()
            whose = duel.current_player().mention
            await interaction.channel.send(f"{whose} — your turn! Pick a move:", view=DuelMoveView(duel))
        return cb

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
    await send_class_select(game_channel)

async def send_class_select(channel):
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
        await ctx.send("Unknown month. Use a full month name e.g. `!zodiac March`"); return
    s = active_sessions[ctx.channel.id]
    s.zodiac = f"{month} — {ZODIAC_MAP[month]}"
    s.unlocked_hard = await db_get_hard_unlocked(ctx.author.id)
    bal = await db_get_gil(ctx.author.id)
    em = discord.Embed(title="✨ Character Created!", color=0xf0d060)
    em.set_image(url=ASSET_BASE_URL + s.chosen_class["gif"])
    em.add_field(name="Name",   value=s.char_name,            inline=True)
    em.add_field(name="Class",  value=s.chosen_class["name"], inline=True)
    em.add_field(name="Zodiac", value=s.zodiac,               inline=True)
    em.add_field(name="Gil",    value=f"💰 {bal} gil",         inline=True)
    em.set_footer(text="!fight to battle  |  !ffduel @user to challenge  |  !gil for balance  |  !ffreset to restart")
    await ctx.send(embed=em)

# ─────────────────────────────────────────────
#  !fight — button enemy select
# ─────────────────────────────────────────────
@bot.command(name="fight")
async def fight(ctx: commands.Context):
    if not _is_game_channel(ctx) or ctx.channel.id not in active_sessions: return
    s = active_sessions[ctx.channel.id]
    s.unlocked_hard = await db_get_hard_unlocked(ctx.author.id)
    em = discord.Embed(title="👹 Choose Your Opponent", description="Click an enemy to begin!", color=0x2a55c0)
    for key, e in ENEMIES.items():
        lock = "🔒 Hard locked" if key not in s.unlocked_hard else "🔴 Hard available"
        em.add_field(name=e["name"], value=f"HP: {e['hp']} | {lock}", inline=True)
    await ctx.send(embed=em, view=FightMenuView(s))

# ─────────────────────────────────────────────
#  !ffduel @user
# ─────────────────────────────────────────────
@bot.command(name="ffduel")
async def ffduel(ctx: commands.Context, opponent: discord.Member):
    if not _is_game_channel(ctx):
        await ctx.send("Use this in your FF Arena channel!"); return
    if opponent.id == ctx.author.id:
        await ctx.send("You can't duel yourself!"); return
    c_session = active_sessions.get(ctx.channel.id)
    if not c_session or not c_session.char_name:
        await ctx.send("Finish character creation first!"); return
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
            f"⏱ 60 seconds to respond."
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
    await c_channel.send("═══════════════  ⚔ DUEL BEGINS  ═══════════════")
    c_msg = await c_channel.send(embed=duel_card(
        duel.c_name, duel.c_class, duel.c_gif, duel.c_hp, duel.c_hp_max,
        duel.c_poison, duel.c_regen, 0x1a3a8a, True))
    o_msg = await c_channel.send(embed=duel_card(
        duel.o_name, duel.o_class, duel.o_gif, duel.o_hp, duel.o_hp_max,
        duel.o_poison, duel.o_regen, 0x8b0000, False))
    await pin_msg(c_msg); await pin_msg(o_msg)
    duel.pinned_c = c_msg; duel.pinned_o = o_msg
    await c_channel.send(
        f"💰 Winner **+{GIL_WIN_DUEL} gil** | Loser **-{GIL_LOSE_DUEL} gil**\n"
        f"{duel.challenger.mention} goes first — pick your move:",
        view=DuelMoveView(duel)
    )
    await ctx.send(f"✅ Duel accepted! Head to {c_channel.mention} to fight!")

@bot.command(name="dueldecline")
async def duel_decline(ctx: commands.Context, challenger: discord.Member):
    data = pending_duels.get(challenger.id)
    if data and data["opponent"].id == ctx.author.id:
        del pending_duels[challenger.id]
        await data["channel"].send(f"❌ {ctx.author.display_name} declined the duel challenge.")
        await ctx.send("❌ Duel declined.")

# ─────────────────────────────────────────────
#  !gil
# ─────────────────────────────────────────────
@bot.command(name="gil")
async def show_gil(ctx: commands.Context):
    if not _is_game_channel(ctx): return
    s    = active_sessions.get(ctx.channel.id)
    name = s.char_name if s and s.char_name else ctx.author.display_name
    bal  = await db_get_gil(ctx.author.id)
    em   = discord.Embed(title="💰 Gil Balance", description=f"**{name}** has **{bal} gil**", color=0xf0d060)
    em.set_footer(text=f"PvE win: +{GIL_WIN_PVE} gil  |  Hard win: +{GIL_WIN_PVE*2} gil  |  Duel win: +{GIL_WIN_DUEL} gil  |  Duel loss: -{GIL_LOSE_DUEL} gil")
    await ctx.send(embed=em)

# ─────────────────────────────────────────────
#  !ffreset
# ─────────────────────────────────────────────
@bot.command(name="ffreset")
async def ffreset(ctx: commands.Context):
    if not _is_game_channel(ctx): return
    if ctx.author.id not in player_channels or player_channels[ctx.author.id] != ctx.channel.id:
        await ctx.send("You can only reset from your own FF Arena channel."); return
    cid = ctx.channel.id
    if cid in active_duels:
        duel = active_duels[cid]
        try: await ctx.channel.set_permissions(duel.opponent, overwrite=None)
        except Exception: pass
        del active_duels[cid]
    if ctx.author.id in pending_duels:
        del pending_duels[ctx.author.id]
    if cid in active_sessions:
        del active_sessions[cid]
    em = discord.Embed(title="🔄 Character Reset",
        description=f"{ctx.author.mention} has been reset!\n\n💰 Gil and hard mode unlocks are **preserved**.\nChoose a new class to start fresh.",
        color=0x2a55c0)
    await ctx.send(embed=em)
    await send_class_select(ctx.channel)

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

@bot.event
async def on_ready():
    await init_db()
    print(f"✅ {bot.user} is online and ready!")

bot.run(BOT_TOKEN)
