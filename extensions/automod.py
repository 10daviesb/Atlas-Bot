import re
import time
import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"

# guild_id -> {words, block_links, log_channel, spam_limit}
_settings: dict[int, dict] = {}
# guild_id -> {user_id -> [timestamps]}
_spam_tracker: dict[int, dict[int, list[float]]] = {}

_rest: hikari.api.RESTClient | None = None

URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest
    _rest = event.app.rest
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS automod_settings (
                guild_id    INTEGER PRIMARY KEY,
                block_links INTEGER NOT NULL DEFAULT 0,
                log_channel INTEGER,
                spam_limit  INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS automod_words (
                guild_id INTEGER NOT NULL,
                word     TEXT    NOT NULL,
                PRIMARY KEY (guild_id, word)
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, block_links, log_channel, spam_limit FROM automod_settings") as cur:
            for guild_id, block_links, log_channel, spam_limit in await cur.fetchall():
                _settings[guild_id] = {
                    "words": [],
                    "block_links": bool(block_links),
                    "log_channel": log_channel,
                    "spam_limit": spam_limit,
                }
        async with db.execute("SELECT guild_id, word FROM automod_words") as cur:
            for guild_id, word in await cur.fetchall():
                if guild_id in _settings:
                    _settings[guild_id]["words"].append(word.lower())
    logger.info(f"AutoMod loaded for {len(_settings)} guilds.")


@loader.listener(hikari.GuildMessageCreateEvent)
async def on_message(event: hikari.GuildMessageCreateEvent) -> None:
    if not event.content or event.author.is_bot or _rest is None:
        return
    cfg = _settings.get(event.guild_id)
    if not cfg:
        return

    content_lower = event.content.lower()
    reason: str | None = None

    # Banned words
    for word in cfg["words"]:
        if word in content_lower:
            reason = f"banned word: `{word}`"
            break

    # Link blocking
    if not reason and cfg["block_links"] and URL_RE.search(event.content):
        reason = "links are not allowed"

    # Spam detection
    if not reason and cfg["spam_limit"] > 0:
        now = time.monotonic()
        tracker = _spam_tracker.setdefault(event.guild_id, {})
        timestamps = tracker.setdefault(event.author_id, [])
        timestamps.append(now)
        tracker[event.author_id] = [t for t in timestamps if now - t < 5]
        if len(tracker[event.author_id]) > cfg["spam_limit"]:
            reason = "spam detected"
            tracker[event.author_id] = []

    if reason:
        try:
            await _rest.delete_message(event.channel_id, event.message_id)
        except Exception:
            pass
        try:
            warn = await _rest.create_message(
                event.channel_id,
                f"⚠️ {event.author.mention}, your message was removed: **{reason}**."
            )
            await _rest.delete_message(event.channel_id, warn.id)
        except Exception:
            pass
        log_ch = cfg.get("log_channel")
        if log_ch:
            try:
                await _rest.create_message(
                    log_ch,
                    f"🚫 AutoMod removed a message by **{event.author}** in <#{event.channel_id}>.\n**Reason:** {reason}"
                )
            except Exception:
                pass


# /automod group
automod_group = lightbulb.Group("automod", "Configure AutoMod.")


@automod_group.register
class AutoModAddWord(lightbulb.SlashCommand, name="addword", description="Add a banned word."):
    word = lightbulb.string("word", "Word to ban.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        word = self.word.lower().strip()
        cfg = _settings.setdefault(ctx.guild_id, {"words": [], "block_links": False, "log_channel": None, "spam_limit": 0})
        if word not in cfg["words"]:
            cfg["words"].append(word)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO automod_settings (guild_id, block_links, log_channel, spam_limit)
                VALUES (?, 0, NULL, 0)
                ON CONFLICT(guild_id) DO NOTHING
            """, (ctx.guild_id,))
            await db.execute("INSERT OR IGNORE INTO automod_words (guild_id, word) VALUES (?, ?)", (ctx.guild_id, word))
            await db.commit()
        await ctx.respond(f"✅ `{word}` added to banned words.")


@automod_group.register
class AutoModRemoveWord(lightbulb.SlashCommand, name="removeword", description="Remove a banned word."):
    word = lightbulb.string("word", "Word to unban.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        word = self.word.lower().strip()
        cfg = _settings.get(ctx.guild_id)
        if cfg and word in cfg["words"]:
            cfg["words"].remove(word)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM automod_words WHERE guild_id = ? AND word = ?", (ctx.guild_id, word))
            await db.commit()
        await ctx.respond(f"✅ `{word}` removed from banned words.")


@automod_group.register
class AutoModLinks(lightbulb.SlashCommand, name="links", description="Toggle link blocking."):
    enabled = lightbulb.boolean("enabled", "Whether to block links.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        cfg = _settings.setdefault(ctx.guild_id, {"words": [], "block_links": False, "log_channel": None, "spam_limit": 0})
        cfg["block_links"] = self.enabled
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO automod_settings (guild_id, block_links, log_channel, spam_limit)
                VALUES (?, ?, NULL, 0)
                ON CONFLICT(guild_id) DO UPDATE SET block_links = excluded.block_links
            """, (ctx.guild_id, int(self.enabled)))
            await db.commit()
        status = "enabled" if self.enabled else "disabled"
        await ctx.respond(f"✅ Link blocking is now **{status}**.")


@automod_group.register
class AutoModSpam(lightbulb.SlashCommand, name="spam", description="Set spam message limit (0 = disabled)."):
    limit = lightbulb.integer("limit", "Max messages per 5 seconds (0 to disable).", min_value=0, max_value=50)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        cfg = _settings.setdefault(ctx.guild_id, {"words": [], "block_links": False, "log_channel": None, "spam_limit": 0})
        cfg["spam_limit"] = self.limit
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO automod_settings (guild_id, block_links, log_channel, spam_limit)
                VALUES (?, 0, NULL, ?)
                ON CONFLICT(guild_id) DO UPDATE SET spam_limit = excluded.spam_limit
            """, (ctx.guild_id, self.limit))
            await db.commit()
        if self.limit == 0:
            await ctx.respond("✅ Spam detection disabled.")
        else:
            await ctx.respond(f"✅ Spam detection set: max **{self.limit}** messages per 5 seconds.")


@automod_group.register
class AutoModLogChannel(lightbulb.SlashCommand, name="log", description="Set the AutoMod log channel."):
    channel = lightbulb.channel("channel", "Channel to send mod logs.", default=None)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        channel = self.channel
        channel_id = channel.id if channel else None
        cfg = _settings.setdefault(ctx.guild_id, {"words": [], "block_links": False, "log_channel": None, "spam_limit": 0})
        cfg["log_channel"] = channel_id
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO automod_settings (guild_id, block_links, log_channel, spam_limit)
                VALUES (?, 0, ?, 0)
                ON CONFLICT(guild_id) DO UPDATE SET log_channel = excluded.log_channel
            """, (ctx.guild_id, channel_id))
            await db.commit()
        if channel:
            await ctx.respond(f"✅ AutoMod logs will be sent to {channel.mention}.")
        else:
            await ctx.respond("✅ AutoMod log channel cleared.")


@automod_group.register
class AutoModList(lightbulb.SlashCommand, name="list", description="List banned words and settings."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        cfg = _settings.get(ctx.guild_id)
        if not cfg:
            await ctx.respond("ℹ️ No AutoMod settings configured for this server.")
            return
        words = ", ".join(f"`{w}`" for w in cfg["words"]) or "*none*"
        embed = hikari.Embed(title="AutoMod Settings", color=0x5865F2)
        embed.add_field("Banned Words", words, inline=False)
        embed.add_field("Link Blocking", "Enabled" if cfg["block_links"] else "Disabled", inline=True)
        embed.add_field("Spam Limit", str(cfg["spam_limit"]) if cfg["spam_limit"] else "Disabled", inline=True)
        log_ch = cfg.get("log_channel")
        embed.add_field("Log Channel", f"<#{log_ch}>" if log_ch else "Not set", inline=True)
        await ctx.respond(embed=embed)


loader.command(automod_group)
