import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("AuditLog")

DB_PATH = "atlas.db"
_log_channels: dict[int, int] = {}


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auditlog_config (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, channel_id FROM auditlog_config") as cur:
            for guild_id, channel_id in await cur.fetchall():
                _log_channels[guild_id] = channel_id
    logger.info("AuditLog DB initialized.")


async def _log(guild_id: int, content: str) -> None:
    channel_id = _log_channels.get(guild_id)
    if not channel_id:
        return
    try:
        await plugin.bot.rest.create_message(channel_id, content)
    except Exception as e:
        logger.warning(f"AuditLog post failed: {e}")


@plugin.listener(hikari.MemberCreateEvent)
async def on_join(event: hikari.MemberCreateEvent) -> None:
    await _log(event.guild_id, f"📥 **{event.member}** joined the server.")


@plugin.listener(hikari.MemberDeleteEvent)
async def on_leave(event: hikari.MemberDeleteEvent) -> None:
    await _log(event.guild_id, f"📤 **{event.user}** left the server.")


@plugin.listener(hikari.BanCreateEvent)
async def on_ban(event: hikari.BanCreateEvent) -> None:
    await _log(event.guild_id, f"🔨 **{event.user}** was banned.")


@plugin.listener(hikari.BanDeleteEvent)
async def on_unban(event: hikari.BanDeleteEvent) -> None:
    await _log(event.guild_id, f"✅ **{event.user}** was unbanned.")


@plugin.listener(hikari.GuildMessageDeleteEvent)
async def on_delete(event: hikari.GuildMessageDeleteEvent) -> None:
    msg = event.old_message
    if msg and not msg.author.is_bot:
        content = (msg.content or "[no text]")[:500]
        await _log(event.guild_id, f"🗑️ Message by **{msg.author}** deleted in <#{event.channel_id}>:\n> {content}")


@plugin.listener(hikari.GuildMessageUpdateEvent)
async def on_edit(event: hikari.GuildMessageUpdateEvent) -> None:
    if not event.old_message or not event.author or event.author.is_bot:
        return
    old = event.old_message.content or "[empty]"
    new = event.content or "[empty]"
    if old != new:
        await _log(
            event.guild_id,
            f"✏️ **{event.author}** edited a message in <#{event.channel_id}>:\n"
            f"> **Before:** {old[:250]}\n> **After:** {new[:250]}"
        )


@plugin.listener(hikari.MemberUpdateEvent)
async def on_member_update(event: hikari.MemberUpdateEvent) -> None:
    old, new = event.old_member, event.member
    if not old or not new:
        return

    added = set(new.role_ids) - set(old.role_ids)
    removed = set(old.role_ids) - set(new.role_ids)
    for role_id in added:
        await _log(event.guild_id, f"🏷️ **{new}** was given role <@&{role_id}>.")
    for role_id in removed:
        await _log(event.guild_id, f"🏷️ **{new}** had role <@&{role_id}> removed.")

    if old.nickname != new.nickname:
        await _log(
            event.guild_id,
            f"📝 **{new.user}** changed nickname: `{old.nickname or 'None'}` → `{new.nickname or 'None'}`"
        )


@plugin.command()
@lightbulb.command("auditlog", "Manage the audit log.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def auditlog(ctx: lightbulb.Context) -> None:
    pass


@auditlog.child
@lightbulb.option("channel", "Channel for audit logs.", type=hikari.TextableGuildChannel)
@lightbulb.command("set", "Set the audit log channel.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def auditlog_set(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    channel = ctx.options.channel
    _log_channels[ctx.guild_id] = channel.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO auditlog_config (guild_id, channel_id) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
        """, (ctx.guild_id, channel.id))
        await db.commit()
    await ctx.respond(f"✅ Audit logs will be sent to {channel.mention}.")


@auditlog.child
@lightbulb.command("disable", "Disable the audit log.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def auditlog_disable(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    _log_channels.pop(ctx.guild_id, None)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM auditlog_config WHERE guild_id = ?", (ctx.guild_id,))
        await db.commit()
    await ctx.respond("✅ Audit logging disabled.")


def load(bot):
    bot.add_plugin(plugin)
    logger.info("AuditLog extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("AuditLog extension unloaded.")
