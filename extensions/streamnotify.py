import asyncio
import aiohttp
import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None

# guild_id -> {channel_id, streamers: [name], live_cache: {name: bool}}
_stream_config: dict[int, dict] = {}
_poll_task: asyncio.Task | None = None

CHECK_INTERVAL = 120  # seconds


async def _check_twitch(streamer: str) -> bool:
    """Simple check using Twitch's unofficial API. Returns True if live."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://www.twitch.tv/{streamer}",
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    return False
                text = await resp.text()
                return '"isLiveBroadcast":true' in text or '"isLiveBroadcast": true' in text
    except Exception:
        return False


async def _poll_loop() -> None:
    while True:
        await asyncio.sleep(CHECK_INTERVAL)
        if _rest is None:
            continue
        for guild_id, cfg in list(_stream_config.items()):
            channel_id = cfg["channel_id"]
            for streamer in cfg.get("streamers", []):
                was_live = cfg["live_cache"].get(streamer, False)
                is_live = await _check_twitch(streamer)
                cfg["live_cache"][streamer] = is_live
                if is_live and not was_live:
                    try:
                        await _rest.create_message(
                            channel_id,
                            f"🔴 **{streamer}** is now live on Twitch! https://twitch.tv/{streamer}"
                        )
                    except Exception as e:
                        logger.warning(f"Stream notify failed: {e}")


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest, _poll_task
    _rest = event.app.rest
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stream_config (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stream_streamers (
                guild_id INTEGER NOT NULL,
                streamer TEXT    NOT NULL,
                PRIMARY KEY (guild_id, streamer)
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, channel_id FROM stream_config") as cur:
            for guild_id, channel_id in await cur.fetchall():
                _stream_config[guild_id] = {"channel_id": channel_id, "streamers": [], "live_cache": {}}
        async with db.execute("SELECT guild_id, streamer FROM stream_streamers") as cur:
            for guild_id, streamer in await cur.fetchall():
                if guild_id in _stream_config:
                    _stream_config[guild_id]["streamers"].append(streamer)
    _poll_task = asyncio.create_task(_poll_loop())
    logger.info("StreamNotify loaded.")


@loader.listener(hikari.StoppingEvent)
async def on_stopping(event: hikari.StoppingEvent) -> None:
    if _poll_task:
        _poll_task.cancel()


# /stream group
stream_group = lightbulb.Group("stream", "Manage stream notifications.")


@stream_group.register
class StreamSetChannel(lightbulb.SlashCommand, name="setchannel", description="Set the notification channel."):
    channel = lightbulb.channel("channel", "Channel for live notifications.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        ch = self.channel
        cfg = _stream_config.setdefault(ctx.guild_id, {"channel_id": ch.id, "streamers": [], "live_cache": {}})
        cfg["channel_id"] = ch.id
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO stream_config (guild_id, channel_id) VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
            """, (ctx.guild_id, ch.id))
            await db.commit()
        await ctx.respond(f"✅ Stream notifications will be sent to {ch.mention}.")


@stream_group.register
class StreamAdd(lightbulb.SlashCommand, name="add", description="Add a Twitch streamer to monitor."):
    streamer = lightbulb.string("streamer", "Twitch username.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        if ctx.guild_id not in _stream_config:
            await ctx.respond("❌ Please set a notification channel first with `/stream setchannel`.")
            return
        name = self.streamer.lower().strip()
        cfg = _stream_config[ctx.guild_id]
        if name in cfg["streamers"]:
            await ctx.respond(f"⚠️ **{name}** is already being monitored.")
            return
        cfg["streamers"].append(name)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO stream_streamers (guild_id, streamer) VALUES (?, ?)", (ctx.guild_id, name))
            await db.commit()
        await ctx.respond(f"✅ Now monitoring **{name}** on Twitch.")


@stream_group.register
class StreamRemove(lightbulb.SlashCommand, name="remove", description="Remove a streamer from monitoring."):
    streamer = lightbulb.string("streamer", "Twitch username.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        name = self.streamer.lower().strip()
        cfg = _stream_config.get(ctx.guild_id)
        if cfg and name in cfg["streamers"]:
            cfg["streamers"].remove(name)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM stream_streamers WHERE guild_id = ? AND streamer = ?", (ctx.guild_id, name))
            await db.commit()
        await ctx.respond(f"✅ Stopped monitoring **{name}**.")


@stream_group.register
class StreamList(lightbulb.SlashCommand, name="list", description="List monitored streamers."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        cfg = _stream_config.get(ctx.guild_id)
        if not cfg or not cfg["streamers"]:
            await ctx.respond("ℹ️ No streamers being monitored.")
            return
        lines = [f"• **{s}**" for s in cfg["streamers"]]
        await ctx.respond("**Monitored Streamers:**\n" + "\n".join(lines))


loader.command(stream_group)
