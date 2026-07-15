import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("ReactionRoles")

DB_PATH = "atlas.db"

# (message_id, emoji_str) -> role_id
_cache: dict[tuple[int, str], int] = {}


def _emoji_key(emoji: hikari.Emoji) -> str:
    if isinstance(emoji, hikari.CustomEmoji):
        return str(emoji.id)
    return str(emoji)


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reaction_roles (
                guild_id   INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                emoji      TEXT    NOT NULL,
                role_id    INTEGER NOT NULL,
                PRIMARY KEY (message_id, emoji)
            )
        """)
        await db.commit()
        async with db.execute("SELECT message_id, emoji, role_id FROM reaction_roles") as cur:
            for message_id, emoji, role_id in await cur.fetchall():
                _cache[(message_id, emoji)] = role_id
    logger.info(f"Reaction roles loaded: {len(_cache)} entries.")


@plugin.listener(hikari.GuildReactionAddEvent)
async def on_reaction_add(event: hikari.GuildReactionAddEvent) -> None:
    if event.user_id == plugin.bot.get_me().id:
        return
    role_id = _cache.get((event.message_id, _emoji_key(event.emoji)))
    if role_id:
        try:
            await plugin.bot.rest.add_role_to_member(event.guild_id, event.user_id, role_id)
        except Exception as e:
            logger.warning(f"Failed to assign reaction role: {e}")


@plugin.listener(hikari.GuildReactionDeleteEvent)
async def on_reaction_remove(event: hikari.GuildReactionDeleteEvent) -> None:
    role_id = _cache.get((event.message_id, _emoji_key(event.emoji)))
    if role_id:
        try:
            await plugin.bot.rest.remove_role_from_member(event.guild_id, event.user_id, role_id)
        except Exception as e:
            logger.warning(f"Failed to remove reaction role: {e}")


@plugin.command()
@lightbulb.command("reactionrole", "Manage reaction roles.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def reactionrole(ctx: lightbulb.Context) -> None:
    pass


@reactionrole.child
@lightbulb.option("role", "Role to assign.", type=hikari.Role)
@lightbulb.option("emoji", "Emoji to react with.", type=str)
@lightbulb.option("message_id", "ID of the target message.", type=str)
@lightbulb.command("add", "Attach a role to a reaction on a message.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def rr_add(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_ROLES:
        await ctx.respond("❌ You need the **Manage Roles** permission.")
        return
    try:
        message_id = int(ctx.options.message_id)
    except ValueError:
        await ctx.respond("❌ Invalid message ID.")
        return

    emoji: str = ctx.options.emoji.strip()
    role: hikari.Role = ctx.options.role

    _cache[(message_id, emoji)] = role.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO reaction_roles (guild_id, message_id, emoji, role_id)
            VALUES (?, ?, ?, ?)
        """, (ctx.guild_id, message_id, emoji, role.id))
        await db.commit()

    try:
        await plugin.bot.rest.add_reaction(ctx.channel_id, message_id, emoji)
    except Exception:
        pass

    await ctx.respond(f"✅ Reacting {emoji} on message `{message_id}` will assign **{role.name}**.")
    logger.info(f"Reaction role added: {emoji} -> {role.name} on msg {message_id}")


@reactionrole.child
@lightbulb.option("emoji", "Emoji to remove.", type=str)
@lightbulb.option("message_id", "ID of the target message.", type=str)
@lightbulb.command("remove", "Remove a reaction role.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def rr_remove(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_ROLES:
        await ctx.respond("❌ You need the **Manage Roles** permission.")
        return
    try:
        message_id = int(ctx.options.message_id)
    except ValueError:
        await ctx.respond("❌ Invalid message ID.")
        return

    emoji: str = ctx.options.emoji.strip()
    _cache.pop((message_id, emoji), None)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM reaction_roles WHERE message_id = ? AND emoji = ?", (message_id, emoji))
        await db.commit()

    await ctx.respond(f"✅ Reaction role for {emoji} on message `{message_id}` removed.")


@reactionrole.child
@lightbulb.command("list", "List all reaction roles in this server.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def rr_list(ctx: lightbulb.Context) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT message_id, emoji, role_id FROM reaction_roles WHERE guild_id = ?",
            (ctx.guild_id,)
        ) as cur:
            rows = await cur.fetchall()

    if not rows:
        await ctx.respond("📭 No reaction roles set up.")
        return

    lines = ["**Reaction Roles**"]
    for message_id, emoji, role_id in rows:
        lines.append(f"{emoji}  on msg `{message_id}` → <@&{role_id}>")
    await ctx.respond("\n".join(lines))


def load(bot):
    bot.add_plugin(plugin)
    logger.info("ReactionRoles extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("ReactionRoles extension unloaded.")
