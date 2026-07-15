import asyncio
import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Bumper")

DB_PATH = "atlas.db"
DISBOARD_ID = 302050872383242240
BUMP_COOLDOWN = 7200  # 2 hours in seconds

# Strings that appear in Disboard's bump success embed description
_BUMP_STRINGS = ("bump done", "bumped", "server bumped")

# guild_id -> {channel_id, role_id or None}
_configs: dict[int, dict] = {}
# guild_id -> asyncio.Task
_pending: dict[int, asyncio.Task] = {}


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bump_config (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                role_id    INTEGER
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, channel_id, role_id FROM bump_config") as cur:
            for guild_id, channel_id, role_id in await cur.fetchall():
                _configs[guild_id] = {"channel_id": channel_id, "role_id": role_id}
    logger.info("Bumper DB initialized.")


async def _send_reminder(guild_id: int) -> None:
    await asyncio.sleep(BUMP_COOLDOWN)
    cfg = _configs.get(guild_id)
    if not cfg:
        return
    _pending.pop(guild_id, None)
    role_mention = f"<@&{cfg['role_id']}> " if cfg.get("role_id") else ""
    try:
        await plugin.bot.rest.create_message(
            cfg["channel_id"],
            f"🔔 {role_mention}Time to bump the server! Use `/bump` on Disboard.",
        )
    except Exception as e:
        logger.warning(f"Bump reminder failed for guild {guild_id}: {e}")


def _is_bump_success(message: hikari.Message) -> bool:
    if not message.embeds:
        return False
    for embed in message.embeds:
        desc = (embed.description or "").lower()
        if any(s in desc for s in _BUMP_STRINGS):
            return True
    return False


@plugin.listener(hikari.GuildMessageCreateEvent)
async def on_message(event: hikari.GuildMessageCreateEvent) -> None:
    if event.author_id != DISBOARD_ID:
        return
    if not _configs.get(event.guild_id):
        return
    msg = event.message
    if not _is_bump_success(msg):
        return

    if event.guild_id in _pending:
        _pending[event.guild_id].cancel()

    _pending[event.guild_id] = asyncio.create_task(_send_reminder(event.guild_id))

    try:
        await plugin.bot.rest.add_reaction(event.channel_id, event.message_id, "✅")
    except Exception:
        pass
    logger.info(f"Bump detected in guild {event.guild_id}, reminder scheduled in 2h.")


@plugin.command()
@lightbulb.option("role", "Role to ping when it's time to bump (optional).", type=hikari.Role, default=None)
@lightbulb.option("channel", "Channel to post the bump reminder in.", type=hikari.TextableGuildChannel)
@lightbulb.command("bumpsetup", "Configure the bump reminder system.")
@lightbulb.implements(lightbulb.SlashCommand)
async def bumpsetup(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    channel: hikari.TextableGuildChannel = ctx.options.channel
    role: hikari.Role | None = ctx.options.role
    role_id = role.id if role else None
    _configs[ctx.guild_id] = {"channel_id": channel.id, "role_id": role_id}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO bump_config (guild_id, channel_id, role_id) VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, role_id = excluded.role_id
        """, (ctx.guild_id, channel.id, role_id))
        await db.commit()
    msg = f"✅ Bump reminders will post to {channel.mention}."
    if role:
        msg += f" {role.mention} will be pinged."
    await ctx.respond(msg)


@plugin.command()
@lightbulb.command("bumpdisable", "Disable bump reminders.")
@lightbulb.implements(lightbulb.SlashCommand)
async def bumpdisable(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    _configs.pop(ctx.guild_id, None)
    if ctx.guild_id in _pending:
        _pending.pop(ctx.guild_id).cancel()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM bump_config WHERE guild_id = ?", (ctx.guild_id,))
        await db.commit()
    await ctx.respond("✅ Bump reminders disabled.")


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Bumper extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Bumper extension unloaded.")
