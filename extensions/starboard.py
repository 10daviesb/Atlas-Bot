import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Starboard")

DB_PATH = "atlas.db"
STAR = "⭐"

# guild_id -> {channel_id, threshold}
_config: dict[int, dict] = {}
# original_message_id -> starboard_message_id
_posted: dict[int, int] = {}


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS starboard_config (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                threshold  INTEGER NOT NULL DEFAULT 3
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS starboard_posts (
                original_id  INTEGER PRIMARY KEY,
                starboard_id INTEGER NOT NULL
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, channel_id, threshold FROM starboard_config") as cur:
            for guild_id, channel_id, threshold in await cur.fetchall():
                _config[guild_id] = {"channel_id": channel_id, "threshold": threshold}
        async with db.execute("SELECT original_id, starboard_id FROM starboard_posts") as cur:
            for orig, star in await cur.fetchall():
                _posted[orig] = star
    logger.info("Starboard DB initialized.")


async def _star_count(channel_id: int, message_id: int) -> int:
    try:
        msg = await plugin.bot.rest.fetch_message(channel_id, message_id)
        for reaction in msg.reactions:
            if str(reaction.emoji) == STAR:
                return reaction.count
    except Exception:
        pass
    return 0


async def _make_embed(msg: hikari.Message) -> hikari.Embed:
    embed = hikari.Embed(description=msg.content or "", color=0xFFAC33)
    embed.set_author(name=str(msg.author), icon=msg.author.display_avatar_url)
    link = f"https://discord.com/channels/{msg.guild_id}/{msg.channel_id}/{msg.id}"
    embed.add_field("Source", f"[Jump to message]({link})")
    if msg.attachments:
        embed.set_image(msg.attachments[0].url)
    return embed


@plugin.listener(hikari.GuildReactionAddEvent)
async def on_reaction_add(event: hikari.GuildReactionAddEvent) -> None:
    if str(event.emoji) != STAR:
        return
    cfg = _config.get(event.guild_id)
    if not cfg or event.channel_id == cfg["channel_id"]:
        return

    count = await _star_count(event.channel_id, event.message_id)

    if event.message_id in _posted:
        try:
            await plugin.bot.rest.edit_message(
                cfg["channel_id"], _posted[event.message_id],
                content=f"{STAR} **{count}** | <#{event.channel_id}>",
            )
        except Exception as e:
            logger.warning(f"Failed to update starboard post: {e}")
        return

    if count >= cfg["threshold"]:
        try:
            msg = await plugin.bot.rest.fetch_message(event.channel_id, event.message_id)
            posted = await plugin.bot.rest.create_message(
                cfg["channel_id"],
                content=f"{STAR} **{count}** | <#{event.channel_id}>",
                embed=await _make_embed(msg),
            )
            _posted[event.message_id] = posted.id
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute(
                    "INSERT OR IGNORE INTO starboard_posts (original_id, starboard_id) VALUES (?, ?)",
                    (event.message_id, posted.id)
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Failed to post to starboard: {e}")


@plugin.listener(hikari.GuildReactionDeleteEvent)
async def on_reaction_remove(event: hikari.GuildReactionDeleteEvent) -> None:
    if str(event.emoji) != STAR or event.message_id not in _posted:
        return
    cfg = _config.get(event.guild_id)
    if not cfg:
        return
    count = await _star_count(event.channel_id, event.message_id)
    try:
        await plugin.bot.rest.edit_message(
            cfg["channel_id"], _posted[event.message_id],
            content=f"{STAR} **{count}** | <#{event.channel_id}>",
        )
    except Exception as e:
        logger.warning(f"Failed to update starboard count: {e}")


@plugin.command()
@lightbulb.command("starboard", "Manage the starboard.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def starboard(ctx: lightbulb.Context) -> None:
    pass


@starboard.child
@lightbulb.option("channel", "Channel for starred messages.", type=hikari.TextableGuildChannel)
@lightbulb.command("set", "Set the starboard channel.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def starboard_set(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    channel = ctx.options.channel
    cfg = _config.setdefault(ctx.guild_id, {"threshold": 3})
    cfg["channel_id"] = channel.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO starboard_config (guild_id, channel_id, threshold) VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
        """, (ctx.guild_id, channel.id, cfg["threshold"]))
        await db.commit()
    await ctx.respond(f"✅ Starboard set to {channel.mention}.")


@starboard.child
@lightbulb.option("count", "Stars needed (default 3).", type=int)
@lightbulb.command("threshold", "Set how many ⭐ reactions a message needs.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def starboard_threshold(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    count = max(1, ctx.options.count)
    cfg = _config.setdefault(ctx.guild_id, {})
    cfg["threshold"] = count
    if "channel_id" in cfg:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO starboard_config (guild_id, channel_id, threshold) VALUES (?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET threshold = excluded.threshold
            """, (ctx.guild_id, cfg["channel_id"], count))
            await db.commit()
    await ctx.respond(f"✅ Starboard threshold set to **{count}** ⭐.")


@starboard.child
@lightbulb.command("disable", "Disable the starboard.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def starboard_disable(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    _config.pop(ctx.guild_id, None)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM starboard_config WHERE guild_id = ?", (ctx.guild_id,))
        await db.commit()
    await ctx.respond("✅ Starboard disabled.")


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Starboard extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Starboard extension unloaded.")
