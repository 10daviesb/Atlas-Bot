import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None
_bot_id: int | None = None

# guild_id -> {channel_id, threshold, emoji}
_sb_config: dict[int, dict] = {}
# (guild_id, original_message_id) -> starboard_message_id
_starred: dict[tuple[int, int], int] = {}


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest, _bot_id
    _rest = event.app.rest
    me = await _rest.fetch_my_user()
    _bot_id = me.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS starboard_config (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                threshold  INTEGER NOT NULL DEFAULT 3,
                emoji      TEXT    NOT NULL DEFAULT '⭐'
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS starboard_messages (
                guild_id           INTEGER NOT NULL,
                original_message_id INTEGER NOT NULL,
                starboard_message_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, original_message_id)
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, channel_id, threshold, emoji FROM starboard_config") as cur:
            for guild_id, channel_id, threshold, emoji in await cur.fetchall():
                _sb_config[guild_id] = {"channel_id": channel_id, "threshold": threshold, "emoji": emoji}
        async with db.execute("SELECT guild_id, original_message_id, starboard_message_id FROM starboard_messages") as cur:
            for guild_id, orig_id, sb_id in await cur.fetchall():
                _starred[(guild_id, orig_id)] = sb_id
    logger.info("Starboard loaded.")


@loader.listener(hikari.GuildReactionAddEvent)
async def on_reaction_add(event: hikari.GuildReactionAddEvent) -> None:
    cfg = _sb_config.get(event.guild_id)
    if not cfg or _rest is None:
        return
    if str(event.emoji_name) != cfg["emoji"]:
        return
    if event.user_id == _bot_id:
        return

    try:
        msg = await _rest.fetch_message(event.channel_id, event.message_id)
    except Exception:
        return

    if msg.author.is_bot:
        return

    # Count reactions
    count = 0
    for reaction in msg.reactions:
        if str(reaction.emoji) == cfg["emoji"]:
            count = reaction.count
            break

    if count < cfg["threshold"]:
        return

    sb_channel = cfg["channel_id"]
    key = (event.guild_id, event.message_id)
    existing_sb_id = _starred.get(key)

    content_preview = (msg.content or "")[:500] or "*[no text content]*"
    jump_url = f"https://discord.com/channels/{event.guild_id}/{event.channel_id}/{event.message_id}"

    embed = hikari.Embed(
        description=content_preview,
        color=0xFFD700,
        timestamp=msg.created_at,
    )
    embed.set_author(
        name=msg.author.username,
        icon=msg.author.avatar_url or msg.author.default_avatar_url,
    )
    embed.add_field("Source", f"[Jump to message]({jump_url})", inline=False)
    if msg.attachments:
        embed.set_image(msg.attachments[0].url)

    try:
        if existing_sb_id:
            await _rest.edit_message(
                sb_channel, existing_sb_id,
                content=f"{cfg['emoji']} **{count}** <#{event.channel_id}>",
                embed=embed,
            )
        else:
            sb_msg = await _rest.create_message(
                sb_channel,
                content=f"{cfg['emoji']} **{count}** <#{event.channel_id}>",
                embed=embed,
            )
            _starred[key] = sb_msg.id
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("""
                    INSERT INTO starboard_messages (guild_id, original_message_id, starboard_message_id)
                    VALUES (?, ?, ?)
                    ON CONFLICT(guild_id, original_message_id) DO UPDATE SET starboard_message_id = excluded.starboard_message_id
                """, (event.guild_id, event.message_id, sb_msg.id))
                await db.commit()
    except Exception as e:
        logger.warning(f"Starboard post failed: {e}")


# /starboard group
sb_group = lightbulb.Group("starboard", "Configure the starboard.")


@sb_group.register
class StarboardSet(lightbulb.SlashCommand, name="set", description="Set up the starboard."):
    channel = lightbulb.channel("channel", "Starboard channel.")
    threshold = lightbulb.integer("threshold", "Stars needed to feature a message.", default=3, min_value=1)
    emoji = lightbulb.string("emoji", "Reaction emoji to count.", default="⭐")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        channel = self.channel
        _sb_config[ctx.guild_id] = {
            "channel_id": channel.id,
            "threshold": self.threshold,
            "emoji": self.emoji,
        }
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO starboard_config (guild_id, channel_id, threshold, emoji) VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id=excluded.channel_id, threshold=excluded.threshold, emoji=excluded.emoji
            """, (ctx.guild_id, channel.id, self.threshold, self.emoji))
            await db.commit()
        await ctx.respond(f"✅ Starboard set to {channel.mention} with {self.emoji} × {self.threshold}.")


@sb_group.register
class StarboardDisable(lightbulb.SlashCommand, name="disable", description="Disable the starboard."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        _sb_config.pop(ctx.guild_id, None)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM starboard_config WHERE guild_id = ?", (ctx.guild_id,))
            await db.commit()
        await ctx.respond("✅ Starboard disabled.")


loader.command(sb_group)
