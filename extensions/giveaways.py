import asyncio
import datetime
import random
import re

import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Giveaways")

DB_PATH = "atlas.db"
GIVEAWAY_EMOJI = "🎉"

_DURATION_RE = re.compile(
    r"^(?:(\d+)\s*d(?:ays?)?)?\s*(?:(\d+)\s*h(?:ours?)?)?\s*"
    r"(?:(\d+)\s*m(?:in(?:utes?)?)?)?\s*(?:(\d+)\s*s(?:ec(?:onds?)?)?)?$",
    re.IGNORECASE,
)


def _parse(text: str) -> int | None:
    m = _DURATION_RE.match(text.strip())
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (int(v) if v else 0 for v in m.groups())
    total = d * 86400 + h * 3600 + mi * 60 + s
    return total if total > 0 else None


def _fmt(seconds: int) -> str:
    parts = []
    for unit, size in [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]:
        if seconds >= size:
            parts.append(f"{seconds // size}{unit}")
            seconds %= size
    return " ".join(parts) or "0s"


async def _pick_winners(channel_id: int, message_id: int, count: int) -> list[int]:
    reactors: list[int] = []
    try:
        async for user in plugin.bot.rest.fetch_reactions_for_emoji(channel_id, message_id, GIVEAWAY_EMOJI):
            if not user.is_bot and user.id != plugin.bot.get_me().id:
                reactors.append(user.id)
    except Exception as e:
        logger.warning(f"Failed to fetch giveaway reactors: {e}")
    return random.sample(reactors, min(count, len(reactors))) if reactors else []


async def _end_giveaway(giveaway_id: int, channel_id: int, message_id: int, prize: str, winner_count: int) -> None:
    winners = await _pick_winners(channel_id, message_id, winner_count)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE giveaways SET ended = 1 WHERE id = ?", (giveaway_id,))
        await db.commit()

    if not winners:
        result = "No valid entries — no winner this time!"
    else:
        result = f"Winner{'s' if len(winners) > 1 else ''}: " + ", ".join(f"<@{w}>" for w in winners)

    try:
        await plugin.bot.rest.edit_message(
            channel_id, message_id,
            embed=hikari.Embed(title="🎉 Giveaway Ended", description=f"**Prize:** {prize}\n{result}", color=0xFF73FA),
        )
        await plugin.bot.rest.create_message(channel_id, f"🎉 The giveaway for **{prize}** has ended! {result}")
    except Exception as e:
        logger.warning(f"Failed to post giveaway result: {e}")


async def _schedule(delay: int, giveaway_id: int, channel_id: int, message_id: int, prize: str, winners: int) -> None:
    await asyncio.sleep(delay)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT ended FROM giveaways WHERE id = ?", (giveaway_id,)) as cur:
            row = await cur.fetchone()
    if row and not row[0]:
        await _end_giveaway(giveaway_id, channel_id, message_id, prize, winners)


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS giveaways (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message_id INTEGER,
                prize      TEXT    NOT NULL,
                winners    INTEGER NOT NULL DEFAULT 1,
                end_time   INTEGER NOT NULL,
                ended      INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.commit()
        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        async with db.execute(
            "SELECT id, channel_id, message_id, prize, winners, end_time FROM giveaways WHERE ended = 0 AND message_id IS NOT NULL"
        ) as cur:
            rows = await cur.fetchall()

    for gid, ch, msg, prize, winners, end_time in rows:
        asyncio.create_task(_schedule(max(0, end_time - now), gid, ch, msg, prize, winners))

    logger.info(f"Giveaways loaded: {len(rows)} pending.")


@plugin.command()
@lightbulb.command("giveaway", "Manage giveaways.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def giveaway(ctx: lightbulb.Context) -> None:
    pass


@giveaway.child
@lightbulb.option("winners", "Number of winners.", type=int, default=1)
@lightbulb.option("prize", "What's being given away.", type=str)
@lightbulb.option("duration", "How long to run, e.g. 1h, 2d, 30m.", type=str)
@lightbulb.command("start", "Start a giveaway.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def giveaway_start(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    seconds = _parse(ctx.options.duration)
    if not seconds:
        await ctx.respond("❌ Invalid duration. Use e.g. `1h`, `30m`, `2d`.")
        return

    prize = ctx.options.prize
    winners = max(1, ctx.options.winners)
    end_dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)
    end_time = int(end_dt.timestamp())

    embed = hikari.Embed(
        title="🎉 Giveaway!",
        description=f"**Prize:** {prize}\n\nReact with 🎉 to enter!\n\n"
                    f"Duration: **{_fmt(seconds)}**\nWinners: **{winners}**",
        color=0xFF73FA,
    )
    embed.timestamp = end_dt
    embed.set_footer("Ends at")

    response = await ctx.respond(embed=embed)
    message = await response.message()
    await plugin.bot.rest.add_reaction(ctx.channel_id, message.id, GIVEAWAY_EMOJI)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO giveaways (guild_id, channel_id, message_id, prize, winners, end_time) VALUES (?, ?, ?, ?, ?, ?)",
            (ctx.guild_id, ctx.channel_id, message.id, prize, winners, end_time),
        )
        giveaway_id = cur.lastrowid
        await db.commit()

    asyncio.create_task(_schedule(seconds, giveaway_id, ctx.channel_id, message.id, prize, winners))
    logger.info(f"Giveaway started by {ctx.author} in guild {ctx.guild_id}: {prize!r}")


@giveaway.child
@lightbulb.option("message_id", "ID of the giveaway message.", type=str)
@lightbulb.command("end", "End a giveaway early and pick winners.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def giveaway_end(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    try:
        message_id = int(ctx.options.message_id)
    except ValueError:
        await ctx.respond("❌ Invalid message ID.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id, channel_id, prize, winners FROM giveaways WHERE message_id = ? AND ended = 0",
            (message_id,),
        ) as cur:
            row = await cur.fetchone()

    if not row:
        await ctx.respond("❌ No active giveaway with that message ID.")
        return

    await ctx.respond("⏹️ Ending giveaway now...")
    await _end_giveaway(row[0], row[1], message_id, row[2], row[3])


@giveaway.child
@lightbulb.option("message_id", "ID of the giveaway message.", type=str)
@lightbulb.command("reroll", "Reroll the winner of a finished giveaway.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def giveaway_reroll(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    try:
        message_id = int(ctx.options.message_id)
    except ValueError:
        await ctx.respond("❌ Invalid message ID.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT channel_id, winners FROM giveaways WHERE message_id = ?",
            (message_id,),
        ) as cur:
            row = await cur.fetchone()

    if not row:
        await ctx.respond("❌ No giveaway found with that message ID.")
        return

    winners = await _pick_winners(row[0], message_id, row[1])
    if not winners:
        await ctx.respond("❌ No valid entries to reroll from.")
        return

    mentions = ", ".join(f"<@{w}>" for w in winners)
    await ctx.respond(f"🎉 Reroll! New winner{'s' if len(winners) > 1 else ''}: {mentions}")


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Giveaways extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Giveaways extension unloaded.")
