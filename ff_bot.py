import discord, random, asyncio, os, asyncpg
from discord.ext import commands

# ── CONFIG ──────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ASSET_BASE_URL = "https://raw.githubusercontent.com/PigeonHawk/ff-bot/main/"
FF_CATEGORY_ID = 1498963161934467184

# ── DATA ────────────────────────────────────────────────────────────────────
CLASSES = {
    "warrior":   {"name":"Warrior",       "role":"Tank",           "gif":"Warrior.gif",   "hp":200},
    "blackmage": {"name":"Black Mage",    "role":"Mage / DPS",     "gif":"Blackmage.gif", "hp":150},
    "whitemage": {"name":"White Mage",    "role":"Healer",         "gif":"Whitemage.gif", "hp":170},
    "archer":    {"name":"Archer",        "role":"Ranger / DPS",   "gif":"Archer.gif",    "hp":165},
    "thief":     {"name":"Thief",         "role":"Rogue / Support","gif":"Thief.gif",     "hp":160},
    "redmage":   {"name":"Red Mage",      "role":"Hybrid / Mage",  "gif":"Redmage.gif",   "hp":175},
}
ENEMIES = {
    "garland":   {"name":"Garland",           "hp":280,"gif":"unit_201000203_1idle_opac.gif",
                  "sig":{"name":"Chaos Slicer","dmg":(18,28)},"slash_dmg":(6,14),
                  "hard":{"hp":450,"slash_dmg":(10,20),"sig_dmg":(28,42)}},
    "sephiroth": {"name":"Sephiroth",         "hp":320,"gif":"unit_335000305_1idle_opac.gif",
                  "sig":{"name":"Octoslash","dmg":(22,35)},"slash_dmg":(7,15),
                  "hard":{"hp":500,"slash_dmg":(12,22),"sig_dmg":(34,52)}},
    "cod":       {"name":"Cloud of Darkness", "hp":350,"gif":"unit_203000803_1idle_opac.gif",
                  "sig":{"name":"Aura Ball","dmg":(20,32)},"slash_dmg":(6,13),
                  "hard":{"hp":540,"slash_dmg":(11,21),"sig_dmg":(30,48)}},
}
MOVES = {
    "slash":   {"cost":1,"type":"atk",   "dmg":(4,10)},
    "axeswing":{"cost":3,"type":"atk",   "dmg":(16,26),"class":"warrior"},
    "poison":  {"cost":3,"type":"status","effect":"poison"},
    "regen":   {"cost":3,"type":"status","effect":"regen"},
    "cure":    {"cost":4,"type":"heal",  "heal":(12,20)},
    "fire":    {"cost":5,"type":"atk",   "dmg":(14,22)},
    "ice":     {"cost":5,"type":"atk",   "dmg":(14,22)},
    "thunder": {"cost":5,"type":"atk",   "dmg":(14,22)},
}
ENEMY_MOVES = {
    "slash":  {"cost":1,"type":"atk"},
    "poison": {"cost":3,"type":"status","effect":"poison"},
    "regen":  {"cost":3,"type":"status","effect":"regen"},
    "fire":   {"cost":5,"type":"atk","dmg":(10,16)},
    "ice":    {"cost":5,"type":"atk","dmg":(10,16)},
    "thunder":{"cost":5,"type":"atk","dmg":(10,16)},
}
LIMIT_BREAKS = {
    "warrior": {"name":"Shield Wall",       "cost":3,"type":"defense","desc":"Reduces damage by 25% for 5 turns."},
    "redmage": {"name":"Vermilion Scourge", "cost":3,"type":"blind",  "desc":"Blinds enemy — miss rate +40% for 5 turns."},
    "default": {"name":"Limit Break",       "cost":3,"type":"atk_boost","desc":"Next attack deals 3× damage."},
}
WIN_MSGS  = ["The crystal glows in your honor!","A legend is born this day.","Victory is yours!","Your name shall be sung across the realm!"]
LOSE_MSGS = ["You absolute dog shit. Get back up and try again.","Dog shit performance. Run it back.","Dog shit. Try harder.","You got cooked. Dog shit. Run it back."]
GIL_WIN_PVE=10; GIL_WIN_DUEL=20; GIL_LOSE_DUEL=10; GIL_START=200
MISS_CHANCE=0.15; CRIT_CHANCE=0.15; LB_MAX=75

# ── DATABASE ─────────────────────────────────────────────────────────────────
db_pool = None
async def init_db():
    global db_pool
    url = os.environ.get("DATABASE_URL")
    if not url: print("WARNING: No DATABASE_URL"); return
    db_pool = await asyncpg.create_pool(url)
    async with db_pool.acquire() as c:
        await c.execute("""CREATE TABLE IF NOT EXISTS players(user_id BIGINT PRIMARY KEY,gil INTEGER NOT NULL DEFAULT 200,hard_unlocked TEXT NOT NULL DEFAULT '')""")
        await c.execute("""CREATE TABLE IF NOT EXISTS save_slots(user_id BIGINT NOT NULL,slot INTEGER NOT NULL CHECK(slot BETWEEN 1 AND 3),class_key TEXT,char_name TEXT,zodiac TEXT,game TEXT NOT NULL DEFAULT 'ff',PRIMARY KEY(user_id,slot,game))""")
    # Migrate existing table — add game column if missing
    async with db_pool.acquire() as c:
        await c.execute("ALTER TABLE save_slots ADD COLUMN IF NOT EXISTS game TEXT NOT NULL DEFAULT 'ff'")
    print("Database ready.")

async def db_ensure(uid):
    if not db_pool: return
    async with db_pool.acquire() as c:
        await c.execute("INSERT INTO players(user_id,gil) VALUES($1,$2) ON CONFLICT DO NOTHING",uid,GIL_START)

async def db_get_gil(uid):
    if not db_pool: return GIL_START
    async with db_pool.acquire() as c:
        r = await c.fetchrow("SELECT gil FROM players WHERE user_id=$1",uid)
        return r["gil"] if r else GIL_START

async def db_add_gil(uid,amt):
    if not db_pool: return
    await db_ensure(uid)
    async with db_pool.acquire() as c:
        await c.execute("UPDATE players SET gil=GREATEST(0,gil+$1) WHERE user_id=$2",amt,uid)

async def db_get_hard(uid):
    if not db_pool: return set()
    async with db_pool.acquire() as c:
        r = await c.fetchrow("SELECT hard_unlocked FROM players WHERE user_id=$1",uid)
        return set(r["hard_unlocked"].split(",")) if r and r["hard_unlocked"] else set()

async def db_unlock_hard(uid,key):
    u = await db_get_hard(uid); u.add(key)
    async with db_pool.acquire() as c:
        await c.execute("UPDATE players SET hard_unlocked=$1 WHERE user_id=$2",",".join(u),uid)

async def db_get_saves(uid,game="ff"):
    saves={1:None,2:None,3:None}
    if not db_pool: return saves
    async with db_pool.acquire() as c:
        rows = await c.fetch("SELECT * FROM save_slots WHERE user_id=$1 AND game=$2",uid,game)
    for r in rows: saves[r["slot"]]=dict(r)
    return saves

async def db_save_char(uid,slot,class_key,char_name,zodiac="",game="ff"):
    if not db_pool: return
    async with db_pool.acquire() as c:
        await c.execute("INSERT INTO save_slots(user_id,slot,class_key,char_name,zodiac,game) VALUES($1,$2,$3,$4,$5,$6) ON CONFLICT(user_id,slot,game) DO UPDATE SET class_key=$3,char_name=$4,zodiac=$5",uid,slot,class_key,char_name,zodiac,game)

async def db_del_save(uid,slot,game="ff"):
    if not db_pool: return
    async with db_pool.acquire() as c:
        await c.execute("DELETE FROM save_slots WHERE user_id=$1 AND slot=$2 AND game=$3",uid,slot,game)

# ── HELPERS ──────────────────────────────────────────────────────────────────
def hp_bar(cur,mx,n=16): f=round((cur/mx)*n); return "█"*f+"░"*(n-f)
def rand(*r): return random.randint(*r)
def clamp(v,lo,hi): return max(lo,min(hi,v))

def calc_hit(dmg,halved=False):
    r=random.random()
    if r<MISS_CHANCE: return 0,"miss"
    d=dmg*2 if r>=(1-CRIT_CHANCE) else dmg
    if halved: d=d//2
    return d,"crit" if r>=(1-CRIT_CHANCE) else "normal"

def hit_line(move,atk,def_,outcome,dmg):
    if outcome=="miss":  return f"💨 **{atk}** uses **{move}** — **MISSED** {def_}!"
    if outcome=="crit":  return f"💥 **CRITICAL!** **{atk}** lands **{move}** on {def_} for **{dmg}** damage!"
    return f"⚔ **{atk}** uses **{move}** on {def_} for **{dmg}** damage!"

async def pin_msg(msg):
    try: await msg.pin()
    except: pass

async def edit_pin(msg,embed):
    try: await msg.edit(embed=embed)
    except: pass

async def send_temp(ch,content,delay=4.0):
    try: msg=await ch.send(content); await asyncio.sleep(delay); await msg.delete()
    except: pass

async def bulk_delete(ch,msgs):
    """Delete a list of messages, using bulk delete where possible."""
    if not msgs: return
    try:
        valid=[m for m in msgs if m is not None]
        if len(valid)>=2:
            await ch.delete_messages(valid)
        else:
            for m in valid:
                try: await m.delete()
                except: pass
    except Exception:
        for m in msgs:
            try: await m.delete()
            except: pass

def slot_card(slot,row):
    if row:
        cls=CLASSES.get(row.get("class_key",""),{})
        em=discord.Embed(title=f"📁 Slot {slot} — {row.get('char_name','?')}",color=0x2a55c0)
        em.set_thumbnail(url=ASSET_BASE_URL+cls.get("gif",""))
        em.add_field(name="Class",value=cls.get("name","?"),inline=True)
    else:
        em=discord.Embed(title=f"📁 Slot {slot} — Empty",description="Start a new adventure",color=0x2a2a4a)
    return em

# ── CARD BUILDERS ────────────────────────────────────────────────────────────
def pve_player_card(s,title=""):
    parts=[f"☠ Poison({s.p_poison})" if s.p_poison else None,
           f"♻ Regen({s.p_regen})" if s.p_regen else None,
           "🛡 Defending" if s.p_defend else None,
           f"📦 Stored +{s.stored}pt" if s.stored else None]
    status="\n".join(p for p in parts if p) or "—"
    pts=f"\n\n🎲 **{s.pts_left}pt** remaining" if s.pts_left else ""
    q=f"\n📋 **{' → '.join(k.capitalize() for k in s.queue)}**" if s.queue else ""
    lb_pct=min(s.lb_meter/LB_MAX,1.0); lb_f=round(lb_pct*12)
    lb_bar="█"*lb_f+"░"*(12-lb_f)
    if s.lb_ready:   lb=f"\n⚡ **LIMIT BREAK READY!** `{lb_bar}`"
    else:            lb=f"\n⚡ Limit `{lb_bar}` {s.lb_meter}/{LB_MAX}"
    if s.lb_active:
        ck=next((k for k,v in CLASSES.items() if v is s.chosen_class),"")
        lb+=f"\n🔥 **{LIMIT_BREAKS.get(ck,LIMIT_BREAKS['default'])['name']}** active ({s.lb_turns}t)"
    em=discord.Embed(title=title or f"⚔ {s.char_name}",color=0x1a3a8a)
    em.set_author(name=f"{s.char_name}  ·  {s.chosen_class['name']}  ·  {s.chosen_class['role']}")
    em.set_image(url=ASSET_BASE_URL+s.chosen_class["gif"])
    em.add_field(name="HP",value=f"`{hp_bar(s.p_hp,s.p_hp_max)}`\n**{s.p_hp}/{s.p_hp_max}**",inline=True)
    em.add_field(name="Status",value=status+pts+q+lb,inline=True)
    return em

def pve_enemy_card(s,title=""):
    e=s.enemy
    parts=[f"☠ Poison({s.e_poison})" if s.e_poison else None,f"♻ Regen({s.e_regen})" if s.e_regen else None]
    status="\n".join(p for p in parts if p) or "—"
    warn="\n\n⚠️ **Signature move ready!**" if s.e_hp>0 and s.e_hp/s.e_hp_max<0.3 else ""
    em=discord.Embed(title=title or f"👹 {e['name']}",color=0x8b0000)
    em.set_author(name=f"{e['name']}  ·  Sig: {e['sig']['name']}")
    em.set_image(url=ASSET_BASE_URL+e["gif"])
    em.add_field(name="HP",value=f"`{hp_bar(s.e_hp,s.e_hp_max)}`\n**{s.e_hp}/{s.e_hp_max}**",inline=True)
    em.add_field(name="Status",value=status+warn,inline=True)
    em.set_footer(text="Signature activates below 30% HP")
    return em

def duel_card(name,cls_name,gif,hp,hp_max,poison,regen,color,is_turn):
    parts=[f"☠ Poison({poison})" if poison else None,f"♻ Regen({regen})" if regen else None]
    status="\n".join(p for p in parts if p) or "—"
    turn=" 🟢 YOUR TURN" if is_turn else ""
    em=discord.Embed(color=color)
    em.set_author(name=f"{name}  ·  {cls_name}{turn}")
    em.set_image(url=ASSET_BASE_URL+gif)
    em.add_field(name="HP",value=f"`{hp_bar(hp,hp_max)}`\n**{hp}/{hp_max}**",inline=True)
    em.add_field(name="Status",value=status,inline=True)
    return em

# ── SESSIONS ─────────────────────────────────────────────────────────────────
class GameSession:
    def __init__(self,player,chosen_class,char_name,zodiac=""):
        self.player=player; self.chosen_class=chosen_class; self.char_name=char_name; self.zodiac=zodiac
        self.p_hp_max=chosen_class["hp"]; self.p_hp=self.p_hp_max
        self.p_poison=self.p_regen=self.stored=self.pts_left=self.pts_total=0
        self.p_defend=False; self.enemy=None; self.e_hp_max=self.e_hp=0; self.e_poison=self.e_regen=0
        self.hard_mode=False; self.unlocked_hard=set(); self.queue=[]; self.phase="select_enemy"
        self.pinned_player=self.pinned_enemy=None
        self.lb_meter=self.lb_turns=self.e_blind_turns=self.p_shield_pct=self.p_shield_turns=0
        self.lb_ready=self.lb_used=self.lb_active=self.lb_boost_next=self.e_blinded=False

    def reset_for_battle(self,ekey,hard=False):
        e=ENEMIES[ekey]; self.enemy=e; self.hard_mode=hard
        self.e_hp_max=e["hard"]["hp"] if hard else e["hp"]; self.e_hp=self.e_hp_max
        self.p_hp_max=self.chosen_class["hp"]+(50 if hard else 0); self.p_hp=self.p_hp_max
        self.e_poison=self.e_regen=self.p_poison=self.p_regen=self.stored=0
        self.p_defend=False; self.queue=[]; self.phase="battle"
        self.lb_meter=self.lb_turns=self.e_blind_turns=self.p_shield_pct=self.p_shield_turns=0
        self.lb_ready=self.lb_used=self.lb_active=self.lb_boost_next=self.e_blinded=False
        self.pinned_player=self.pinned_enemy=None

    async def refresh_pins(self,pt="",et=""):
        if self.pinned_player: await edit_pin(self.pinned_player,pve_player_card(self,pt))
        if self.pinned_enemy:  await edit_pin(self.pinned_enemy, pve_enemy_card(self,et))

class DuelSession:
    def __init__(self,challenger,opponent,cs,os_,channel):
        self.challenger=challenger; self.opponent=opponent; self.channel=channel
        self.c_hp_max=400; self.c_hp=400; self.c_poison=self.c_regen=0
        self.c_name=cs.char_name; self.c_class=cs.chosen_class["name"]; self.c_gif=cs.chosen_class["gif"]
        self.o_hp_max=400; self.o_hp=400; self.o_poison=self.o_regen=0
        self.o_name=os_.char_name; self.o_class=os_.chosen_class["name"]; self.o_gif=os_.chosen_class["gif"]
        self.turn="challenger"; self.active=True; self.pinned_c=self.pinned_o=None

    def current_player(self): return self.challenger if self.turn=="challenger" else self.opponent
    def swap_turn(self): self.turn="opponent" if self.turn=="challenger" else "challenger"

    async def refresh_pins(self):
        if self.pinned_c: await edit_pin(self.pinned_c,duel_card(self.c_name,self.c_class,self.c_gif,self.c_hp,self.c_hp_max,self.c_poison,self.c_regen,0x1a3a8a,self.turn=="challenger"))
        if self.pinned_o: await edit_pin(self.pinned_o,duel_card(self.o_name,self.o_class,self.o_gif,self.o_hp,self.o_hp_max,self.o_poison,self.o_regen,0x8b0000,self.turn=="opponent"))

    def apply_move(self,mk,attacker):
        m=DUEL_MOVES[mk]; atk=self.c_name if attacker=="challenger" else self.o_name; def_=self.o_name if attacker=="challenger" else self.c_name
        if m["type"]=="atk":
            dmg=rand(*m["dmg"])
            if attacker=="challenger": self.o_hp=clamp(self.o_hp-dmg,0,self.o_hp_max)
            else: self.c_hp=clamp(self.c_hp-dmg,0,self.c_hp_max)
            return f"⚔ **{atk}** uses **{mk.capitalize()}** on {def_} for **{dmg}** damage!"
        if m["type"]=="heal":
            h=rand(*m["heal"])
            if attacker=="challenger": self.c_hp=clamp(self.c_hp+h,0,self.c_hp_max)
            else: self.o_hp=clamp(self.o_hp+h,0,self.o_hp_max)
            return f"💚 **{atk}** uses **Cure** and restores **{h}** HP!"
        if m["type"]=="status":
            if m["effect"]=="poison":
                if attacker=="challenger": self.o_poison=3
                else: self.c_poison=3
                return f"☠ **{atk}** poisons {def_} for 3 turns!"
            if attacker=="challenger": self.c_regen=3
            else: self.o_regen=3
            return f"♻ **{atk}** gains Regen for 3 turns!"
        return ""

    def tick(self):
        lines=[]
        for who in ("challenger","opponent"):
            name=self.c_name if who=="challenger" else self.o_name
            if who=="challenger":
                if self.c_poison>0: self.c_hp=max(0,self.c_hp-3); self.c_poison-=1; lines.append(f"☠ {name} takes **3** poison damage!")
                if self.c_regen>0: h=rand(5,10); self.c_hp=min(self.c_hp_max,self.c_hp+h); self.c_regen-=1; lines.append(f"♻ {name} regenerates **{h}** HP!")
            else:
                if self.o_poison>0: self.o_hp=max(0,self.o_hp-3); self.o_poison-=1; lines.append(f"☠ {name} takes **3** poison damage!")
                if self.o_regen>0: h=rand(5,10); self.o_hp=min(self.o_hp_max,self.o_hp+h); self.o_regen-=1; lines.append(f"♻ {name} regenerates **{h}** HP!")
        return lines

    def is_over(self):
        if self.c_hp<=0: return "opponent"
        if self.o_hp<=0: return "challenger"
        return None

DUEL_MOVES={
    "slash":  {"type":"atk",   "dmg":(6,14)},
    "poison": {"type":"status","effect":"poison"},
    "regen":  {"type":"status","effect":"regen"},
    "cure":   {"type":"heal",  "heal":(15,25)},
    "fire":   {"type":"atk",   "dmg":(16,24)},
    "ice":    {"type":"atk",   "dmg":(16,24)},
    "thunder":{"type":"atk",   "dmg":(16,24)},
}

# ── ENEMY TURN ───────────────────────────────────────────────────────────────
async def run_enemy_turn(ch,s):
    tick=[]
    if s.p_poison>0: s.p_hp=max(0,s.p_hp-3); s.p_poison-=1; tick.append("☠ Poison deals **3** damage!")
    if s.p_regen>0: h=rand(5,10); s.p_hp=min(s.p_hp_max,s.p_hp+h); s.p_regen-=1; tick.append(f"♻ Regen restores **{h}** HP!")
    if tick: await send_temp(ch,"\n".join(tick))
    if s.p_hp<=0: await s.refresh_pins("💀 Defeated","👹 Wins!"); await end_pve(ch,s,False); return
    e=s.enemy; eroll=rand(1,6); epts=eroll
    faces=["⚀","⚁","⚂","⚃","⚄","⚅"]; lines=[f"👹 **{e['name']}** rolls {faces[eroll-1]} (**{eroll}pt**)"]
    blind_extra=0.40 if s.e_blinded else 0.0

    def eatk(raw,halved):
        r=random.random()
        if r<(MISS_CHANCE+blind_extra): return 0,"miss"
        if s.hard_mode and r>=(1-CRIT_CHANCE): d=raw*2; return (d//2 if halved else d),"crit"
        return (raw//2 if halved else raw),"normal"

    def shield(d): return max(1,int(d*(1-s.p_shield_pct/100))) if s.p_shield_turns>0 and d>0 else d

    def deal_player(dmg):
        if dmg>0:
            s.p_hp=max(0,s.p_hp-dmg); s.lb_meter=min(LB_MAX,s.lb_meter+dmg)
            if s.lb_meter>=LB_MAX: s.lb_ready=True

    if s.e_hp/s.e_hp_max<0.3:
        sr=e["hard"]["sig_dmg"] if s.hard_mode else e["sig"]["dmg"]
        raw=int(rand(*sr)*0.85); dmg,out=eatk(raw,s.p_defend); dmg=shield(dmg); deal_player(dmg)
        ht=f" *(halved)*" if s.p_defend and dmg>0 else ""
        if out=="miss": lines.append(f"💨 **{e['name']}** uses **{e['sig']['name']}** — MISSED!")
        elif out=="crit": lines.append(f"💥 **CRITICAL!** **{e['name']}** uses **{e['sig']['name']}** for **{dmg}** damage!{ht}")
        else: lines.append(f"💥 **{e['name']}** uses **{e['sig']['name']}** for **{dmg}** damage!{ht}")
        epts=max(0,epts-6)

    actions=[]; att=0
    while epts>0 and att<20:
        att+=1; affordable=[(k,m) for k,m in ENEMY_MOVES.items() if m["cost"]<=epts]
        if not affordable: break
        mk,m=random.choice(affordable)
        if m["type"]=="atk":
            sr=e["hard"]["slash_dmg"] if (s.hard_mode and mk=="slash") else e["slash_dmg"] if mk=="slash" else m.get("dmg",e["slash_dmg"])
            raw=int(rand(*sr)*0.85); dmg,out=eatk(raw,s.p_defend); dmg=shield(dmg); deal_player(dmg)
            tag=" 💥CRIT" if out=="crit" else (" 💨MISS" if out=="miss" else "")
            actions.append(f"**{mk.capitalize()}**{tag} ({dmg} dmg)")
        elif m["type"]=="status":
            if m["effect"]=="poison" and s.p_poison==0: s.p_poison=3; actions.append("**Poison**")
            elif m["effect"]=="regen" and s.e_regen==0: s.e_regen=3; actions.append("**Regen**")
            else:
                sr=e["hard"]["slash_dmg"] if s.hard_mode else e["slash_dmg"]
                raw=int(rand(*sr)*0.85); dmg,out=eatk(raw,s.p_defend); dmg=shield(dmg); deal_player(dmg)
                tag=" 💥CRIT" if out=="crit" else (" 💨MISS" if out=="miss" else "")
                actions.append(f"**Slash**{tag} ({dmg} dmg)")
        epts-=m["cost"]
    if actions: lines.append(f"👹 {e['name']} uses: "+", ".join(actions))
    if s.e_poison>0: s.e_hp=max(0,s.e_hp-3); s.e_poison-=1; lines.append(f"☠ {e['name']} takes **3** poison damage!")
    if s.e_regen>0: h=rand(5,10); s.e_hp=min(s.e_hp_max,s.e_hp+h); s.e_regen-=1; lines.append(f"♻ {e['name']} regenerates **{h}** HP!")
    if s.e_blinded: s.e_blind_turns-=1
    if s.e_blind_turns==0 and s.e_blinded: s.e_blinded=False; lines.append("👁 Blind has worn off!")
    if s.p_shield_turns>0: s.p_shield_turns-=1
    if s.p_shield_turns==0 and s.p_shield_pct: s.p_shield_pct=0; lines.append("🛡 Shield Wall expired!")
    if s.lb_active and s.lb_turns>0: s.lb_turns-=1
    if s.lb_active and s.lb_turns==0: s.lb_active=False; lines.append("⚡ Limit Break effect worn off!")
    s.p_defend=False
    await send_temp(ch,"\n".join(lines),delay=5.0)
    await s.refresh_pins()
    if s.p_hp<=0: await s.refresh_pins("💀 Defeated","👹 Wins!"); await end_pve(ch,s,False); return
    if s.e_hp<=0: await s.refresh_pins("🏆 Victory!","💀 Defeated"); await end_pve(ch,s,True); return
    await ch.send("⚔ Your turn — what will you do?",view=RollAgainView(s))

async def end_pve(ch,s,won):
    uid=s.player.id
    if won:
        gb=GIL_WIN_PVE*2 if s.hard_mode else GIL_WIN_PVE; await db_add_gil(uid,gb)
        hm=""
        if not s.hard_mode:
            ek=next(k for k,v in ENEMIES.items() if v is s.enemy)
            uh=await db_get_hard(uid)
            if ek not in uh: await db_unlock_hard(uid,ek); uh.add(ek); hm=f"\n\n🔴 **HARD MODE UNLOCKED:** {s.enemy['name']}!"
            s.unlocked_hard=uh
        mt=" *(Hard)*" if s.hard_mode else ""; nb=await db_get_gil(uid)
        em=discord.Embed(title="🏆 VICTORY!",description=f"**{s.char_name}!**{mt}\n\n{random.choice(WIN_MSGS)}\n\n💰 +{gb} gil! Balance: **{nb} gil**{hm}",color=0x50e090)
    else:
        lb=await db_get_gil(uid)
        em=discord.Embed(title="💀 DEFEATED",description=f"**{random.choice(LOSE_MSGS)}**\n\n💰 Balance: **{lb} gil**",color=0xe05050)
    s.phase="select_enemy"; s.pinned_player=s.pinned_enemy=None
    s.unlocked_hard=await db_get_hard(uid)
    await ch.send(embed=em,view=FightMenuView(s))

async def end_duel(ch,duel,winner_side):
    duel.active=False
    w=duel.challenger if winner_side=="challenger" else duel.opponent
    l=duel.opponent   if winner_side=="challenger" else duel.challenger
    wn=duel.c_name    if winner_side=="challenger" else duel.o_name
    ln=duel.o_name    if winner_side=="challenger" else duel.c_name
    await db_add_gil(w.id,GIL_WIN_DUEL); await db_add_gil(l.id,-GIL_LOSE_DUEL)
    wb=await db_get_gil(w.id); lb=await db_get_gil(l.id)
    em=discord.Embed(title="🏆 DUEL OVER!",description=f"**{wn}** defeats **{ln}**!\n\n💰 {w.mention} +{GIL_WIN_DUEL} → **{wb} gil**\n💸 {l.mention} -{GIL_LOSE_DUEL} → **{lb} gil**",color=0xf0d060)
    await ch.send(embed=em)
    try: await duel.channel.set_permissions(duel.opponent,overwrite=None)
    except: pass
    if ch.id in active_duels: del active_duels[ch.id]

# ── TIMEOUT HELPER ────────────────────────────────────────────────────────────
async def battle_timeout(s):
    try:
        ch=s.pinned_player.channel if s.pinned_player else None
        if not ch: return
        s.phase="select_enemy"; s.enemy=s.pinned_player=s.pinned_enemy=None; s.queue=[]
        s.unlocked_hard=await db_get_hard(s.player.id)
        em=discord.Embed(title="⏱ Battle Timed Out",description=f"{s.player.mention} took too long! Battle stopped.\nType `!fight` to try again.",color=0xe05050)
        await ch.send(embed=em,view=FightMenuView(s))
    except: pass

# ── VIEWS ────────────────────────────────────────────────────────────────────
class FightMenuView(discord.ui.View):
    def __init__(self,s):
        super().__init__(timeout=300); self.session=s
        for key,e in ENEMIES.items():
            b=discord.ui.Button(label=f"⚔ {e['name']}",style=discord.ButtonStyle.danger,custom_id=f"f_{key}"); b.callback=self._cb(key,False); self.add_item(b)
            if key in s.unlocked_hard:
                b2=discord.ui.Button(label=f"🔴 {e['name']} (Hard)",style=discord.ButtonStyle.danger,custom_id=f"fh_{key}"); b2.callback=self._cb(key,True); self.add_item(b2)
    def _cb(self,key,hard):
        async def cb(i):
            s=self.session
            if i.user.id!=s.player.id: await i.response.send_message("Not your battle!",ephemeral=True); return
            await i.response.defer(); self.stop()
            s.reset_for_battle(key,hard=hard); mode="  🔴 HARD MODE" if hard else ""
            banner=await i.followup.send(f"═══════  ⚔ BATTLE START{mode}  ═══════")
            ch=i.channel
            pm=await ch.send(embed=pve_player_card(s)); em_=await ch.send(embed=pve_enemy_card(s))
            await pin_msg(pm); await pin_msg(em_); s.pinned_player=pm; s.pinned_enemy=em_
            await asyncio.sleep(3); await banner.delete()
            await ch.send("⚔ Your turn — what will you do?",view=RollView(s))
        return cb

class RollView(discord.ui.View):
    def __init__(self,s): super().__init__(timeout=120); self.session=s
    async def on_timeout(self): await battle_timeout(self.session)

    @discord.ui.button(label="🎲 Roll Dice",style=discord.ButtonStyle.primary,row=0)
    async def roll(self,i,b):
        s=self.session
        if i.user.id!=s.player.id: await i.response.send_message("Not your battle!",ephemeral=True); return
        await i.response.defer(); base=rand(1,6); total=base+s.stored; s.stored=0; s.pts_left=s.pts_total=total
        faces=["⚀","⚁","⚂","⚃","⚄","⚅"]; note=f" (+{total-base} stored)={total}" if total>base else ""
        self.stop(); msg=await i.followup.send(f"{faces[base-1]} Rolled **{base}**{note}! **{s.pts_left}pt** to spend.")
        await s.refresh_pins(); await asyncio.sleep(3); await msg.delete()
        await i.channel.send("🎯 Pick your moves:",view=MoveView(s))

    @discord.ui.button(label="📊 Status",style=discord.ButtonStyle.secondary,row=0)
    async def status(self,i,b):
        s=self.session
        if i.user.id!=s.player.id: await i.response.send_message("Not your battle!",ephemeral=True); return
        await i.response.send_message(embeds=[pve_player_card(s),pve_enemy_card(s)],ephemeral=True)

    @discord.ui.button(label="🛑 Stop Battle",style=discord.ButtonStyle.danger,row=1)
    async def stop(self,i,b):
        s=self.session
        if i.user.id!=s.player.id: await i.response.send_message("Not your battle!",ephemeral=True); return
        await i.response.defer(); self.stop()
        s.phase="select_enemy"; s.enemy=s.pinned_player=s.pinned_enemy=None; s.queue=[]
        s.unlocked_hard=await db_get_hard(i.user.id)
        em=discord.Embed(title="⚔ Battle Stopped",description="Choose your next opponent.",color=0x2a55c0)
        await i.followup.send(embed=em,view=FightMenuView(s))

class RollAgainView(discord.ui.View):
    def __init__(self,s): super().__init__(timeout=120); self.session=s
    async def on_timeout(self): await battle_timeout(self.session)

    @discord.ui.button(label="🎲 Roll Again",style=discord.ButtonStyle.primary,row=0)
    async def roll(self,i,b):
        s=self.session
        if i.user.id!=s.player.id: await i.response.send_message("Not your battle!",ephemeral=True); return
        await i.response.defer(); base=rand(1,6); total=base+s.stored; s.stored=0; s.pts_left=s.pts_total=total
        faces=["⚀","⚁","⚂","⚃","⚄","⚅"]; note=f" (+{total-base} stored)={total}" if total>base else ""
        self.stop(); msg=await i.followup.send(f"{faces[base-1]} Rolled **{base}**{note}! **{s.pts_left}pt** to spend.")
        await s.refresh_pins(); await asyncio.sleep(3); await msg.delete()
        await i.channel.send("🎯 Pick your moves:",view=MoveView(s))

    @discord.ui.button(label="📊 Status",style=discord.ButtonStyle.secondary,row=0)
    async def status(self,i,b):
        s=self.session
        if i.user.id!=s.player.id: await i.response.send_message("Not your battle!",ephemeral=True); return
        await i.response.send_message(embeds=[pve_player_card(s),pve_enemy_card(s)],ephemeral=True)

    @discord.ui.button(label="🛑 Stop Battle",style=discord.ButtonStyle.danger,row=1)
    async def stop(self,i,b):
        s=self.session
        if i.user.id!=s.player.id: await i.response.send_message("Not your battle!",ephemeral=True); return
        await i.response.defer(); self.stop()
        s.phase="select_enemy"; s.enemy=s.pinned_player=s.pinned_enemy=None; s.queue=[]
        s.unlocked_hard=await db_get_hard(i.user.id)
        em=discord.Embed(title="⚔ Battle Stopped",description="Choose your next opponent.",color=0x2a55c0)
        await i.followup.send(embed=em,view=FightMenuView(s))

class MoveView(discord.ui.View):
    MOVE_DEFS=[("⚔ Slash (1pt)","slash",discord.ButtonStyle.secondary,1),
               ("☠ Poison (3pt)","poison",discord.ButtonStyle.secondary,3),
               ("♻ Regen (3pt)","regen",discord.ButtonStyle.success,3),
               ("💚 Cure (4pt)","cure",discord.ButtonStyle.success,4),
               ("🔥 Fire (5pt)","fire",discord.ButtonStyle.danger,5),
               ("❄ Ice (5pt)","ice",discord.ButtonStyle.danger,5),
               ("⚡ Thunder (5pt)","thunder",discord.ButtonStyle.danger,5)]
    WARRIOR=("🪓 Axe Swing (3pt)","axeswing",discord.ButtonStyle.secondary,3)

    def __init__(self,s): super().__init__(timeout=120); self.session=s; self._build()
    async def on_timeout(self): await battle_timeout(self.session)

    def _build(self):
        self.clear_items(); s=self.session
        ck=next((k for k,v in CLASSES.items() if v is s.chosen_class),"")
        defs=list(self.MOVE_DEFS)
        if ck=="warrior": defs.insert(1,self.WARRIOR)
        for i,(label,key,style,cost) in enumerate(defs):
            row=0 if i<4 else 1
            b=discord.ui.Button(label=label,style=style,disabled=s.pts_left<cost,custom_id=f"mv_{key}",row=row)
            b.callback=self._move_cb(key,cost); self.add_item(b)
        # Execute
        eb=discord.ui.Button(label=f"✅ Execute ({len(s.queue)} queued)" if s.queue else "✅ Execute",
            style=discord.ButtonStyle.primary,disabled=not s.queue,custom_id="mv_exec",row=2)
        eb.callback=self._exec; self.add_item(eb)
        # Defend
        db=discord.ui.Button(label="🛡 Defend (store roll + halve damage)",style=discord.ButtonStyle.secondary,custom_id="mv_def",row=2)
        db.callback=self._defend; self.add_item(db)
        # Status
        sb=discord.ui.Button(label="📊 Status",style=discord.ButtonStyle.secondary,custom_id="mv_stat",row=2)
        sb.callback=self._status; self.add_item(sb)
        # Limit Break
        if s.lb_ready and not s.lb_used:
            lb_def=LIMIT_BREAKS.get(ck,LIMIT_BREAKS["default"])
            lb=discord.ui.Button(label=f"⚡ LIMIT BREAK — {lb_def['name']} (3pt)",style=discord.ButtonStyle.danger,disabled=s.pts_left<3,custom_id="mv_lb",row=3)
            lb.callback=self._lb; self.add_item(lb)

    def _move_cb(self,key,cost):
        async def cb(i):
            s=self.session
            if i.user.id!=s.player.id: await i.response.send_message("Not your battle!",ephemeral=True); return
            if s.pts_left<cost: await i.response.send_message("Not enough points!",ephemeral=True); return
            await i.response.defer(); s.pts_left-=cost; s.queue.append(key)
            await s.refresh_pins(); self._build()
            await i.edit_original_response(content=f"✅ **{key.capitalize()}** queued [{' → '.join(k.capitalize() for k in s.queue)}] — **{s.pts_left}pt** left",view=self)
        return cb

    async def _defend(self,i,b):
        s=self.session
        if i.user.id!=s.player.id: await i.response.send_message("Not your battle!",ephemeral=True); return
        await i.response.defer(); s.queue=[]; base=rand(1,6); s.stored+=base; s.p_defend=True
        faces=["⚀","⚁","⚂","⚃","⚄","⚅"]; self.stop()
        msg=await i.followup.send(f"🛡 {faces[base-1]} **Defend!** Rolled **{base}** stored. Damage halved.\n📦 Stored: **{s.stored}pt**")
        await s.refresh_pins(); await asyncio.sleep(4); await msg.delete()
        await run_enemy_turn(i.channel,s)

    async def _status(self,i,b):
        s=self.session
        if i.user.id!=s.player.id: await i.response.send_message("Not your battle!",ephemeral=True); return
        await i.response.send_message(embeds=[pve_player_card(s),pve_enemy_card(s)],ephemeral=True)

    async def _lb(self,i,b):
        s=self.session
        if i.user.id!=s.player.id: await i.response.send_message("Not your battle!",ephemeral=True); return
        if s.pts_left<3: await i.response.send_message("Not enough points!",ephemeral=True); return
        await i.response.defer(); s.pts_left-=3; s.lb_ready=False; s.lb_used=True; s.lb_meter=0
        ck=next((k for k,v in CLASSES.items() if v is s.chosen_class),"")
        lb_def=LIMIT_BREAKS.get(ck,LIMIT_BREAKS["default"]); self.stop()
        if lb_def["type"]=="defense": s.lb_active=True; s.lb_turns=5; s.p_shield_pct=25; s.p_shield_turns=5; msg=f"⚡ **{lb_def['name']}!** Damage reduced 25% for 5 turns!"
        elif lb_def["type"]=="blind": s.lb_active=True; s.lb_turns=5; s.e_blinded=True; s.e_blind_turns=5; msg=f"⚡ **{lb_def['name']}!** Enemy blinded — miss rate +40% for 5 turns!"
        else: s.lb_boost_next=True; msg=f"⚡ **{lb_def['name']}!** Next attack deals 3× damage!"
        r=await i.followup.send(msg); await s.refresh_pins(); await asyncio.sleep(4); await r.delete()
        if s.pts_left>0: await i.channel.send(f"🎯 **{s.pts_left}pt** remaining:",view=MoveView(s))
        else: await run_enemy_turn(i.channel,s)

    async def _exec(self,i,b):
        s=self.session
        if i.user.id!=s.player.id: await i.response.send_message("Not your battle!",ephemeral=True); return
        if not s.queue: await i.response.send_message("Nothing queued!",ephemeral=True); return
        await i.response.defer(); self.stop(); lines=[]
        for mk in s.queue:
            m=MOVES[mk]
            if m["type"]=="atk":
                raw=rand(*m["dmg"]); dmg,out=(calc_hit(raw) if s.hard_mode else (raw,"normal"))
                if s.lb_boost_next and dmg>0: dmg*=3; s.lb_boost_next=False; lines.append("💥 **LIMIT BREAK BOOST!**")
                if dmg>0: s.e_hp=max(0,s.e_hp-dmg)
                lines.append(hit_line("Axe Swing" if mk=="axeswing" else mk.capitalize(),s.char_name,s.enemy["name"],out,dmg))
            elif m["type"]=="heal": h=rand(*m["heal"]); s.p_hp=min(s.p_hp_max,s.p_hp+h); lines.append(f"💚 **Cure** restores **{h}** HP!")
            elif m["type"]=="status":
                if m["effect"]=="poison": s.e_poison=3; lines.append(f"☠ **Poison** on {s.enemy['name']}!")
                else: s.p_regen=3; lines.append("♻ **Regen** granted!")
        s.queue=[]
        msg=await i.followup.send("\n".join(lines)); await s.refresh_pins(); await asyncio.sleep(4); await msg.delete()
        if s.e_hp<=0: await s.refresh_pins("🏆 Victory!","💀 Defeated"); await end_pve(i.channel,s,True); return
        await run_enemy_turn(i.channel,s)

class DuelMoveView(discord.ui.View):
    DEFS=[("⚔ Slash","slash",discord.ButtonStyle.secondary),("☠ Poison","poison",discord.ButtonStyle.secondary),
          ("♻ Regen","regen",discord.ButtonStyle.success),("💚 Cure","cure",discord.ButtonStyle.success),
          ("🔥 Fire","fire",discord.ButtonStyle.danger),("❄ Ice","ice",discord.ButtonStyle.danger),
          ("⚡ Thunder","thunder",discord.ButtonStyle.danger)]
    def __init__(self,duel):
        super().__init__(timeout=120); self.duel=duel
        for label,key,style in self.DEFS:
            b=discord.ui.Button(label=label,style=style,custom_id=f"dm_{key}"); b.callback=self._cb(key); self.add_item(b)
    async def on_timeout(self):
        try: d=self.duel; d.active=False; await d.channel.send("⏱ Duel timed out!"); del active_duels[d.channel.id]
        except: pass
    def _cb(self,mk):
        async def cb(i):
            d=self.duel
            if not d.active: await i.response.send_message("Duel is over!",ephemeral=True); return
            if i.user.id!=d.current_player().id: await i.response.send_message(f"Not your turn! Waiting for **{d.current_player().display_name}**.",ephemeral=True); return
            await i.response.defer(); att="challenger" if i.user.id==d.challenger.id else "opponent"
            log=d.apply_move(mk,att); self.stop()
            msg=await i.followup.send(log); await asyncio.sleep(3); await msg.delete(); await d.refresh_pins()
            ws=d.is_over()
            if ws: await end_duel(i.channel,d,ws); return
            if d.turn=="opponent":
                tick=d.tick()
                if tick:
                    tm=await i.channel.send("\n".join(tick)); await d.refresh_pins(); await asyncio.sleep(3); await tm.delete()
                else: await d.refresh_pins()
                ws=d.is_over()
                if ws: await end_duel(i.channel,d,ws); return
            d.swap_turn(); await d.refresh_pins()
            await i.channel.send(f"{d.current_player().mention} — your turn!",view=DuelMoveView(d))
        return cb

# ── SAVE SLOT VIEWS ───────────────────────────────────────────────────────────
class SaveSlotView(discord.ui.View):
    def __init__(self,uid,saves,channel,guild):
        super().__init__(timeout=120); self.uid=uid; self.saves=saves; self.channel=channel; self.guild=guild
        for slot in(1,2,3):
            row=saves[slot]
            if row: cls=CLASSES.get(row["class_key"],{}); label=f"▶ Slot {slot} — {row['char_name']} ({cls.get('name','?')})"; style=discord.ButtonStyle.primary
            else: label=f"✦ Slot {slot} — Empty"; style=discord.ButtonStyle.secondary
            b=discord.ui.Button(label=label,style=style,custom_id=f"ss_{slot}"); b.callback=self._cb(slot,row); self.add_item(b)
    def _cb(self,slot,row):
        async def cb(i):
            if i.user.id!=self.uid: await i.response.send_message("Not your save!",ephemeral=True); return
            await i.response.defer(); self.stop()
            if row:
                cls=CLASSES.get(row["class_key"],{}); bal=await db_get_gil(self.uid)
                em=discord.Embed(title=f"📁 Slot {slot} — {row['char_name']}",color=0x2a55c0)
                em.set_thumbnail(url=ASSET_BASE_URL+cls.get("gif",""))
                em.add_field(name="Class",value=cls.get("name","?"),inline=True)
                em.add_field(name="Gil",value=f"💰 {bal}",inline=True)
                await i.followup.send(embed=em,view=ContinueOrNewView(self.uid,slot,row,self.channel))
            else:
                _pending_slots[self.channel.id]=slot
                await i.followup.send(f"📁 Slot {slot} — New character! Choose your class:")
                await send_class_select(self.channel,slot)
        return cb

class ContinueOrNewView(discord.ui.View):
    def __init__(self,uid,slot,row,channel):
        super().__init__(timeout=120); self.uid=uid; self.slot=slot; self.row=row; self.channel=channel
    @discord.ui.button(label="▶ Continue",style=discord.ButtonStyle.success,row=0)
    async def cont(self,i,b):
        if i.user.id!=self.uid: await i.response.send_message("Not your save!",ephemeral=True); return
        await i.response.defer(); self.stop()
        cls=CLASSES.get(self.row["class_key"])
        if not cls: await i.followup.send("Invalid save — start new.",ephemeral=True); return
        s=GameSession(i.user,cls,self.row["char_name"])
        s.unlocked_hard=await db_get_hard(self.uid); s._save_slot=self.slot
        active_sessions[self.channel.id]=s
        bal=await db_get_gil(self.uid)
        em=discord.Embed(title="✨ Welcome back!",color=0xf0d060)
        em.set_image(url=ASSET_BASE_URL+cls["gif"])
        em.add_field(name="Name",value=self.row["char_name"],inline=True)
        em.add_field(name="Class",value=cls["name"],inline=True)
        em.add_field(name="Gil",value=f"💰 {bal}",inline=True)
        await i.followup.send(embed=em)
    @discord.ui.button(label="🔄 New Game (overwrites)",style=discord.ButtonStyle.danger,row=0)
    async def new(self,i,b):
        if i.user.id!=self.uid: await i.response.send_message("Not your save!",ephemeral=True); return
        await i.response.defer(); self.stop()
        await i.followup.send(f"⚠️ Delete **{self.row['char_name']}** in Slot {self.slot}? Are you sure?",view=ConfirmOverwriteView(self.uid,self.slot,self.channel))
    @discord.ui.button(label="← Back",style=discord.ButtonStyle.secondary,row=1)
    async def back(self,i,b):
        if i.user.id!=self.uid: await i.response.send_message("Not your save!",ephemeral=True); return
        await i.response.defer(); self.stop()
        saves=await db_get_saves(self.uid)
        hdr=discord.Embed(title="📁 Select Save Slot",color=0x2a55c0)
        await i.followup.send(embeds=[hdr]+[slot_card(s,saves[s]) for s in(1,2,3)],view=SaveSlotView(self.uid,saves,self.channel,i.guild))

class ConfirmOverwriteView(discord.ui.View):
    def __init__(self,uid,slot,channel):
        super().__init__(timeout=60); self.uid=uid; self.slot=slot; self.channel=channel
    @discord.ui.button(label="✅ Yes, delete",style=discord.ButtonStyle.danger)
    async def yes(self,i,b):
        if i.user.id!=self.uid: await i.response.send_message("Not your save!",ephemeral=True); return
        await i.response.defer(); self.stop()
        await db_del_save(self.uid,self.slot)
        await i.followup.send(f"🗑 Slot {self.slot} cleared!")
        await send_class_select(self.channel,self.slot)
    @discord.ui.button(label="✗ Cancel",style=discord.ButtonStyle.secondary)
    async def no(self,i,b):
        if i.user.id!=self.uid: await i.response.send_message("Not your save!",ephemeral=True); return
        await i.response.defer(); self.stop()
        saves=await db_get_saves(self.uid)
        hdr=discord.Embed(title="📁 Select Save Slot",color=0x2a55c0)
        await i.followup.send(embeds=[hdr]+[slot_card(s,saves[s]) for s in(1,2,3)],view=SaveSlotView(self.uid,saves,self.channel,i.guild))

class TitleScreenView(discord.ui.View):
    def __init__(self,uid,saves,channel,guild):
        super().__init__(timeout=300); self.uid=uid; self.saves=saves; self.channel=channel; self.guild=guild
        for slot in(1,2,3):
            row=saves[slot]
            if row: cls=CLASSES.get(row["class_key"],{}); label=f"▶ Slot {slot} — {row['char_name']} ({cls.get('name','?')})"; style=discord.ButtonStyle.primary
            else: label=f"✦ Slot {slot} — New Game"; style=discord.ButtonStyle.secondary
            b=discord.ui.Button(label=label,style=style,custom_id=f"ts_{slot}"); b.callback=self._cb(slot,row); self.add_item(b)
    def _cb(self,slot,row):
        async def cb(i):
            if i.user.id!=self.uid: await i.response.send_message("Not your save!",ephemeral=True); return
            await i.response.defer(); self.stop()
            cid=self.channel.id
            if row:
                cls=CLASSES.get(row["class_key"])
                s=GameSession(i.user,cls,row["char_name"]); s.unlocked_hard=await db_get_hard(self.uid); s._save_slot=slot
                active_sessions[cid]=s; bal=await db_get_gil(self.uid)
                em=discord.Embed(title=f"▶ Resuming Slot {slot}",color=0xf0d060)
                em.set_image(url=ASSET_BASE_URL+cls["gif"])
                em.add_field(name="Name",value=row["char_name"],inline=True)
                em.add_field(name="Class",value=cls["name"],inline=True)
                em.add_field(name="Gil",value=f"💰 {bal}",inline=True)
                await i.followup.send(embed=em)
            else:
                _pending_slots[cid]=slot
                await i.followup.send(f"📁 Slot {slot} — New character!")
                await send_class_select(self.channel,slot)
        return cb

# ── BOT SETUP ────────────────────────────────────────────────────────────────
intents=discord.Intents.default(); intents.message_content=True; intents.members=True
bot=commands.Bot(command_prefix="!",intents=intents)
active_sessions:dict[int,GameSession]={}; player_channels:dict[int,int]={}
active_duels:dict[int,DuelSession]={}; pending_duels:dict[int,dict]={}
_pending_slots:dict[int,int]={}

# ── COMMANDS ─────────────────────────────────────────────────────────────────
@bot.command(name="FF")
async def start_ff(ctx):
    guild=ctx.guild; category=guild.get_channel(FF_CATEGORY_ID)
    if ctx.author.id in player_channels:
        ch=bot.get_channel(player_channels[ctx.author.id])
        if ch: await ctx.send(f"{ctx.author.mention} You already have an active game: {ch.mention}"); return
    expected=f"ff-{ctx.author.name.lower().replace(' ','-')}"; existing=None
    if category:
        for ch in category.text_channels:
            if ch.name==expected: existing=ch; break
    overwrites={guild.default_role:discord.PermissionOverwrite(view_channel=True,send_messages=False,add_reactions=False),
                ctx.author:discord.PermissionOverwrite(view_channel=True,send_messages=True,add_reactions=True),
                guild.me:discord.PermissionOverwrite(view_channel=True,send_messages=True,manage_channels=True)}
    if existing:
        game_channel=existing; player_channels[ctx.author.id]=game_channel.id
        await ctx.send(f"✨ {ctx.author.mention} Welcome back! {game_channel.mention}")
    else:
        game_channel=await guild.create_text_channel(name=expected,category=category,overwrites=overwrites,topic=f"FF RPG — {ctx.author.display_name}")
        player_channels[ctx.author.id]=game_channel.id
        await ctx.send(f"✨ {ctx.author.mention} Your adventure awaits: {game_channel.mention}")
    await db_ensure(ctx.author.id)
    saves=await db_get_saves(ctx.author.id)
    hdr=discord.Embed(title="📁 Select Save Slot",description="Pick a slot to continue or start fresh.",color=0x2a55c0)
    await game_channel.send(embeds=[hdr]+[slot_card(s,saves[s]) for s in(1,2,3)],view=SaveSlotView(ctx.author.id,saves,game_channel,guild))

async def send_class_select(channel,slot=0):
    if slot: _pending_slots[channel.id]=slot
    em=discord.Embed(title=f"⚔ Choose Your Class{f' (Slot {slot})' if slot else ''}",description="Type `!class <name>` to select.",color=0x2a55c0)
    for key,c in CLASSES.items():
        em.add_field(name=f"`!class {key}` — {c['name']}",value=f"Role: {c['role']} | HP: {c['hp']}",inline=False)
    await channel.send(embed=em)

@bot.command(name="class")
async def choose_class(ctx,class_key:str):
    if not _is_gc(ctx): return
    class_key=class_key.lower()
    if class_key not in CLASSES: await ctx.send(f"Choose from: {', '.join(CLASSES.keys())}"); return
    chosen=CLASSES[class_key]; s=GameSession(ctx.author,chosen,"")
    slot=_pending_slots.pop(ctx.channel.id,0)
    if slot: s._pending_slot=slot
    elif ctx.channel.id in active_sessions: slot=getattr(active_sessions[ctx.channel.id],"_pending_slot",0); s._pending_slot=slot
    active_sessions[ctx.channel.id]=s
    em=discord.Embed(title=f"🌟 Class: {chosen['name']}",description=f"Role: **{chosen['role']}** | HP: **{chosen['hp']}**",color=0x2a55c0)
    em.set_image(url=ASSET_BASE_URL+chosen["gif"])
    em.add_field(name="Next",value="Enter your name: `!name YourName`",inline=False)
    await ctx.send(embed=em)

@bot.command(name="name")
async def set_name(ctx,*,char_name:str):
    if not _is_gc(ctx) or ctx.channel.id not in active_sessions: return
    if len(char_name)>12: await ctx.send("Max 12 characters."); return
    s=active_sessions[ctx.channel.id]; s.char_name=char_name
    slot=getattr(s,"_pending_slot",0)
    if slot:
        ck=next((k for k,v in CLASSES.items() if v is s.chosen_class),"")
        await db_save_char(ctx.author.id,slot,ck,char_name); s._save_slot=slot
    s.unlocked_hard=await db_get_hard(ctx.author.id); bal=await db_get_gil(ctx.author.id)
    em=discord.Embed(title="✨ Character Created!",color=0xf0d060)
    em.set_image(url=ASSET_BASE_URL+s.chosen_class["gif"])
    em.add_field(name="Name",value=s.char_name,inline=True)
    em.add_field(name="Class",value=s.chosen_class["name"],inline=True)
    em.add_field(name="Gil",value=f"💰 {bal} gil",inline=True)
    if slot: em.add_field(name="Save Slot",value=f"📁 Slot {slot}",inline=True)
    em.set_footer(text="!fight to battle  |  !ffduel @user  |  !gil  |  !ffreset")
    await ctx.send(embed=em)

@bot.command(name="fight")
async def fight(ctx):
    if not _is_gc(ctx) or ctx.channel.id not in active_sessions: return
    s=active_sessions[ctx.channel.id]; s.unlocked_hard=await db_get_hard(ctx.author.id)
    em=discord.Embed(title="👹 Choose Your Opponent",description="Click an enemy!",color=0x2a55c0)
    await ctx.send(embed=em,view=FightMenuView(s))

@bot.command(name="ffduel")
async def ffduel(ctx,opponent:discord.Member):
    if not _is_gc(ctx): await ctx.send("Use in your FF channel!"); return
    if opponent.id==ctx.author.id: await ctx.send("Can't duel yourself!"); return
    cs=active_sessions.get(ctx.channel.id)
    if not cs or not cs.char_name: await ctx.send("Finish character creation first!"); return
    och=player_channels.get(opponent.id)
    if not och: await ctx.send(f"{opponent.display_name} hasn't started FF Arena!"); return
    os_=active_sessions.get(och)
    if not os_ or not os_.char_name: await ctx.send(f"{opponent.display_name} hasn't finished character creation!"); return
    if ctx.channel.id in active_duels: await ctx.send("Already an active duel here!"); return
    if ctx.author.id in pending_duels: await ctx.send("Already have a pending challenge!"); return
    pending_duels[ctx.author.id]={"opponent":opponent,"challenger":ctx.author,"c_session":cs,"o_session":os_,"channel":ctx.channel}
    em=discord.Embed(title="⚔ Duel Challenge!",description=f"{opponent.mention} — **{cs.char_name}** [{cs.chosen_class['name']}] challenges you!\n\n`!duelaccept {ctx.author.mention}` to accept\n`!dueldecline {ctx.author.mention}` to decline\n\n⏱ 30 seconds.",color=0x8b0000)
    em.set_footer(text=f"💰 Winner +{GIL_WIN_DUEL} | Loser -{GIL_LOSE_DUEL}")
    await ctx.send(embed=em)
    await asyncio.sleep(30)
    if ctx.author.id in pending_duels: del pending_duels[ctx.author.id]; await ctx.send(f"⏱ Challenge to {opponent.mention} expired.")

@bot.command(name="duelaccept")
async def duel_accept(ctx,challenger:discord.Member):
    if not _is_gc(ctx): return
    data=pending_duels.get(challenger.id)
    if not data or data["opponent"].id!=ctx.author.id: await ctx.send("No pending challenge from that player."); return
    del pending_duels[challenger.id]; cc=data["channel"]
    await cc.set_permissions(ctx.author,send_messages=True,view_channel=True)
    duel=DuelSession(data["challenger"],ctx.author,data["c_session"],data["o_session"],cc)
    active_duels[cc.id]=duel
    await cc.send("═══════════════  ⚔ DUEL BEGINS  ═══════════════")
    cm=await cc.send(embed=duel_card(duel.c_name,duel.c_class,duel.c_gif,duel.c_hp,duel.c_hp_max,duel.c_poison,duel.c_regen,0x1a3a8a,True))
    om=await cc.send(embed=duel_card(duel.o_name,duel.o_class,duel.o_gif,duel.o_hp,duel.o_hp_max,duel.o_poison,duel.o_regen,0x8b0000,False))
    await pin_msg(cm); await pin_msg(om); duel.pinned_c=cm; duel.pinned_o=om
    await cc.send(f"💰 Winner +{GIL_WIN_DUEL} | Loser -{GIL_LOSE_DUEL}\n{duel.challenger.mention} goes first:",view=DuelMoveView(duel))
    await ctx.send(f"✅ Duel accepted! {cc.mention}")

@bot.command(name="dueldecline")
async def duel_decline(ctx,challenger:discord.Member):
    data=pending_duels.get(challenger.id)
    if data and data["opponent"].id==ctx.author.id:
        del pending_duels[challenger.id]; await data["channel"].send(f"❌ {ctx.author.display_name} declined."); await ctx.send("❌ Declined.")

@bot.command(name="gil")
async def show_gil(ctx):
    if not _is_gc(ctx): return
    s=active_sessions.get(ctx.channel.id); name=s.char_name if s and s.char_name else ctx.author.display_name
    bal=await db_get_gil(ctx.author.id)
    em=discord.Embed(title="💰 Gil Balance",description=f"**{name}** has **{bal} gil**",color=0xf0d060)
    em.set_footer(text=f"PvE: +{GIL_WIN_PVE} | Hard: +{GIL_WIN_PVE*2} | Duel win: +{GIL_WIN_DUEL} | Duel loss: -{GIL_LOSE_DUEL}")
    await ctx.send(embed=em)

@bot.command(name="ffreset")
async def ffreset(ctx):
    if not _is_gc(ctx): return
    if ctx.author.id not in player_channels or player_channels[ctx.author.id]!=ctx.channel.id: await ctx.send("Use in your own FF channel."); return
    cid=ctx.channel.id
    if cid in active_duels:
        try: await ctx.channel.set_permissions(active_duels[cid].opponent,overwrite=None)
        except: pass
        del active_duels[cid]
    pending_duels.pop(ctx.author.id,None); active_sessions.pop(cid,None)
    em=discord.Embed(title="🔄 Reset",description=f"{ctx.author.mention} reset!\n💰 Gil and hard mode unlocks preserved.",color=0x2a55c0)
    await ctx.send(embed=em)
    saves=await db_get_saves(ctx.author.id)
    hdr=discord.Embed(title="📁 Select Save Slot",color=0x2a55c0)
    await ctx.send(embeds=[hdr]+[slot_card(s,saves[s]) for s in(1,2,3)],view=SaveSlotView(ctx.author.id,saves,ctx.channel,ctx.guild))

@bot.command(name="ffslot")
async def ffslot(ctx):
    if not _is_gc(ctx): return
    if ctx.author.id not in player_channels or player_channels[ctx.author.id]!=ctx.channel.id: await ctx.send("Use in your own FF channel."); return
    cid=ctx.channel.id
    if cid in active_duels:
        try: await ctx.channel.set_permissions(active_duels[cid].opponent,overwrite=None)
        except: pass
        del active_duels[cid]
    pending_duels.pop(ctx.author.id,None); active_sessions.pop(cid,None)
    saves=await db_get_saves(ctx.author.id)
    hdr=discord.Embed(title="📁 Switch Save Slot",color=0x2a55c0)
    await ctx.send(embeds=[hdr]+[slot_card(s,saves[s]) for s in(1,2,3)],view=SaveSlotView(ctx.author.id,saves,ctx.channel,ctx.guild))

@bot.command(name="titlescreen")
async def titlescreen(ctx):
    if not _is_gc(ctx): return
    if ctx.author.id not in player_channels or player_channels[ctx.author.id]!=ctx.channel.id: await ctx.send("Use in your own FF channel."); return
    cid=ctx.channel.id
    if cid in active_duels:
        try: await ctx.channel.set_permissions(active_duels[cid].opponent,overwrite=None)
        except: pass
        del active_duels[cid]
    pending_duels.pop(ctx.author.id,None)
    if cid in active_sessions: active_sessions[cid].phase="paused"; active_sessions[cid].queue=[]; active_sessions[cid].pinned_player=active_sessions[cid].pinned_enemy=None
    saves=await db_get_saves(ctx.author.id); bal=await db_get_gil(ctx.author.id)
    hdr=discord.Embed(title="🎮 Title Screen",description=f"💰 Gil: **{bal}**\n\nYour progress is saved. Pick a slot.",color=0x1a3a8a)
    hdr.set_footer(text="Select a slot below")
    await ctx.send(embeds=[hdr]+[slot_card(s,saves[s]) for s in(1,2,3)],view=TitleScreenView(ctx.author.id,saves,ctx.channel,ctx.guild))

@bot.command(name="endgame")
async def endgame(ctx):
    if not _is_gc(ctx): return
    await ctx.send("👋 Channel closes in 10 seconds.")
    await asyncio.sleep(10)
    cid=ctx.channel.id
    for uid,ch in list(player_channels.items()):
        if ch==cid: del player_channels[uid]; break
    active_sessions.pop(cid,None); active_duels.pop(cid,None)
    await ctx.channel.delete()

def _is_gc(ctx): return ctx.channel.id in active_sessions or ctx.channel.id in player_channels.values()

# ═══════════════════════════════════════════════════════════════════════════════
#  ICE WIND & FIRE MINI-GAME
# ═══════════════════════════════════════════════════════════════════════════════
IWF_MAX_HP=10; IWF_ROUNDS=10
ELEMENTS={"ice":{"label":"🧊 Ice","emoji":"🧊","beats":"wind"},"wind":{"label":"🌪 Wind","emoji":"🌪","beats":"fire"},"fire":{"label":"🔥 Fire","emoji":"🔥","beats":"ice"}}
IWF_CLASSES={"crystalwarrior":{"name":"Crystal Warrior","role":"Fighter","gif":"Warrior.gif"},"stormcaller":{"name":"Storm Caller","role":"Mage","gif":"Redmage.gif"},"emberblade":{"name":"Ember Blade","role":"Duelist","gif":"Archer.gif"}}
IWF_ENEMIES={"sephiroth":{"name":"Sephiroth","gif":"unit_335000305_1idle_opac.gif","element":"wind","desc":"The One-Winged Angel."},"cod":{"name":"Cloud of Darkness","gif":"unit_203000803_1idle_opac.gif","element":"ice","desc":"An entity of void."},"garland":{"name":"Garland","gif":"unit_201000203_1idle_opac.gif","element":"fire","desc":"The knight of chaos."}}
IWF_WIN=["The elements bow to your mastery!","Victory! Your instincts are unmatched.","Flawless!","You bend the elements!"]
IWF_LOSE=["The elements overwhelm you!","Defeated!","The balance tips against you...","Your element was consumed!"]
REVEAL={("ice","wind"):"🧊 Ice freezes the wind!",("wind","fire"):"🌪 Wind smothers the flames!",("fire","ice"):"🔥 Fire melts the ice!",("wind","ice"):"🧊 Ice blocks the gale!",("fire","wind"):"🌪 Wind extinguishes fire!",("ice","fire"):"🔥 Fire melts through ice!",("ice","ice"):"🧊 Ice meets Ice!",("wind","wind"):"🌪 Wind meets Wind!",("fire","fire"):"🔥 Fire meets Fire!"}

def iwf_resolve(a,b):
    if a==b: return "tie"
    return "a" if ELEMENTS[a]["beats"]==b else "b"

def iwf_hp_bar(cur,n=10): f=round((cur/IWF_MAX_HP)*n); return "█"*f+"░"*(n-f)

def iwf_battle_em(pn,pc,pg,php,en,ec,eg,ehp,rnd,title="Ice Wind & Fire",footer=""):
    em=discord.Embed(title=title,color=0x1a3a8a)
    em.set_thumbnail(url=ASSET_BASE_URL+pg); em.set_image(url=ASSET_BASE_URL+eg)
    em.add_field(name=f"⚔ {pn} [{pc}]",value=f"`{iwf_hp_bar(php)}` **{php}/{IWF_MAX_HP}**",inline=True)
    em.add_field(name=f"👹 {en} [{ec}]",value=f"`{iwf_hp_bar(ehp)}` **{ehp}/{IWF_MAX_HP}**",inline=True)
    em.add_field(name="Round",value=f"**{rnd}**/{IWF_ROUNDS}",inline=False)
    if footer: em.set_footer(text=footer)
    return em

def iwf_duel_em(cn,cg,chp,on,og,ohp,rnd,cp,op,title="IWF Duel"):
    em=discord.Embed(title=title,color=0x8b0000)
    em.set_thumbnail(url=ASSET_BASE_URL+cg); em.set_image(url=ASSET_BASE_URL+og)
    em.add_field(name=cn,value=f"`{iwf_hp_bar(chp)}` **{chp}/{IWF_MAX_HP}**\n{'✅ Picked' if cp else '⏳ Waiting...'}",inline=True)
    em.add_field(name=on,value=f"`{iwf_hp_bar(ohp)}` **{ohp}/{IWF_MAX_HP}**\n{'✅ Picked' if op else '⏳ Waiting...'}",inline=True)
    em.add_field(name="Round",value=f"**{rnd}**/{IWF_ROUNDS}",inline=False)
    em.set_footer(text="Both players pick simultaneously!")
    return em

class IWFSession:
    def __init__(self,player,char_name,char_class,enemy_key):
        self.player=player; self.char_name=char_name; self.char_class=char_class
        self.enemy_key=enemy_key; self.enemy=IWF_ENEMIES[enemy_key]
        self.p_hp=IWF_MAX_HP; self.e_hp=IWF_MAX_HP; self.round=1; self.pinned=None
        self.battle_msgs=[]   # track all messages sent during battle for cleanup
    async def refresh(self,title="Ice Wind & Fire"):
        if self.pinned:
            try: await self.pinned.edit(embed=iwf_battle_em(self.char_name,self.char_class["name"],self.char_class["gif"],self.p_hp,self.enemy["name"],self.enemy["element"].capitalize(),self.enemy["gif"],self.e_hp,self.round,title=title))
            except: pass

class IWFDuelSession:
    def __init__(self,challenger,opponent,cn,cc,on_,oc,channel):
        self.challenger=challenger; self.opponent=opponent; self.channel=channel
        self.c_name=cn; self.c_class=cc; self.o_name=on_; self.o_class=oc
        self.c_hp=IWF_MAX_HP; self.o_hp=IWF_MAX_HP; self.round=1
        self.c_pick=self.o_pick=None; self.active=True; self.pinned=None
    async def refresh(self,title="IWF Duel"):
        if self.pinned:
            try: await self.pinned.edit(embed=iwf_duel_em(self.c_name,self.c_class["gif"],self.c_hp,self.o_name,self.o_class["gif"],self.o_hp,self.round,self.c_pick is not None,self.o_pick is not None,title=title))
            except: pass

async def iwf_end_pve(ch,s,sk,iwf_sessions):
    if s.p_hp<=0: title="Defeated!"; desc=random.choice(IWF_LOSE); color=0xe05050
    elif s.e_hp<=0: title="Victory!"; desc=random.choice(IWF_WIN); color=0x50e090
    else: title="Draw!"; desc="10 rounds — no winner!"; color=0xf0d060
    await s.refresh(title)
    result_msg=await ch.send(embed=discord.Embed(title=title,description=desc,color=color))
    await asyncio.sleep(3)
    # Bulk delete all battle messages (pinned card + all round prompts/reveals)
    to_delete=[m for m in s.battle_msgs if m is not None]
    to_delete.append(result_msg)
    await bulk_delete(ch,to_delete)
    # Unpin the battle card
    try: await s.pinned.unpin()
    except: pass
    em2=discord.Embed(title="Choose Next Opponent",color=0x2a55c0)
    for k,e in IWF_ENEMIES.items(): em2.add_field(name=e["name"],value=e["desc"],inline=False)
    await ch.send(embed=em2,view=IWFEnemyView(sk,iwf_sessions,ch))

async def iwf_end_duel(d,iwf_duels):
    d.active=False
    if d.c_hp<=0 and d.o_hp<=0: title="Draw!"; color=0xf0d060; w=l=None
    elif d.c_hp<=0: title=f"{d.o_name} Wins!"; color=0x50e090; w=d.opponent; l=d.challenger
    elif d.o_hp<=0: title=f"{d.c_name} Wins!"; color=0x50e090; w=d.challenger; l=d.opponent
    else: title="Draw!"; color=0xf0d060; w=l=None
    await d.refresh(title)
    em=discord.Embed(title=title,description=random.choice(IWF_WIN) if w else "No winner!",color=color)
    if w and l: em.add_field(name="Result",value=f"{w.mention} defeats {l.mention}!",inline=False)
    await d.channel.send(embed=em)
    try: await d.channel.set_permissions(d.opponent,overwrite=None)
    except: pass
    if d.channel.id in iwf_duels: del iwf_duels[d.channel.id]

class IWFPickView(discord.ui.View):
    def __init__(self,s,sk,iwf_sessions,ch):
        super().__init__(timeout=120); self.s=s; self.sk=sk; self.iwf_sessions=iwf_sessions; self.ch=ch
        for key,el in ELEMENTS.items():
            b=discord.ui.Button(label=el["label"],style=discord.ButtonStyle.primary,custom_id=f"iwfp_{key}"); b.callback=self._cb(key); self.add_item(b)
    async def on_timeout(self):
        try: em=discord.Embed(title="⏱ Timed Out",description=f"{self.s.player.mention} took too long!",color=0xe05050); await self.ch.send(embed=em,view=IWFEnemyView(self.sk,self.iwf_sessions,self.ch))
        except: pass
    def _cb(self,pp):
        async def cb(i):
            s=self.s
            if i.user.id!=s.player.id: await i.response.send_message("Not your game!",ephemeral=True); return
            await i.response.defer(); self.stop()
            ep=s.enemy["element"] if random.random()<0.5 else random.choice(list(ELEMENTS.keys()))
            out=iwf_resolve(pp,ep); flavor=REVEAL.get((pp,ep),"The elements clash!")
            if out=="a": s.e_hp-=1; result=f"**{s.char_name}** wins! {flavor}"
            elif out=="b": s.p_hp-=1; result=f"**{s.enemy['name']}** wins! {flavor}"
            else: result=f"Tie! {flavor}"
            msg=await i.followup.send(f"**Round {s.round}!**\n{s.char_name}: {ELEMENTS[pp]['emoji']} **{pp.capitalize()}**\n{s.enemy['name']}: {ELEMENTS[ep]['emoji']} **{ep.capitalize()}**\n\n{result}")
            s.battle_msgs.append(msg)
            s.round+=1; await s.refresh(); await asyncio.sleep(4); await msg.delete()
            if s.p_hp<=0 or s.e_hp<=0 or s.round>IWF_ROUNDS: await iwf_end_pve(i.channel,s,self.sk,self.iwf_sessions)
            else:
                next_msg=await i.channel.send(f"Round {s.round} — Pick:",view=IWFPickView(s,self.sk,self.iwf_sessions,i.channel))
                s.battle_msgs.append(next_msg)
        return cb

class IWFDuelPickView(discord.ui.View):
    def __init__(self,d,iwf_duels):
        super().__init__(timeout=120); self.d=d; self.iwf_duels=iwf_duels
        for key,el in ELEMENTS.items():
            b=discord.ui.Button(label=el["label"],style=discord.ButtonStyle.primary,custom_id=f"iwfd_{key}"); b.callback=self._cb(key); self.add_item(b)
    async def on_timeout(self):
        try: d=self.d; d.active=False; await d.channel.send("⏱ Duel timed out!"); del self.iwf_duels[d.channel.id]
        except: pass
    def _cb(self,pick):
        async def cb(i):
            d=self.d
            if not d.active: await i.response.send_message("Duel is over!",ephemeral=True); return
            uid=i.user.id
            if uid not in(d.challenger.id,d.opponent.id): await i.response.send_message("Not in this duel!",ephemeral=True); return
            is_c=uid==d.challenger.id
            if is_c and d.c_pick: await i.response.send_message("Already picked!",ephemeral=True); return
            if not is_c and d.o_pick: await i.response.send_message("Already picked!",ephemeral=True); return
            await i.response.send_message(f"You picked {ELEMENTS[pick]['emoji']} **{pick.capitalize()}** — waiting...",ephemeral=True)
            if is_c: d.c_pick=pick
            else: d.o_pick=pick
            await d.refresh()
            if d.c_pick and d.o_pick:
                self.stop()
                cp,op=d.c_pick,d.o_pick; d.c_pick=d.o_pick=None
                out=iwf_resolve(cp,op); flavor=REVEAL.get((cp,op),"The elements clash!")
                if out=="a": d.o_hp-=1; result=f"**{d.c_name}** wins! {flavor}"
                elif out=="b": d.c_hp-=1; result=f"**{d.o_name}** wins! {flavor}"
                else: result=f"Tie! {flavor}"
                msg=await d.channel.send(f"**Round {d.round}!**\n{d.c_name}: {ELEMENTS[cp]['emoji']} **{cp.capitalize()}**\n{d.o_name}: {ELEMENTS[op]['emoji']} **{op.capitalize()}**\n\n{result}")
                d.round+=1; await d.refresh(); await asyncio.sleep(4); await msg.delete()
                if d.c_hp<=0 or d.o_hp<=0 or d.round>IWF_ROUNDS: await iwf_end_duel(d,self.iwf_duels)
                else: await d.channel.send(f"Round {d.round} — Both pick:",view=IWFDuelPickView(d,self.iwf_duels))
        return cb

class IWFEnemyView(discord.ui.View):
    def __init__(self,sk,iwf_sessions,ch):
        super().__init__(timeout=120); self.sk=sk; self.iwf_sessions=iwf_sessions; self.ch=ch
        for key,e in IWF_ENEMIES.items():
            b=discord.ui.Button(label=f"Fight {e['name']}",style=discord.ButtonStyle.danger,custom_id=f"iwfe_{key}"); b.callback=self._cb(key,e); self.add_item(b)
    def _cb(self,key,e):
        async def cb(i):
            uid,slot=self.sk
            if i.user.id!=uid: await i.response.send_message("Not your game!",ephemeral=True); return
            await i.response.defer(); self.stop()
            save=self.iwf_sessions.get(self.sk)
            if not save: await i.followup.send("Session expired — type !FFQ",ephemeral=True); return
            cn=save["char_name"] if isinstance(save,dict) else save.char_name
            cc=save["class"] if isinstance(save,dict) else save.char_class
            s=IWFSession(i.user,cn,cc,key); self.iwf_sessions[self.sk]=s
            em=iwf_battle_em(s.char_name,s.char_class["name"],s.char_class["gif"],s.p_hp,e["name"],e["element"].capitalize(),e["gif"],s.e_hp,s.round,title=f"{s.char_name} vs {e['name']}",footer=e["desc"])
            msg=await self.ch.send(embed=em)
            s.battle_msgs.append(msg)
            try: await msg.pin()
            except: pass
            s.pinned=msg
            pick_msg=await self.ch.send(f"Round 1 — Pick your element:",view=IWFPickView(s,self.sk,self.iwf_sessions,self.ch))
            s.battle_msgs.append(pick_msg)
        return cb

class IWFClassView(discord.ui.View):
    def __init__(self,uid,slot,ch,iwf_sessions,iwf_saves):
        super().__init__(timeout=120); self.uid=uid; self.slot=slot; self.ch=ch; self.iwf_sessions=iwf_sessions; self.iwf_saves=iwf_saves
        for key,cls in IWF_CLASSES.items():
            b=discord.ui.Button(label=f"{cls['name']} ({cls['role']})",style=discord.ButtonStyle.primary,custom_id=f"iwfc_{key}"); b.callback=self._cb(key,cls); self.add_item(b)
    def _cb(self,key,cls):
        async def cb(i):
            if i.user.id!=self.uid: await i.response.send_message("Not your game!",ephemeral=True); return
            await i.response.defer(); self.stop()
            em=discord.Embed(title=f"Class: {cls['name']}",color=0x2a55c0); em.set_image(url=ASSET_BASE_URL+cls["gif"])
            await i.followup.send(embed=em)
            self.iwf_saves[(self.uid,self.slot)]={"class_key":key,"char_name":"","class":cls}
            await self.ch.send("Now type your character name: `!ffqname YourName`")
        return cb

class IWFSlotView(discord.ui.View):
    def __init__(self,uid,saves,ch,guild,iwf_sessions,iwf_saves):
        super().__init__(timeout=120); self.uid=uid; self.saves=saves; self.ch=ch; self.guild=guild; self.iwf_sessions=iwf_sessions; self.iwf_saves=iwf_saves
        for slot in(1,2,3):
            row=saves.get(slot)
            if row: cls=IWF_CLASSES.get(row.get("class_key",""),{}); label=f"▶ Slot {slot} — {row.get('char_name','?')} ({cls.get('name','?')})"; style=discord.ButtonStyle.primary
            else: label=f"✦ Slot {slot} — New Game"; style=discord.ButtonStyle.secondary
            b=discord.ui.Button(label=label,style=style,custom_id=f"iwfs_{slot}"); b.callback=self._cb(slot,row); self.add_item(b)
    def _cb(self,slot,row):
        async def cb(i):
            if i.user.id!=self.uid: await i.response.send_message("Not your game!",ephemeral=True); return
            await i.response.defer(); self.stop(); key=(self.uid,slot)
            if row:
                cls=IWF_CLASSES.get(row.get("class_key",""))
                s=IWFSession(i.user,row["char_name"],cls,list(IWF_ENEMIES.keys())[0]); self.iwf_sessions[key]=s
                em=discord.Embed(title=f"Resuming Slot {slot}",color=0xf0d060); em.set_image(url=ASSET_BASE_URL+cls["gif"])
                await i.followup.send(embed=em)
                em2=discord.Embed(title="Choose Opponent",color=0x2a55c0)
                for k,e in IWF_ENEMIES.items(): em2.add_field(name=e["name"],value=e["desc"],inline=False)
                await self.ch.send(embed=em2,view=IWFEnemyView(key,self.iwf_sessions,self.ch))
            else:
                await i.followup.send(f"Slot {slot} — Choose your class:")
                await self.ch.send(embed=discord.Embed(title="Choose Class",color=0x2a55c0),view=IWFClassView(self.uid,slot,self.ch,self.iwf_sessions,self.iwf_saves))
        return cb

class IceWindFire(commands.Cog):
    def __init__(self,bot,player_channels,db_ensure,db_get_saves,db_save):
        self.bot=bot; self.player_channels=player_channels
        self.iwf_sessions={}; self.iwf_duels={}; self.iwf_pending={}; self.iwf_saves={}; self.iwf_channels={}
        self._db_ensure=db_ensure; self._db_get_saves=db_get_saves; self._db_save=db_save

    @commands.command(name="FFQ")
    async def start_iwf(self,ctx,opponent:discord.Member=None):
        if opponent: await self._duel(ctx,opponent); return
        await self._db_ensure(ctx.author.id)
        saves=await self._db_get_saves(ctx.author.id,"iwf")
        em=discord.Embed(title="🧊🌪🔥 Ice Wind & Fire — Select Slot",color=0x1a3a8a)
        slot_ems=[]
        for slot in(1,2,3):
            row=saves.get(slot)
            if row: cls=IWF_CLASSES.get(row.get("class_key",""),{}); se=discord.Embed(title=f"📁 Slot {slot} — {row.get('char_name','?')}",color=0x2a55c0); se.set_thumbnail(url=ASSET_BASE_URL+cls.get("gif","")); se.add_field(name="Class",value=cls.get("name","?"),inline=True)
            else: se=discord.Embed(title=f"📁 Slot {slot} — Empty",color=0x2a2a4a)
            slot_ems.append(se)
        await ctx.send(embeds=[em]+slot_ems,view=IWFSlotView(ctx.author.id,saves,ctx.channel,ctx.guild,self.iwf_sessions,self.iwf_saves))

    @commands.command(name="ffqname")
    async def set_name(self,ctx,*,char_name:str):
        uid=ctx.author.id
        key=next(((u,s) for(u,s),v in self.iwf_saves.items() if u==uid and isinstance(v,dict) and v.get("char_name")==""),None)
        if not key: await ctx.send("No pending character — type !FFQ to start."); return
        if len(char_name)>12: await ctx.send("Max 12 characters."); return
        save=self.iwf_saves[key]; save["char_name"]=char_name
        await self._db_save(uid,key[1],save["class_key"],char_name,game="iwf")
        cls=save["class"]; em=discord.Embed(title=f"{char_name} enters the arena!",color=0xf0d060); em.set_image(url=ASSET_BASE_URL+cls["gif"]); em.add_field(name="Class",value=cls["name"],inline=True)
        self.iwf_sessions[key]=save; await ctx.send(embed=em)
        em2=discord.Embed(title="Choose Opponent",color=0x2a55c0)
        for k,e in IWF_ENEMIES.items(): em2.add_field(name=e["name"],value=e["desc"],inline=False)
        await ctx.send(embed=em2,view=IWFEnemyView(key,self.iwf_sessions,ctx.channel))

    async def _duel(self,ctx,opponent):
        if ctx.author.id==opponent.id: await ctx.send("Can't duel yourself!"); return
        ck=next(((u,s) for(u,s),v in self.iwf_sessions.items() if u==ctx.author.id and isinstance(v,IWFSession)),None)
        ok=next(((u,s) for(u,s),v in self.iwf_sessions.items() if u==opponent.id and isinstance(v,IWFSession)),None)
        if not ck: await ctx.send("You need an IWF character! Type !FFQ first."); return
        if not ok: await ctx.send(f"{opponent.display_name} doesn't have an IWF character!"); return
        cs=self.iwf_sessions[ck]; os_=self.iwf_sessions[ok]
        if ctx.channel.id in self.iwf_duels: await ctx.send("Already an active duel here!"); return
        self.iwf_pending[ctx.author.id]={"challenger":ctx.author,"opponent":opponent,"c_session":cs,"o_session":os_,"channel":ctx.channel}
        em=discord.Embed(title="🧊🌪🔥 IWF Duel Challenge!",description=f"{opponent.mention} — **{cs.char_name}** challenges you!\n\n`!ffqaccept {ctx.author.mention}` to accept\n`!ffqdecline {ctx.author.mention}` to decline\n\n⏱ 30 seconds.",color=0x8b0000)
        await ctx.send(embed=em)
        await asyncio.sleep(30)
        if ctx.author.id in self.iwf_pending: del self.iwf_pending[ctx.author.id]; await ctx.send(f"IWF challenge to {opponent.mention} expired.")

    @commands.command(name="ffqaccept")
    async def accept(self,ctx,challenger:discord.Member):
        data=self.iwf_pending.get(challenger.id)
        if not data or data["opponent"].id!=ctx.author.id: await ctx.send("No pending IWF challenge."); return
        del self.iwf_pending[challenger.id]; cs=data["c_session"]; os_=data["o_session"]; ch=data["channel"]
        try: await ch.set_permissions(ctx.author,send_messages=True,view_channel=True)
        except: pass
        d=IWFDuelSession(data["challenger"],ctx.author,cs.char_name,cs.char_class,os_.char_name,os_.char_class,ch)
        self.iwf_duels[ch.id]=d
        em=iwf_duel_em(d.c_name,d.c_class["gif"],d.c_hp,d.o_name,d.o_class["gif"],d.o_hp,d.round,False,False,title="🧊🌪🔥 IWF DUEL BEGINS!")
        msg=await ch.send(embed=em)
        try: await msg.pin()
        except: pass
        d.pinned=msg; await ch.send(f"Round 1 — Both pick!\n{data['challenger'].mention} and {ctx.author.mention}",view=IWFDuelPickView(d,self.iwf_duels))
        await ctx.send(f"IWF duel accepted! Head to {ch.mention}!")

    @commands.command(name="ffqdecline")
    async def decline(self,ctx,challenger:discord.Member):
        data=self.iwf_pending.get(challenger.id)
        if data and data["opponent"].id==ctx.author.id:
            del self.iwf_pending[challenger.id]; await data["channel"].send(f"{ctx.author.display_name} declined."); await ctx.send("Declined.")

@bot.event
async def on_ready():
    await init_db()
    await bot.add_cog(IceWindFire(bot,player_channels,db_ensure,db_get_saves,db_save_char))
    print(f"✅ {bot.user} is online and ready!")

bot.run(BOT_TOKEN)
