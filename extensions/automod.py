import datetime
import re
import time
from collections import defaultdict

import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("AutoMod")

DB_PATH = "atlas.db"
SPAM_THRESHOLD = 5    # messages within window triggers timeout
SPAM_WINDOW = 5.0     # seconds
SPAM_TIMEOUT = 60     # seconds to timeout for

URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

# (guild_id, user_id) -> list of recent message timestamps
_message_times: dict[tuple[int, int], list[float]] = defaultdict(list)

# guild_id -> {"spam": bool, "links": bool}
_settings: dict[int, dict[str, bool]] = defaultdict(lambda: {"spam": True, "links": False})


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS automod_words (
                guild_id INTEGER NOT NULL,
                word     TEXT    NOT NULL,
                PRIMARY KEY (guild_id, word)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS automod_settings (
                guild_id      INTEGER PRIMARY KEY,
                spam_enabled  INTEGER NOT NULL DEFAULT 1,
                links_enabled INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, spam_enabled, links_enabled FROM automod_settings") as cur:
            for guild_id, spam, links in await cur.fetchall():
                _settings[guild_id] = {"spam": bool(spam), "links": bool(links)}
    logger.info("AutoMod DB initialized.")


async def _banned_words(guild_id: int) -> set[str]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT word FROM automod_words WHERE guild_id = ?", (guild_id,)) as cur:
            return {row[0] for row in await cur.fetchall()}


async def _save_settings(guild_id: int) -> None:
    s = _settings[guild_id]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO automod_settings (guild_id, spam_enabled, links_enabled) VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET spam_enabled = excluded.spam_enabled, links_enabled = excluded.links_enabled
        """, (guild_id, int(s["spam"]), int(s["links"])))
        await db.commit()


@plugin.listener(hikari.GuildMessageCreateEvent)
async def on_message(event: hikari.GuildMessageCreateEvent) -> None:
    if event.author.is_bot or not event.content:
        return

    settings = _settings[event.guild_id]
    content = event.content

    # Word filter
    banned = await _banned_words(event.guild_id)
    if banned and set(re.findall(r"\w+", content.lower())) & banned:
        try:
            await plugin.bot.rest.delete_message(event.channel_id, event.message_id)
            await plugin.bot.rest.create_message(
                event.channel_id,
                f"⚠️ {event.author.mention}, your message was removed for containing a banned word."
            )
        except Exception as e:
            logger.warning(f"AutoMod word filter failed: {e}")
        return

    # Link filter
    if settings["links"] and URL_PATTERN.search(content):
        try:
            await plugin.bot.rest.delete_message(event.channel_id, event.message_id)
            await plugin.bot.rest.create_message(
                event.channel_id,
                f"⚠️ {event.author.mention}, links are not allowed in this server."
            )
        except Exception as e:
            logger.warning(f"AutoMod link filter failed: {e}")
        return

    # Spam detection
    if settings["spam"]:
        key = (event.guild_id, event.author_id)
        now = time.monotonic()
        times = [t for t in _message_times[key] if now - t < SPAM_WINDOW]
        times.append(now)
        _message_times[key] = times

        if len(times) >= SPAM_THRESHOLD:
            _message_times[key] = []
            until = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=SPAM_TIMEOUT)
            try:
                await plugin.bot.rest.edit_member(
                    event.guild_id, event.author_id,
                    communication_disabled_until=until,
                )
                await plugin.bot.rest.create_message(
                    event.channel_id,
                    f"⚠️ {event.author.mention} has been timed out for **{SPAM_TIMEOUT}s** for spamming."
                )
                logger.info(f"AutoMod: timed out {event.author} for spam in guild {event.guild_id}")
            except Exception as e:
                logger.warning(f"AutoMod spam timeout failed: {e}")


def _has_manage_guild(ctx: lightbulb.Context) -> bool:
    return isinstance(ctx.member, hikari.Member) and bool(ctx.member.permissions & hikari.Permissions.MANAGE_GUILD)


@plugin.command()
@lightbulb.command("automod", "Manage auto-moderation settings.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def automod(ctx: lightbulb.Context) -> None:
    pass


@automod.child
@lightbulb.option("enabled", "Turn spam detection on or off.", type=bool)
@lightbulb.command("spam", "Toggle spam detection.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def automod_spam(ctx: lightbulb.Context) -> None:
    if not _has_manage_guild(ctx):
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    _settings[ctx.guild_id]["spam"] = ctx.options.enabled
    await _save_settings(ctx.guild_id)
    await ctx.respond(f"✅ Spam detection {'enabled' if ctx.options.enabled else 'disabled'}.")


@automod.child
@lightbulb.option("enabled", "Turn link blocking on or off.", type=bool)
@lightbulb.command("links", "Toggle link blocking.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def automod_links(ctx: lightbulb.Context) -> None:
    if not _has_manage_guild(ctx):
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    _settings[ctx.guild_id]["links"] = ctx.options.enabled
    await _save_settings(ctx.guild_id)
    await ctx.respond(f"✅ Link blocking {'enabled' if ctx.options.enabled else 'disabled'}.")


@automod.child
@lightbulb.option("word", "Word to ban.", type=str)
@lightbulb.command("addword", "Add a word to the filter.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def automod_addword(ctx: lightbulb.Context) -> None:
    if not _has_manage_guild(ctx):
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    word = ctx.options.word.lower().strip()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO automod_words (guild_id, word) VALUES (?, ?)", (ctx.guild_id, word))
        await db.commit()
    await ctx.respond(f"✅ `{word}` added to the word filter.")


@automod.child
@lightbulb.option("word", "Word to remove.", type=str)
@lightbulb.command("removeword", "Remove a word from the filter.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def automod_removeword(ctx: lightbulb.Context) -> None:
    if not _has_manage_guild(ctx):
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    word = ctx.options.word.lower().strip()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM automod_words WHERE guild_id = ? AND word = ?", (ctx.guild_id, word))
        await db.commit()
    await ctx.respond(f"✅ `{word}` removed from the word filter.")


@automod.child
@lightbulb.command("listwords", "Show all filtered words.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def automod_listwords(ctx: lightbulb.Context) -> None:
    if not _has_manage_guild(ctx):
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    words = await _banned_words(ctx.guild_id)
    if not words:
        await ctx.respond("📭 No words are currently filtered.")
        return
    await ctx.respond(f"**Filtered words:** {', '.join(f'`{w}`' for w in sorted(words))}")


@automod.child
@lightbulb.command("status", "Show current AutoMod settings.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def automod_status(ctx: lightbulb.Context) -> None:
    s = _settings[ctx.guild_id]
    words = await _banned_words(ctx.guild_id)
    await ctx.respond(
        f"**AutoMod Status**\n"
        f"Spam detection: {'✅' if s['spam'] else '❌'}\n"
        f"Link blocking: {'✅' if s['links'] else '❌'}\n"
        f"Filtered words: {len(words)}"
    )


def load(bot):
    bot.add_plugin(plugin)
    logger.info("AutoMod extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("AutoMod extension unloaded.")
