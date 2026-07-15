import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_log_channels: dict[int, int] = {}
_rest: hikari.api.RESTClient | None = None


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest
    _rest = event.app.rest
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
    if not channel_id or _rest is None:
        return
    try:
        await _rest.create_message(channel_id, content)
    except Exception as e:
        logger.warning(f"AuditLog post failed: {e}")


@loader.listener(hikari.MemberCreateEvent)
async def on_join(event: hikari.MemberCreateEvent) -> None:
    await _log(event.guild_id, f"📥 **{event.member}** joined the server.")


@loader.listener(hikari.MemberDeleteEvent)
async def on_leave(event: hikari.MemberDeleteEvent) -> None:
    await _log(event.guild_id, f"📤 **{event.user}** left the server.")


@loader.listener(hikari.BanCreateEvent)
async def on_ban(event: hikari.BanCreateEvent) -> None:
    await _log(event.guild_id, f"🔨 **{event.user}** was banned.")


@loader.listener(hikari.BanDeleteEvent)
async def on_unban(event: hikari.BanDeleteEvent) -> None:
    await _log(event.guild_id, f"✅ **{event.user}** was unbanned.")


@loader.listener(hikari.GuildMessageDeleteEvent)
async def on_delete(event: hikari.GuildMessageDeleteEvent) -> None:
    msg = event.old_message
    if msg and not msg.author.is_bot:
        content = (msg.content or "[no text]")[:500]
        await _log(event.guild_id, f"🗑️ Message by **{msg.author}** deleted in <#{event.channel_id}>:\n> {content}")


@loader.listener(hikari.GuildMessageUpdateEvent)
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


@loader.listener(hikari.MemberUpdateEvent)
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


# /auditlog group
auditlog_group = lightbulb.Group("auditlog", "Manage the audit log.")


@loader.command
@auditlog_group.register
class AuditLogSet(lightbulb.SlashCommand, name="set", description="Set the audit log channel."):
    channel = lightbulb.channel("channel", "Channel for audit logs.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        channel = self.channel
        _log_channels[ctx.guild_id] = channel.id
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO auditlog_config (guild_id, channel_id) VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id
            """, (ctx.guild_id, channel.id))
            await db.commit()
        await ctx.respond(f"✅ Audit logs will be sent to {channel.mention}.")


@loader.command
@auditlog_group.register
class AuditLogDisable(lightbulb.SlashCommand, name="disable", description="Disable the audit log."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        _log_channels.pop(ctx.guild_id, None)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM auditlog_config WHERE guild_id = ?", (ctx.guild_id,))
            await db.commit()
        await ctx.respond("✅ Audit logging disabled.")


loader.command(auditlog_group)
