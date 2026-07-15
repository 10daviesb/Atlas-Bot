import datetime

import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("AFK")

DB_PATH = "atlas.db"

# (guild_id, user_id) -> {reason, since}
_afk: dict[tuple[int, int], dict] = {}


def _now() -> int:
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


def _fmt_elapsed(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    h, m = divmod(seconds // 60, 60)
    return f"{h}h {m}m" if m else f"{h}h"


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS afk (
                guild_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                reason   TEXT    NOT NULL DEFAULT 'AFK',
                since    INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, user_id, reason, since FROM afk") as cur:
            for guild_id, user_id, reason, since in await cur.fetchall():
                _afk[(guild_id, user_id)] = {"reason": reason, "since": since}
    logger.info(f"AFK loaded: {len(_afk)} entries.")


@plugin.listener(hikari.GuildMessageCreateEvent)
async def on_message(event: hikari.GuildMessageCreateEvent) -> None:
    if event.author.is_bot:
        return

    key = (event.guild_id, event.author_id)

    # Clear AFK when the user themselves sends a message
    if key in _afk:
        elapsed = _now() - _afk.pop(key)["since"]
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM afk WHERE guild_id = ? AND user_id = ?", key)
            await db.commit()
        await plugin.bot.rest.create_message(
            event.channel_id,
            f"👋 Welcome back, {event.author.mention}! You were AFK for **{_fmt_elapsed(elapsed)}**."
        )
        return

    # Notify if a mentioned user is AFK
    if not event.content:
        return
    notified: set[int] = set()
    for user_id in event.message.user_mentions_ids:
        if user_id in notified:
            continue
        data = _afk.get((event.guild_id, user_id))
        if data:
            elapsed = _now() - data["since"]
            await plugin.bot.rest.create_message(
                event.channel_id,
                f"💤 <@{user_id}> is AFK: **{data['reason']}** (gone for {_fmt_elapsed(elapsed)})"
            )
            notified.add(user_id)


@plugin.command()
@lightbulb.option("reason", "Why you're going AFK.", type=str, default="AFK")
@lightbulb.command("afk", "Mark yourself as AFK. Auto-clears when you next send a message.")
@lightbulb.implements(lightbulb.SlashCommand)
async def afk(ctx: lightbulb.Context) -> None:
    reason = ctx.options.reason
    now = _now()
    key = (ctx.guild_id, ctx.author.id)
    _afk[key] = {"reason": reason, "since": now}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO afk (guild_id, user_id, reason, since) VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET reason = excluded.reason, since = excluded.since
        """, (ctx.guild_id, ctx.author.id, reason, now))
        await db.commit()
    await ctx.respond(f"💤 You're now AFK: **{reason}**")


def load(bot):
    bot.add_plugin(plugin)
    logger.info("AFK extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("AFK extension unloaded.")
