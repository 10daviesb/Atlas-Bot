import hikari
import lightbulb
import logging
import aiosqlite
from config import config

logger = logging.getLogger(__name__)

loader = lightbulb.Loader(should_load_hook=lambda: getattr(config, "ENABLE_WELCOME_MESSAGES", True))

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None

# guild_id -> {channel_id, message}
_welcome_config: dict[int, dict] = {}

DEFAULT_MESSAGE = "Welcome to the server, {mention}! 🎉"


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest
    _rest = event.app.rest
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS welcome_config (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                message    TEXT    NOT NULL
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, channel_id, message FROM welcome_config") as cur:
            for guild_id, channel_id, message in await cur.fetchall():
                _welcome_config[guild_id] = {"channel_id": channel_id, "message": message}
    logger.info(f"Welcome loaded for {len(_welcome_config)} guilds.")


@loader.listener(hikari.MemberCreateEvent)
async def on_member_join(event: hikari.MemberCreateEvent) -> None:
    cfg = _welcome_config.get(event.guild_id)
    if not cfg or _rest is None:
        return

    message_template = cfg["message"]
    try:
        guild = await _rest.fetch_guild(event.guild_id)
        guild_name = guild.name
    except Exception:
        guild_name = "the server"

    message = message_template.format(
        mention=event.member.mention,
        username=event.member.username,
        display_name=event.member.display_name,
        guild=guild_name,
        member_count=getattr(guild, "member_count", "?") if "guild" in dir() else "?",
    )

    try:
        await _rest.create_message(cfg["channel_id"], message)
    except Exception as e:
        logger.warning(f"Welcome message failed: {e}")


@loader.command
class SetWelcome(
    lightbulb.SlashCommand,
    name="setwelcome",
    description="Set up the welcome message.",
):
    channel = lightbulb.channel("channel", "Channel to send welcome messages in.")
    message = lightbulb.string(
        "message",
        "Welcome message. Use {mention}, {username}, {guild}, {member_count}.",
        default=DEFAULT_MESSAGE,
    )

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return

        ch = self.channel
        msg = self.message
        _welcome_config[ctx.guild_id] = {"channel_id": ch.id, "message": msg}

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO welcome_config (guild_id, channel_id, message) VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, message = excluded.message
            """, (ctx.guild_id, ch.id, msg))
            await db.commit()

        preview = msg.format(
            mention=ctx.user.mention,
            username=ctx.user.username,
            display_name=ctx.user.username,
            guild="This Server",
            member_count="?",
        )
        await ctx.respond(f"✅ Welcome message set to channel {ch.mention}.\n**Preview:**\n{preview}")


@loader.command
class ClearWelcome(
    lightbulb.SlashCommand,
    name="clearwelcome",
    description="Remove the welcome message configuration.",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return

        _welcome_config.pop(ctx.guild_id, None)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM welcome_config WHERE guild_id = ?", (ctx.guild_id,))
            await db.commit()
        await ctx.respond("✅ Welcome message removed.")
