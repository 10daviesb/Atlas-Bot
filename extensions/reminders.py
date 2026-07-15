import asyncio
import datetime
import re

import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Reminders")

DB_PATH = "atlas.db"
MAX_DAYS = 30

_DURATION_RE = re.compile(
    r"^(?:(\d+)\s*d(?:ays?)?)?\s*"
    r"(?:(\d+)\s*h(?:ours?)?)?\s*"
    r"(?:(\d+)\s*m(?:in(?:utes?)?)?)?\s*"
    r"(?:(\d+)\s*s(?:ec(?:onds?)?)?)?$",
    re.IGNORECASE,
)


def _parse_duration(text: str) -> int | None:
    m = _DURATION_RE.match(text.strip())
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (int(v) if v else 0 for v in m.groups())
    total = d * 86400 + h * 3600 + mi * 60 + s
    return total if total > 0 else None


def _fmt_duration(seconds: int) -> str:
    parts = []
    for unit, size in [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]:
        if seconds >= size:
            parts.append(f"{seconds // size}{unit}")
            seconds %= size
    return " ".join(parts)


async def _fire(delay: int, channel_id: int, user_id: int, message: str, reminder_id: int) -> None:
    await asyncio.sleep(delay)
    try:
        await plugin.bot.rest.create_message(channel_id, f"⏰ <@{user_id}> Reminder: **{message}**")
    except Exception as e:
        logger.warning(f"Failed to fire reminder {reminder_id}: {e}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        await db.commit()


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message    TEXT    NOT NULL,
                fire_at    INTEGER NOT NULL
            )
        """)
        await db.commit()
        now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        async with db.execute("SELECT id, user_id, channel_id, message, fire_at FROM reminders") as cur:
            rows = await cur.fetchall()

    for rid, user_id, channel_id, message, fire_at in rows:
        asyncio.create_task(_fire(max(0, fire_at - now), channel_id, user_id, message, rid))

    logger.info(f"Reminders loaded: {len(rows)} pending.")


@plugin.command()
@lightbulb.option("message", "What to remind you about.", type=str)
@lightbulb.option("duration", "How long from now, e.g. 1h30m, 2d, 45s.", type=str)
@lightbulb.command("remind", "Set a reminder.")
@lightbulb.implements(lightbulb.SlashCommand)
async def remind(ctx: lightbulb.Context) -> None:
    seconds = _parse_duration(ctx.options.duration)
    if seconds is None:
        await ctx.respond("❌ Invalid duration. Examples: `30m`, `2h`, `1d`, `1h30m`.")
        return
    if seconds > MAX_DAYS * 86400:
        await ctx.respond(f"❌ Reminders can't be more than {MAX_DAYS} days away.")
        return

    fire_at = int((datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=seconds)).timestamp())

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO reminders (user_id, channel_id, message, fire_at) VALUES (?, ?, ?, ?)",
            (ctx.author.id, ctx.channel_id, ctx.options.message, fire_at),
        )
        rid = cur.lastrowid
        await db.commit()

    asyncio.create_task(_fire(seconds, ctx.channel_id, ctx.author.id, ctx.options.message, rid))

    await ctx.respond(f"✅ I'll remind you in **{_fmt_duration(seconds)}**: {ctx.options.message}")
    logger.info(f"Reminder set by {ctx.author}: {seconds}s — {ctx.options.message!r}")


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Reminders extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Reminders extension unloaded.")
