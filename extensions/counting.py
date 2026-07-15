import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None

# guild_id -> {channel_id, count, last_user_id}
_counting: dict[int, dict] = {}


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest
    _rest = event.app.rest
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS counting_config (
                guild_id     INTEGER PRIMARY KEY,
                channel_id   INTEGER NOT NULL,
                count        INTEGER NOT NULL DEFAULT 0,
                last_user_id INTEGER
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, channel_id, count, last_user_id FROM counting_config") as cur:
            for guild_id, channel_id, count, last_user_id in await cur.fetchall():
                _counting[guild_id] = {
                    "channel_id": channel_id,
                    "count": count,
                    "last_user_id": last_user_id,
                }
    logger.info("Counting loaded.")


@loader.listener(hikari.GuildMessageCreateEvent)
async def on_message(event: hikari.GuildMessageCreateEvent) -> None:
    if event.author.is_bot or _rest is None:
        return
    cfg = _counting.get(event.guild_id)
    if not cfg or event.channel_id != cfg["channel_id"]:
        return

    content = (event.content or "").strip()
    try:
        num = int(content)
    except ValueError:
        try:
            await _rest.delete_message(event.channel_id, event.message_id)
        except Exception:
            pass
        return

    expected = cfg["count"] + 1
    if num != expected or event.author_id == cfg.get("last_user_id"):
        # Reset
        cfg["count"] = 0
        cfg["last_user_id"] = None
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE counting_config SET count = 0, last_user_id = NULL WHERE guild_id = ?",
                (event.guild_id,)
            )
            await db.commit()
        try:
            await _rest.create_message(
                event.channel_id,
                f"❌ The count was ruined! Starting over from 1. (Expected **{expected}**)"
            )
            await _rest.delete_message(event.channel_id, event.message_id)
        except Exception:
            pass
    else:
        cfg["count"] = num
        cfg["last_user_id"] = event.author_id
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE counting_config SET count = ?, last_user_id = ? WHERE guild_id = ?",
                (num, event.author_id, event.guild_id)
            )
            await db.commit()
        try:
            await _rest.add_reaction(event.channel_id, event.message_id, "✅")
        except Exception:
            pass


@loader.command
class CountingSetup(
    lightbulb.SlashCommand,
    name="countingsetup",
    description="Set up the counting channel.",
):
    channel = lightbulb.channel("channel", "Channel for counting.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        channel = self.channel
        _counting[ctx.guild_id] = {"channel_id": channel.id, "count": 0, "last_user_id": None}
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO counting_config (guild_id, channel_id, count, last_user_id) VALUES (?, ?, 0, NULL)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, count = 0, last_user_id = NULL
            """, (ctx.guild_id, channel.id))
            await db.commit()
        await ctx.respond(f"✅ Counting channel set to {channel.mention}. Count reset to 0.")


@loader.command
class CountingDisable(
    lightbulb.SlashCommand,
    name="countingdisable",
    description="Disable the counting channel.",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        _counting.pop(ctx.guild_id, None)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM counting_config WHERE guild_id = ?", (ctx.guild_id,))
            await db.commit()
        await ctx.respond("✅ Counting disabled.")


@loader.command
class CountingCount(
    lightbulb.SlashCommand,
    name="countingcount",
    description="Show the current count.",
):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        cfg = _counting.get(ctx.guild_id)
        if not cfg:
            await ctx.respond("ℹ️ Counting is not set up for this server.")
            return
        await ctx.respond(f"🔢 Current count: **{cfg['count']}**")
