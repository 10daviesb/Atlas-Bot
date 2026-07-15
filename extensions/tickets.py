import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None
_bot_id: int | None = None

# guild_id -> {category_id, support_role_id, log_channel_id}
_ticket_config: dict[int, dict] = {}
# channel_id -> {guild_id, user_id, ticket_number}
_open_tickets: dict[int, dict] = {}


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest, _bot_id
    _rest = event.app.rest
    me = await _rest.fetch_my_user()
    _bot_id = me.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ticket_config (
                guild_id       INTEGER PRIMARY KEY,
                category_id    INTEGER,
                support_role   INTEGER,
                log_channel    INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                user_id     INTEGER NOT NULL,
                channel_id  INTEGER,
                status      TEXT NOT NULL DEFAULT 'open'
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, category_id, support_role, log_channel FROM ticket_config") as cur:
            for guild_id, category_id, support_role, log_channel in await cur.fetchall():
                _ticket_config[guild_id] = {
                    "category_id": category_id,
                    "support_role": support_role,
                    "log_channel": log_channel,
                }
        async with db.execute("SELECT channel_id, guild_id, user_id, id FROM tickets WHERE status = 'open' AND channel_id IS NOT NULL") as cur:
            for channel_id, guild_id, user_id, tid in await cur.fetchall():
                _open_tickets[channel_id] = {"guild_id": guild_id, "user_id": user_id, "ticket_number": tid}
    logger.info("Tickets loaded.")


async def _create_ticket(guild_id: int, user: hikari.User) -> hikari.GuildTextChannel | None:
    if _rest is None:
        return None
    cfg = _ticket_config.get(guild_id)

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tickets (guild_id, user_id, status) VALUES (?, ?, 'open')",
            (guild_id, user.id)
        )
        await db.commit()
        ticket_id = cur.lastrowid

    name = f"ticket-{ticket_id:04d}"
    overwrites = {
        # Deny everyone
        hikari.Snowflake(guild_id): hikari.PermissionOverwrite(
            id=guild_id,
            type=hikari.PermissionOverwriteType.ROLE,
            deny=hikari.Permissions.VIEW_CHANNEL,
        ),
        # Allow the user
        hikari.Snowflake(user.id): hikari.PermissionOverwrite(
            id=user.id,
            type=hikari.PermissionOverwriteType.MEMBER,
            allow=hikari.Permissions.VIEW_CHANNEL | hikari.Permissions.SEND_MESSAGES | hikari.Permissions.READ_MESSAGE_HISTORY,
        ),
    }
    # Allow support role
    if cfg and cfg.get("support_role"):
        overwrites[hikari.Snowflake(cfg["support_role"])] = hikari.PermissionOverwrite(
            id=cfg["support_role"],
            type=hikari.PermissionOverwriteType.ROLE,
            allow=hikari.Permissions.VIEW_CHANNEL | hikari.Permissions.SEND_MESSAGES | hikari.Permissions.READ_MESSAGE_HISTORY | hikari.Permissions.MANAGE_MESSAGES,
        )

    try:
        channel = await _rest.create_guild_text_channel(
            guild_id,
            name,
            category=cfg["category_id"] if cfg and cfg.get("category_id") else hikari.UNDEFINED,
            permission_overwrites=list(overwrites.values()),
            topic=f"Support ticket for {user.username} | ID: {ticket_id}",
        )
    except Exception as e:
        logger.error(f"Failed to create ticket channel: {e}")
        return None

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tickets SET channel_id = ? WHERE id = ?", (channel.id, ticket_id))
        await db.commit()

    _open_tickets[channel.id] = {"guild_id": guild_id, "user_id": user.id, "ticket_number": ticket_id}

    await _rest.create_message(
        channel.id,
        f"👋 Hello {user.mention}! A support member will be with you shortly.\n"
        f"To close this ticket, use `/ticket close`."
    )
    return channel


# /ticket group
ticket_group = lightbulb.Group("ticket", "Manage support tickets.")


@ticket_group.register
class TicketOpen(lightbulb.SlashCommand, name="open", description="Open a support ticket."):
    reason = lightbulb.string("reason", "Reason for opening the ticket.", default="Support needed.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if ctx.guild_id not in _ticket_config:
            await ctx.respond("❌ The ticket system is not set up for this server.")
            return

        # Check for existing open ticket
        existing = next(
            (ch for ch, d in _open_tickets.items() if d["guild_id"] == ctx.guild_id and d["user_id"] == ctx.user.id),
            None
        )
        if existing:
            await ctx.respond(f"❌ You already have an open ticket: <#{existing}>")
            return

        await ctx.respond("✅ Opening your ticket...", flags=hikari.MessageFlag.EPHEMERAL)
        channel = await _create_ticket(ctx.guild_id, ctx.user)
        if channel:
            await ctx.edit_last_response(f"✅ Ticket opened: {channel.mention}")
        else:
            await ctx.edit_last_response("❌ Failed to create ticket channel.")


@ticket_group.register
class TicketClose(lightbulb.SlashCommand, name="close", description="Close a ticket."):
    reason = lightbulb.string("reason", "Reason for closing.", default="Issue resolved.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        ticket = _open_tickets.get(ctx.channel_id)
        if not ticket:
            await ctx.respond("❌ This is not a ticket channel.")
            return

        cfg = _ticket_config.get(ctx.guild_id, {})
        log_ch = cfg.get("log_channel")

        if log_ch and _rest:
            try:
                await _rest.create_message(
                    log_ch,
                    f"🎫 Ticket `{ctx.channel_id}` closed by {ctx.user.mention}. Reason: {self.reason}"
                )
            except Exception:
                pass

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (ctx.channel_id,))
            await db.commit()

        _open_tickets.pop(ctx.channel_id, None)

        await ctx.respond(f"🔒 Ticket closed. Reason: {self.reason}\nThis channel will be deleted in 5 seconds.")

        import asyncio
        await asyncio.sleep(5)
        if _rest:
            try:
                await _rest.delete_channel(ctx.channel_id)
            except Exception as e:
                logger.warning(f"Failed to delete ticket channel: {e}")


@ticket_group.register
class TicketAdd(lightbulb.SlashCommand, name="add", description="Add a user to this ticket."):
    user = lightbulb.user("user", "User to add.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if ctx.channel_id not in _open_tickets:
            await ctx.respond("❌ This is not a ticket channel.")
            return
        target = self.user
        if _rest:
            try:
                await _rest.edit_permission_overwrite(
                    ctx.channel_id,
                    target.id,
                    target_type=hikari.PermissionOverwriteType.MEMBER,
                    allow=hikari.Permissions.VIEW_CHANNEL | hikari.Permissions.SEND_MESSAGES | hikari.Permissions.READ_MESSAGE_HISTORY,
                )
            except Exception as e:
                await ctx.respond(f"❌ Failed to add user: {e}")
                return
        await ctx.respond(f"✅ Added {target.mention} to the ticket.")


@ticket_group.register
class TicketRemove(lightbulb.SlashCommand, name="remove", description="Remove a user from this ticket."):
    user = lightbulb.user("user", "User to remove.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if ctx.channel_id not in _open_tickets:
            await ctx.respond("❌ This is not a ticket channel.")
            return
        target = self.user
        if _rest:
            try:
                await _rest.delete_permission_overwrite(ctx.channel_id, target.id)
            except Exception as e:
                await ctx.respond(f"❌ Failed to remove user: {e}")
                return
        await ctx.respond(f"✅ Removed {target.mention} from the ticket.")


loader.command(ticket_group)


@loader.command
class TicketSetup(
    lightbulb.SlashCommand,
    name="ticketsetup",
    description="Configure the ticket system.",
):
    category = lightbulb.channel("category", "Category channel for tickets.", default=None)
    support_role = lightbulb.role("support_role", "Role that can see all tickets.", default=None)
    log_channel = lightbulb.channel("log_channel", "Channel for ticket logs.", default=None)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.ADMINISTRATOR):
            await ctx.respond("❌ You need the **Administrator** permission.")
            return

        cat = self.category
        sup = self.support_role
        log = self.log_channel

        _ticket_config[ctx.guild_id] = {
            "category_id": cat.id if cat else None,
            "support_role": sup.id if sup else None,
            "log_channel": log.id if log else None,
        }

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO ticket_config (guild_id, category_id, support_role, log_channel) VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    category_id = excluded.category_id,
                    support_role = excluded.support_role,
                    log_channel = excluded.log_channel
            """, (ctx.guild_id, cat.id if cat else None, sup.id if sup else None, log.id if log else None))
            await db.commit()

        parts = ["✅ Ticket system configured!"]
        if cat:
            parts.append(f"Category: {cat.mention}")
        if sup:
            parts.append(f"Support role: {sup.mention}")
        if log:
            parts.append(f"Log channel: {log.mention}")
        await ctx.respond("\n".join(parts))
