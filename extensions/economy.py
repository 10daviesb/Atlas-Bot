import datetime
import random

import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Economy")

DB_PATH = "atlas.db"
CURRENCY = "🪙"
DAILY_MIN, DAILY_MAX = 100, 200
WORK_MIN, WORK_MAX = 50, 100
WORK_COOLDOWN = 3600    # 1 hour in seconds
DAILY_COOLDOWN = 86400  # 24 hours in seconds

WORK_LINES = [
    "You worked as a delivery driver",
    "You fixed bugs as a freelance developer",
    "You served tables at a local restaurant",
    "You walked the neighbour's dog",
    "You won a street chess tournament",
    "You sold lemonade on a sunny day",
    "You won the pub quiz",
    "You found cash down the back of the sofa",
    "You did some freelance graphic design",
    "You busked in the town centre",
]


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS economy (
                guild_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                balance    INTEGER NOT NULL DEFAULT 0,
                last_daily INTEGER NOT NULL DEFAULT 0,
                last_work  INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.commit()
    logger.info("Economy DB initialized.")


async def _balance(guild_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def _add(guild_id: int, user_id: int, delta: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO economy (guild_id, user_id, balance) VALUES (?, ?, MAX(0, ?))
            ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = MAX(0, balance + ?)
        """, (guild_id, user_id, max(0, delta), delta))
        await db.commit()
        async with db.execute(
            "SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


def _now() -> int:
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


@plugin.command()
@lightbulb.option("member", "Member to check (defaults to you).", type=hikari.Member, default=None)
@lightbulb.command("balance", "Check your coin balance.")
@lightbulb.implements(lightbulb.SlashCommand)
async def balance(ctx: lightbulb.Context) -> None:
    target = ctx.options.member or ctx.member
    bal = await _balance(ctx.guild_id, target.id)
    await ctx.respond(f"{CURRENCY} **{target.display_name}** has **{bal:,}** coins.")


@plugin.command()
@lightbulb.command("daily", "Claim your daily coins (resets every 24 hours).")
@lightbulb.implements(lightbulb.SlashCommand)
async def daily(ctx: lightbulb.Context) -> None:
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT last_daily FROM economy WHERE guild_id = ? AND user_id = ?",
            (ctx.guild_id, ctx.author.id),
        ) as cur:
            row = await cur.fetchone()

    remaining = DAILY_COOLDOWN - (now - (row[0] if row else 0))
    if remaining > 0:
        h, m = divmod(remaining // 60, 60)
        await ctx.respond(f"⏳ Daily already claimed. Next in **{h}h {m}m**.")
        return

    amount = random.randint(DAILY_MIN, DAILY_MAX)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO economy (guild_id, user_id, balance, last_daily) VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = balance + ?, last_daily = ?
        """, (ctx.guild_id, ctx.author.id, amount, now, amount, now))
        await db.commit()
    await ctx.respond(f"{CURRENCY} Daily claimed! You received **{amount}** coins.")


@plugin.command()
@lightbulb.command("work", "Work for coins (1 hour cooldown).")
@lightbulb.implements(lightbulb.SlashCommand)
async def work(ctx: lightbulb.Context) -> None:
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT last_work FROM economy WHERE guild_id = ? AND user_id = ?",
            (ctx.guild_id, ctx.author.id),
        ) as cur:
            row = await cur.fetchone()

    remaining = WORK_COOLDOWN - (now - (row[0] if row else 0))
    if remaining > 0:
        m = remaining // 60
        await ctx.respond(f"⏳ Still tired from last shift. Try again in **{m}m**.")
        return

    amount = random.randint(WORK_MIN, WORK_MAX)
    job = random.choice(WORK_LINES)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO economy (guild_id, user_id, balance, last_work) VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = balance + ?, last_work = ?
        """, (ctx.guild_id, ctx.author.id, amount, now, amount, now))
        await db.commit()
    await ctx.respond(f"💼 {job} and earned **{amount}** coins {CURRENCY}")


@plugin.command()
@lightbulb.option("amount", "Amount to bet.", type=int)
@lightbulb.command("gamble", "Bet your coins — 45% chance to double up.")
@lightbulb.implements(lightbulb.SlashCommand)
async def gamble(ctx: lightbulb.Context) -> None:
    amount = ctx.options.amount
    if amount <= 0:
        await ctx.respond("❌ Bet must be greater than 0.")
        return
    bal = await _balance(ctx.guild_id, ctx.author.id)
    if amount > bal:
        await ctx.respond(f"❌ You only have **{bal:,}** coins.")
        return
    if random.random() < 0.45:
        new = await _add(ctx.guild_id, ctx.author.id, amount)
        await ctx.respond(f"🎰 You won! **+{amount}** coins. Balance: **{new:,}** {CURRENCY}")
    else:
        new = await _add(ctx.guild_id, ctx.author.id, -amount)
        await ctx.respond(f"🎰 You lost **{amount}** coins. Balance: **{new:,}** {CURRENCY}")


@plugin.command()
@lightbulb.option("amount", "Amount to send.", type=int)
@lightbulb.option("member", "Who to pay.", type=hikari.Member)
@lightbulb.command("pay", "Send coins to another user.")
@lightbulb.implements(lightbulb.SlashCommand)
async def pay(ctx: lightbulb.Context) -> None:
    target: hikari.Member = ctx.options.member
    amount = ctx.options.amount
    if target.id == ctx.author.id:
        await ctx.respond("❌ You can't pay yourself.")
        return
    if amount <= 0:
        await ctx.respond("❌ Amount must be greater than 0.")
        return
    bal = await _balance(ctx.guild_id, ctx.author.id)
    if amount > bal:
        await ctx.respond(f"❌ You only have **{bal:,}** coins.")
        return
    await _add(ctx.guild_id, ctx.author.id, -amount)
    await _add(ctx.guild_id, target.id, amount)
    await ctx.respond(f"{CURRENCY} Sent **{amount:,}** coins to {target.mention}. Your balance: **{bal - amount:,}**.")


@plugin.command()
@lightbulb.command("richest", "Show the richest users in this server.")
@lightbulb.implements(lightbulb.SlashCommand)
async def richest(ctx: lightbulb.Context) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, balance FROM economy WHERE guild_id = ? ORDER BY balance DESC LIMIT 10",
            (ctx.guild_id,),
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await ctx.respond("Nobody has any coins yet — use `/daily` to get started!")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = [f"**{CURRENCY} Richest Members**"]
    for i, (user_id, bal) in enumerate(rows):
        prefix = medals[i] if i < 3 else f"`#{i + 1}`"
        lines.append(f"{prefix} <@{user_id}> — **{bal:,}** coins")
    await ctx.respond("\n".join(lines))


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Economy extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Economy extension unloaded.")
