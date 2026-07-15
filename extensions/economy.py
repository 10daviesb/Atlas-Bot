import datetime
import random

import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
DAILY_AMOUNT = 100
WORK_MIN = 10
WORK_MAX = 75


async def _get_balance(guild_id: int, user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT balance FROM economy WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        ) as cur:
            row = await cur.fetchone()
    return row[0] if row else 0


async def _set_balance(guild_id: int, user_id: int, amount: int) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO economy (guild_id, user_id, balance) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = excluded.balance
        """, (guild_id, user_id, max(0, amount)))
        await db.commit()


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS economy (
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                balance     INTEGER NOT NULL DEFAULT 0,
                last_daily  TEXT,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.commit()
    logger.info("Economy DB initialized.")


@loader.command
class Balance(lightbulb.SlashCommand, name="balance", description="Check your balance or another user's."):
    user = lightbulb.user("user", "User to check.", default=None)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        target = self.user or ctx.user
        bal = await _get_balance(ctx.guild_id, target.id)
        await ctx.respond(f"💰 **{target.username}**'s balance: **{bal} coins**")


@loader.command
class Daily(lightbulb.SlashCommand, name="daily", description="Claim your daily coins."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        today = datetime.date.today().isoformat()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO economy (guild_id, user_id, balance, last_daily) VALUES (?, ?, 0, NULL)
                ON CONFLICT(guild_id, user_id) DO NOTHING
            """, (ctx.guild_id, ctx.user.id))
            async with db.execute(
                "SELECT last_daily, balance FROM economy WHERE guild_id = ? AND user_id = ?",
                (ctx.guild_id, ctx.user.id)
            ) as cur:
                row = await cur.fetchone()
            last_daily, balance = row if row else (None, 0)
            if last_daily == today:
                await ctx.respond("⏰ You've already claimed your daily today. Come back tomorrow!")
                return
            new_balance = (balance or 0) + DAILY_AMOUNT
            await db.execute(
                "UPDATE economy SET balance = ?, last_daily = ? WHERE guild_id = ? AND user_id = ?",
                (new_balance, today, ctx.guild_id, ctx.user.id)
            )
            await db.commit()
        await ctx.respond(f"✅ You claimed your daily **{DAILY_AMOUNT} coins**! New balance: **{new_balance} coins**.")


@loader.command
class Work(lightbulb.SlashCommand, name="work", description="Work to earn some coins."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        earned = random.randint(WORK_MIN, WORK_MAX)
        bal = await _get_balance(ctx.guild_id, ctx.user.id)
        await _set_balance(ctx.guild_id, ctx.user.id, bal + earned)
        actions = [
            f"You fixed some bugs and earned **{earned} coins**.",
            f"You delivered packages and earned **{earned} coins**.",
            f"You coded all night and earned **{earned} coins**.",
            f"You helped at the market and earned **{earned} coins**.",
        ]
        await ctx.respond(f"💼 {random.choice(actions)}")


@loader.command
class Gamble(lightbulb.SlashCommand, name="gamble", description="Gamble your coins."):
    amount = lightbulb.integer("amount", "Amount to gamble.", min_value=1)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        amount = self.amount
        bal = await _get_balance(ctx.guild_id, ctx.user.id)
        if amount > bal:
            await ctx.respond(f"❌ You only have **{bal} coins**.")
            return
        if random.random() < 0.45:
            new_bal = bal + amount
            await _set_balance(ctx.guild_id, ctx.user.id, new_bal)
            await ctx.respond(f"🎰 You won! **+{amount} coins**. New balance: **{new_bal} coins**.")
        else:
            new_bal = bal - amount
            await _set_balance(ctx.guild_id, ctx.user.id, new_bal)
            await ctx.respond(f"🎰 You lost! **-{amount} coins**. New balance: **{new_bal} coins**.")


@loader.command
class Pay(lightbulb.SlashCommand, name="pay", description="Pay another user coins."):
    user = lightbulb.user("user", "User to pay.")
    amount = lightbulb.integer("amount", "Amount to pay.", min_value=1)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        target = self.user
        amount = self.amount
        if target.id == ctx.user.id:
            await ctx.respond("❌ You can't pay yourself.")
            return
        if target.is_bot:
            await ctx.respond("❌ You can't pay a bot.")
            return
        bal = await _get_balance(ctx.guild_id, ctx.user.id)
        if amount > bal:
            await ctx.respond(f"❌ You only have **{bal} coins**.")
            return
        await _set_balance(ctx.guild_id, ctx.user.id, bal - amount)
        target_bal = await _get_balance(ctx.guild_id, target.id)
        await _set_balance(ctx.guild_id, target.id, target_bal + amount)
        await ctx.respond(f"✅ Paid **{amount} coins** to {target.mention}.")


@loader.command
class Richest(lightbulb.SlashCommand, name="richest", description="Show the richest users in the server."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, balance FROM economy WHERE guild_id = ? ORDER BY balance DESC LIMIT 10",
                (ctx.guild_id,)
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            await ctx.respond("ℹ️ No economy data yet.")
            return
        lines = [f"**#{i+1}** <@{uid}>: {bal} coins" for i, (uid, bal) in enumerate(rows)]
        embed = hikari.Embed(title="💰 Richest Members", description="\n".join(lines), color=0xFFD700)
        await ctx.respond(embed=embed)
