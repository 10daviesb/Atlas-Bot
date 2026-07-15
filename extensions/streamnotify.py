import asyncio
import aiohttp
import aiosqlite
import hikari
import lightbulb
import logging
from config import config

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("StreamNotify")

DB_PATH = "atlas.db"
POLL_INTERVAL = 300  # 5 minutes

# guild_id -> list of {username, channel_id}
_trackers: dict[int, list[dict]] = {}
# username -> bool (currently live)
_live_state: dict[str, bool] = {}
_twitch_token: str | None = None


async def _get_twitch_token(session: aiohttp.ClientSession) -> str | None:
    if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
        return None
    try:
        async with session.post(
            "https://id.twitch.tv/oauth2/token",
            params={
                "client_id": config.TWITCH_CLIENT_ID,
                "client_secret": config.TWITCH_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
        ) as resp:
            data = await resp.json()
            return data.get("access_token")
    except Exception as e:
        logger.warning(f"Twitch token fetch failed: {e}")
        return None


async def _check_streams() -> None:
    if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
        return
    global _twitch_token
    async with aiohttp.ClientSession() as session:
        if not _twitch_token:
            _twitch_token = await _get_twitch_token(session)
        if not _twitch_token:
            return

        all_usernames: set[str] = set()
        for trackers in _trackers.values():
            for t in trackers:
                all_usernames.add(t["username"].lower())

        if not all_usernames:
            return

        headers = {
            "Client-ID": config.TWITCH_CLIENT_ID,
            "Authorization": f"Bearer {_twitch_token}",
        }
        params = [("user_login", u) for u in all_usernames]
        try:
            async with session.get(
                "https://api.twitch.tv/helix/streams",
                headers=headers,
                params=params,
            ) as resp:
                if resp.status == 401:
                    _twitch_token = await _get_twitch_token(session)
                    return
                data = await resp.json()
        except Exception as e:
            logger.warning(f"Twitch stream check failed: {e}")
            return

        live_now: set[str] = {s["user_login"].lower() for s in data.get("data", [])}
        stream_info: dict[str, dict] = {s["user_login"].lower(): s for s in data.get("data", [])}

        for username in all_usernames:
            was_live = _live_state.get(username, False)
            is_live = username in live_now
            _live_state[username] = is_live

            if is_live and not was_live:
                info = stream_info[username]
                for guild_id, trackers in _trackers.items():
                    for t in trackers:
                        if t["username"].lower() == username:
                            embed = hikari.Embed(
                                title=f"🔴 {info['user_name']} is live!",
                                description=info.get("title", "No title"),
                                color=0x9146FF,
                                url=f"https://twitch.tv/{username}",
                            )
                            embed.add_field("Game", info.get("game_name") or "Unknown", inline=True)
                            embed.add_field("Viewers", str(info.get("viewer_count", 0)), inline=True)
                            try:
                                await plugin.bot.rest.create_message(t["channel_id"], embed=embed)
                            except Exception as e:
                                logger.warning(f"Stream notify failed: {e}")


async def _poll_loop() -> None:
    await asyncio.sleep(10)
    while True:
        await _check_streams()
        await asyncio.sleep(POLL_INTERVAL)


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS stream_trackers (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                username   TEXT    NOT NULL,
                channel_id INTEGER NOT NULL,
                UNIQUE(guild_id, username)
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, username, channel_id FROM stream_trackers") as cur:
            for guild_id, username, channel_id in await cur.fetchall():
                _trackers.setdefault(guild_id, []).append(
                    {"username": username, "channel_id": channel_id}
                )

    if config.TWITCH_CLIENT_ID and config.TWITCH_CLIENT_SECRET:
        asyncio.create_task(_poll_loop())
        logger.info("StreamNotify polling started.")
    else:
        logger.info("StreamNotify: TWITCH_CLIENT_ID/SECRET not set — polling disabled.")


@plugin.command()
@lightbulb.command("stream", "Manage stream live notifications.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def stream(ctx: lightbulb.Context) -> None:
    pass


@stream.child
@lightbulb.option("channel", "Channel to post notifications in.", type=hikari.TextableGuildChannel, default=None)
@lightbulb.option("username", "Twitch username to track.", type=str)
@lightbulb.command("add", "Track a Twitch streamer.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def stream_add(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    if not config.TWITCH_CLIENT_ID or not config.TWITCH_CLIENT_SECRET:
        await ctx.respond("❌ Twitch API credentials not configured. Set `TWITCH_CLIENT_ID` and `TWITCH_CLIENT_SECRET` in `.env`.")
        return
    username: str = ctx.options.username.lower().strip()
    notify_channel = ctx.options.channel or ctx.get_channel()
    channel_id = notify_channel.id

    guild_trackers = _trackers.setdefault(ctx.guild_id, [])
    if any(t["username"] == username for t in guild_trackers):
        await ctx.respond(f"❌ Already tracking **{username}**.")
        return
    guild_trackers.append({"username": username, "channel_id": channel_id})
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO stream_trackers (guild_id, username, channel_id) VALUES (?, ?, ?)",
            (ctx.guild_id, username, channel_id),
        )
        await db.commit()
    await ctx.respond(f"✅ Now tracking **{username}** on Twitch. Notifications → <#{channel_id}>.")


@stream.child
@lightbulb.option("username", "Twitch username to stop tracking.", type=str)
@lightbulb.command("remove", "Stop tracking a Twitch streamer.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def stream_remove(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    username = ctx.options.username.lower().strip()
    guild_trackers = _trackers.get(ctx.guild_id, [])
    before = len(guild_trackers)
    _trackers[ctx.guild_id] = [t for t in guild_trackers if t["username"] != username]
    if len(_trackers[ctx.guild_id]) == before:
        await ctx.respond(f"❌ Not tracking **{username}**.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM stream_trackers WHERE guild_id = ? AND username = ?",
            (ctx.guild_id, username),
        )
        await db.commit()
    await ctx.respond(f"✅ Stopped tracking **{username}**.")


@stream.child
@lightbulb.command("list", "List tracked streamers in this server.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def stream_list(ctx: lightbulb.Context) -> None:
    trackers = _trackers.get(ctx.guild_id, [])
    if not trackers:
        await ctx.respond("No streamers being tracked.")
        return
    lines = ["**Tracked Streamers**"]
    for t in trackers:
        status = "🔴 LIVE" if _live_state.get(t["username"]) else "⚫ offline"
        lines.append(f"**{t['username']}** — {status} → <#{t['channel_id']}>")
    await ctx.respond("\n".join(lines))


def load(bot):
    bot.add_plugin(plugin)
    logger.info("StreamNotify extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("StreamNotify extension unloaded.")
