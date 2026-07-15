import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Tickets")

DB_PATH = "atlas.db"

# guild_id -> category_id (or None)
_categories: dict[int, int | None] = {}
# channel_id -> user_id
_tickets: dict[int, int] = {}


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS ticket_config (
                guild_id    INTEGER PRIMARY KEY,
                category_id INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                guild_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, category_id FROM ticket_config") as cur:
            for guild_id, cat_id in await cur.fetchall():
                _categories[guild_id] = cat_id
        async with db.execute("SELECT channel_id, user_id FROM tickets") as cur:
            for channel_id, user_id in await cur.fetchall():
                _tickets[channel_id] = user_id
    logger.info(f"Tickets loaded: {len(_tickets)} open.")


@plugin.command()
@lightbulb.command("ticket", "Manage support tickets.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def ticket(ctx: lightbulb.Context) -> None:
    pass


@ticket.child
@lightbulb.option("reason", "Reason for opening this ticket.", type=str, default="No reason provided.")
@lightbulb.command("open", "Open a support ticket.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def ticket_open(ctx: lightbulb.Context) -> None:
    # One ticket per user
    for ch_id, u_id in _tickets.items():
        if u_id == ctx.author.id:
            await ctx.respond(f"❌ You already have an open ticket: <#{ch_id}>.")
            return

    category_id = _categories.get(ctx.guild_id)
    overwrites = [
        hikari.PermissionOverwrite(
            id=ctx.guild_id,
            type=hikari.PermissionOverwriteType.ROLE,
            deny=hikari.Permissions.VIEW_CHANNEL,
        ),
        hikari.PermissionOverwrite(
            id=ctx.author.id,
            type=hikari.PermissionOverwriteType.MEMBER,
            allow=(
                hikari.Permissions.VIEW_CHANNEL
                | hikari.Permissions.SEND_MESSAGES
                | hikari.Permissions.READ_MESSAGE_HISTORY
            ),
        ),
    ]

    name = f"ticket-{ctx.author.username}".lower().replace(" ", "-")[:100]
    try:
        channel = await plugin.bot.rest.create_guild_text_channel(
            ctx.guild_id,
            name,
            category=category_id,
            permission_overwrites=overwrites,
            topic=f"Ticket opened by {ctx.author}",
        )
    except Exception as e:
        await ctx.respond(f"❌ Could not create ticket channel: {e}")
        return

    _tickets[channel.id] = ctx.author.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO tickets (channel_id, guild_id, user_id) VALUES (?, ?, ?)",
            (channel.id, ctx.guild_id, ctx.author.id),
        )
        await db.commit()

    await plugin.bot.rest.create_message(
        channel.id,
        f"👋 Hello {ctx.author.mention}! Your ticket has been created.\n"
        f"**Reason:** {ctx.options.reason}\n\n"
        f"Staff will be with you shortly. Use `/ticket close` when resolved."
    )
    await ctx.respond(f"✅ Ticket opened: {channel.mention}")
    logger.info(f"Ticket opened by {ctx.author} in guild {ctx.guild_id}")


@ticket.child
@lightbulb.command("close", "Close and delete this ticket channel.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def ticket_close(ctx: lightbulb.Context) -> None:
    if ctx.channel_id not in _tickets:
        await ctx.respond("❌ This is not a ticket channel.")
        return

    is_owner = _tickets[ctx.channel_id] == ctx.author.id
    has_manage = isinstance(ctx.member, hikari.Member) and bool(ctx.member.permissions & hikari.Permissions.MANAGE_CHANNELS)
    if not (is_owner or has_manage):
        await ctx.respond("❌ Only the ticket owner or a moderator can close this.")
        return

    await ctx.respond("🔒 Closing ticket...")
    _tickets.pop(ctx.channel_id, None)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tickets WHERE channel_id = ?", (ctx.channel_id,))
        await db.commit()
    await plugin.bot.rest.delete_channel(ctx.channel_id)
    logger.info(f"Ticket {ctx.channel_id} closed by {ctx.author}")


@ticket.child
@lightbulb.option("user", "User to add.", type=hikari.Member)
@lightbulb.command("add", "Add a user to this ticket.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def ticket_add(ctx: lightbulb.Context) -> None:
    if ctx.channel_id not in _tickets:
        await ctx.respond("❌ This is not a ticket channel.")
        return
    member: hikari.Member = ctx.options.user
    await plugin.bot.rest.edit_permission_overwrites(
        ctx.channel_id, member,
        target_type=hikari.PermissionOverwriteType.MEMBER,
        allow=(
            hikari.Permissions.VIEW_CHANNEL
            | hikari.Permissions.SEND_MESSAGES
            | hikari.Permissions.READ_MESSAGE_HISTORY
        ),
    )
    await ctx.respond(f"✅ Added {member.mention} to this ticket.")


@plugin.command()
@lightbulb.option("category", "Category to place ticket channels in.", type=hikari.GuildChannel)
@lightbulb.command("ticketsetup", "Set the category for new ticket channels.")
@lightbulb.implements(lightbulb.SlashCommand)
async def ticketsetup(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    cat = ctx.options.category
    _categories[ctx.guild_id] = cat.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO ticket_config (guild_id, category_id) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET category_id = excluded.category_id
        """, (ctx.guild_id, cat.id))
        await db.commit()
    await ctx.respond(f"✅ Tickets will be created under **{cat.name}**.")


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Tickets extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Tickets extension unloaded.")
