import asyncio
import datetime
import re

import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None
_reminder_task: asyncio.Task | None = None


def _parse_duration(text: str) -> int | None:
    m = re.fullmatch(r"(\d+)([smhd])", text.strip().lower())
    if not m:
        return None
    val, unit = int(m.group(1)), m.group(2)
    return val * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


async def _fire_reminders() -> None:
    while True:
        await asyncio.sleep(15)
        if _rest is None:
            continue
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, user_id, channel_id, message FROM reminders WHERE fire_at <= ?",
                (now,)
            ) as cur:
                due = await cur.fetchall()
            for rid, user_id, channel_id, message in due:
                try:
                    await _rest.create_message(channel_id, f"⏰ <@{user_id}> Reminder: **{message}**")
                except Exception as e:
                    logger.warning(f"Reminder delivery failed: {e}")
                await db.execute("DELETE FROM reminders WHERE id = ?", (rid,))
            if due:
                await db.commit()


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest, _reminder_task
    _rest = event.app.rest
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                message    TEXT    NOT NULL,
                fire_at    REAL    NOT NULL
            )
        """)
        await db.commit()
    _reminder_task = asyncio.create_task(_fire_reminders())
    logger.info("Reminders loaded.")


@loader.listener(hikari.StoppingEvent)
async def on_stopping(event: hikari.StoppingEvent) -> None:
    if _reminder_task:
        _reminder_task.cancel()


@loader.command
class Remind(lightbulb.SlashCommand, name="remind", description="Set a reminder."):
    duration = lightbulb.string("duration", "When to remind you (e.g. 30m, 1h, 2d).")
    message = lightbulb.string("message", "What to remind you about.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        secs = _parse_duration(self.duration)
        if not secs:
            await ctx.respond("❌ Invalid duration. Examples: `30m`, `2h`, `1d`.")
            return
        fire_at = datetime.datetime.now(datetime.timezone.utc).timestamp() + secs
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO reminders (guild_id, user_id, channel_id, message, fire_at)
                VALUES (?, ?, ?, ?, ?)
            """, (ctx.guild_id, ctx.user.id, ctx.channel_id, self.message, fire_at))
            await db.commit()
        fire_dt = datetime.datetime.fromtimestamp(fire_at, tz=datetime.timezone.utc)
        await ctx.respond(f"✅ I'll remind you about **{self.message}** <t:{int(fire_at)}:R>.")
