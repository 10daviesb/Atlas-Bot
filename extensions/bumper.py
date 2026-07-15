import asyncio
import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None

# guild_id -> {channel_id, remind_channel_id, last_bump, interval}
_bump_config: dict[int, dict] = {}
_reminder_tasks: dict[int, asyncio.Task] = {}

DISBOARD_ID = 302050872383242240
BUMP_INTERVAL = 7200  # 2 hours


async def _send_reminder(guild_id: int, channel_id: int) -> None:
    await asyncio.sleep(BUMP_INTERVAL)
    if _rest is None:
        return
    try:
        await _rest.create_message(channel_id, "⏰ Time to bump the server! Use `/bump` with Disboard.")
    except Exception as e:
        logger.warning(f"Bump reminder failed for guild {guild_id}: {e}")
    _reminder_tasks.pop(guild_id, None)


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest
    _rest = event.app.rest
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bump_config (
                guild_id        INTEGER PRIMARY KEY,
                channel_id      INTEGER NOT NULL,
                remind_channel  INTEGER NOT NULL
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, channel_id, remind_channel FROM bump_config") as cur:
            for guild_id, channel_id, remind_channel in await cur.fetchall():
                _bump_config[guild_id] = {
                    "channel_id": channel_id,
                    "remind_channel": remind_channel,
                }
    logger.info("Bumper loaded.")


@loader.listener(hikari.StoppingEvent)
async def on_stopping(event: hikari.StoppingEvent) -> None:
    for task in _reminder_tasks.values():
        task.cancel()


@loader.listener(hikari.GuildMessageCreateEvent)
async def on_message(event: hikari.GuildMessageCreateEvent) -> None:
    if event.author_id != DISBOARD_ID:
        return
    if not event.message.embeds:
        return
    for embed in event.message.embeds:
        if embed.description and "bump done" in embed.description.lower():
            cfg = _bump_config.get(event.guild_id)
            if not cfg:
                return
            # Cancel existing reminder
            old = _reminder_tasks.pop(event.guild_id, None)
            if old:
                old.cancel()
            remind_ch = cfg.get("remind_channel") or cfg["channel_id"]
            task = asyncio.create_task(_send_reminder(event.guild_id, remind_ch))
            _reminder_tasks[event.guild_id] = task
            try:
                await _rest.create_message(event.channel_id, "✅ Bump registered! I'll remind you in 2 hours.")
            except Exception:
                pass
            break


@loader.command
class BumpSetup(
    lightbulb.SlashCommand,
    name="bumpsetup",
    description="Set up the bump reminder system.",
):
    channel = lightbulb.channel("channel", "Channel where bumps happen.")
    remind_channel = lightbulb.channel("remind_channel", "Channel for bump reminders.", default=None)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        channel = self.channel
        remind_ch = self.remind_channel or channel
        _bump_config[ctx.guild_id] = {
            "channel_id": channel.id,
            "remind_channel": remind_ch.id,
        }
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO bump_config (guild_id, channel_id, remind_channel) VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, remind_channel = excluded.remind_channel
            """, (ctx.guild_id, channel.id, remind_ch.id))
            await db.commit()
        await ctx.respond(f"✅ Bump reminder configured. Bump channel: {channel.mention}, remind channel: {remind_ch.mention}.")


@loader.command
class BumpDisable(
    lightbulb.SlashCommand,
    name="bumpdisable",
    description="Disable bump reminders.",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        _bump_config.pop(ctx.guild_id, None)
        old = _reminder_tasks.pop(ctx.guild_id, None)
        if old:
            old.cancel()
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM bump_config WHERE guild_id = ?", (ctx.guild_id,))
            await db.commit()
        await ctx.respond("✅ Bump reminders disabled.")
