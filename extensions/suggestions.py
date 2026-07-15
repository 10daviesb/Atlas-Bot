import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Suggestions")

DB_PATH = "atlas.db"

# guild_id -> channel_id
_channels: dict[int, int] = {}


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS suggestion_config (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                content    TEXT    NOT NULL,
                status     TEXT    NOT NULL DEFAULT 'pending'
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, channel_id FROM suggestion_config") as cur:
            for guild_id, channel_id in await cur.fetchall():
                _channels[guild_id] = channel_id
    logger.info("Suggestions DB initialized.")


@plugin.command()
@lightbulb.option("channel", "Channel for suggestions.", type=hikari.TextableGuildChannel)
@lightbulb.command("suggestionsetup", "Set the channel where suggestions are posted.")
@lightbulb.implements(lightbulb.SlashCommand)
async def suggestionsetup(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    channel = ctx.options.channel
    _channels[ctx.guild_id] = channel.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO suggestion_config (guild_id, channel_id) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
        """, (ctx.guild_id, channel.id))
        await db.commit()
    await ctx.respond(f"✅ Suggestions will be posted to {channel.mention}.")


@plugin.command()
@lightbulb.option("idea", "Your suggestion.", type=str)
@lightbulb.command("suggest", "Submit a suggestion.")
@lightbulb.implements(lightbulb.SlashCommand)
async def suggest(ctx: lightbulb.Context) -> None:
    channel_id = _channels.get(ctx.guild_id)
    if not channel_id:
        await ctx.respond("❌ No suggestions channel configured. Ask an admin to use `/suggestionsetup`.")
        return

    embed = hikari.Embed(title="💡 New Suggestion", description=ctx.options.idea, color=0x5865F2)
    embed.set_author(name=str(ctx.author), icon=ctx.author.display_avatar_url)
    embed.set_footer("Status: Pending")

    msg = await plugin.bot.rest.create_message(channel_id, embed=embed)
    await plugin.bot.rest.add_reaction(channel_id, msg.id, "👍")
    await plugin.bot.rest.add_reaction(channel_id, msg.id, "👎")

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO suggestions (guild_id, message_id, user_id, content) VALUES (?, ?, ?, ?)",
            (ctx.guild_id, msg.id, ctx.author.id, ctx.options.idea),
        )
        await db.commit()

    await ctx.respond(f"✅ Suggestion submitted! See it in <#{channel_id}>.")
    logger.info(f"Suggestion by {ctx.author} in guild {ctx.guild_id}")


async def _review(ctx: lightbulb.Context, status: str, color: int) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    channel_id = _channels.get(ctx.guild_id)
    if not channel_id:
        await ctx.respond("❌ No suggestions channel configured.")
        return
    try:
        message_id = int(ctx.options.message_id)
    except ValueError:
        await ctx.respond("❌ Invalid message ID.")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT content, user_id FROM suggestions WHERE message_id = ? AND guild_id = ?",
            (message_id, ctx.guild_id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await ctx.respond("❌ Suggestion not found.")
            return
        content, user_id = row
        await db.execute(
            "UPDATE suggestions SET status = ? WHERE message_id = ?",
            (status, message_id),
        )
        await db.commit()

    reason = getattr(ctx.options, "reason", None)
    embed = hikari.Embed(
        title=f"💡 Suggestion — {status.title()}",
        description=content,
        color=color,
    )
    embed.set_footer(f"Status: {status.title()}{f'  ·  {reason}' if reason else ''}")
    embed.add_field("Reviewed by", str(ctx.author), inline=True)

    try:
        await plugin.bot.rest.edit_message(channel_id, message_id, embed=embed)
    except Exception as e:
        logger.warning(f"Failed to update suggestion embed: {e}")

    await ctx.respond(f"✅ Suggestion marked as **{status}**.")


@plugin.command()
@lightbulb.command("suggestion", "Review suggestions.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def suggestion(ctx: lightbulb.Context) -> None:
    pass


@suggestion.child
@lightbulb.option("reason", "Reason for approval (optional).", type=str, default=None)
@lightbulb.option("message_id", "ID of the suggestion message.", type=str)
@lightbulb.command("approve", "Approve a suggestion.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def suggestion_approve(ctx: lightbulb.Context) -> None:
    await _review(ctx, "approved", 0x57F287)


@suggestion.child
@lightbulb.option("reason", "Reason for denial (optional).", type=str, default=None)
@lightbulb.option("message_id", "ID of the suggestion message.", type=str)
@lightbulb.command("deny", "Deny a suggestion.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def suggestion_deny(ctx: lightbulb.Context) -> None:
    await _review(ctx, "denied", 0xED4245)


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Suggestions extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Suggestions extension unloaded.")
