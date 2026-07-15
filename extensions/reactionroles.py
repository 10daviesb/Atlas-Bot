import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None
_bot_id: int | None = None

# (guild_id, message_id, emoji) -> role_id
_reaction_roles: dict[tuple[int, int, str], int] = {}


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest, _bot_id
    _rest = event.app.rest
    me = await _rest.fetch_my_user()
    _bot_id = me.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS reaction_roles (
                guild_id   INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                emoji      TEXT    NOT NULL,
                role_id    INTEGER NOT NULL,
                PRIMARY KEY (guild_id, message_id, emoji)
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, message_id, emoji, role_id FROM reaction_roles") as cur:
            for guild_id, message_id, emoji, role_id in await cur.fetchall():
                _reaction_roles[(guild_id, message_id, emoji)] = role_id
    logger.info(f"ReactionRoles loaded: {len(_reaction_roles)} entries.")


@loader.listener(hikari.GuildReactionAddEvent)
async def on_reaction_add(event: hikari.GuildReactionAddEvent) -> None:
    if event.user_id == _bot_id or _rest is None:
        return
    emoji_str = str(event.emoji_name)
    role_id = _reaction_roles.get((event.guild_id, event.message_id, emoji_str))
    if role_id:
        try:
            await _rest.add_role_to_member(event.guild_id, event.user_id, role_id, reason="Reaction role")
        except Exception as e:
            logger.warning(f"Failed to add reaction role: {e}")


@loader.listener(hikari.GuildReactionDeleteEvent)
async def on_reaction_remove(event: hikari.GuildReactionDeleteEvent) -> None:
    if event.user_id == _bot_id or _rest is None:
        return
    emoji_str = str(event.emoji_name)
    role_id = _reaction_roles.get((event.guild_id, event.message_id, emoji_str))
    if role_id:
        try:
            await _rest.remove_role_from_member(event.guild_id, event.user_id, role_id, reason="Reaction role removed")
        except Exception as e:
            logger.warning(f"Failed to remove reaction role: {e}")


# /reactionrole group
rr_group = lightbulb.Group("reactionrole", "Manage reaction roles.")


@rr_group.register
class RRAdd(lightbulb.SlashCommand, name="add", description="Add a reaction role to a message."):
    message_id = lightbulb.string("message_id", "Message ID.")
    emoji = lightbulb.string("emoji", "Emoji to react with.")
    role = lightbulb.role("role", "Role to assign.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_ROLES):
            await ctx.respond("❌ You need the **Manage Roles** permission.")
            return
        try:
            mid = int(self.message_id)
        except ValueError:
            await ctx.respond("❌ Invalid message ID.")
            return

        emoji = self.emoji.strip()
        role = self.role
        _reaction_roles[(ctx.guild_id, mid, emoji)] = role.id
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, message_id, emoji) DO UPDATE SET role_id = excluded.role_id
            """, (ctx.guild_id, mid, emoji, role.id))
            await db.commit()

        if _rest:
            try:
                await _rest.add_reaction(ctx.channel_id, mid, emoji)
            except Exception:
                pass

        await ctx.respond(f"✅ Reaction role set: {emoji} → {role.mention}")


@rr_group.register
class RRRemove(lightbulb.SlashCommand, name="remove", description="Remove a reaction role from a message."):
    message_id = lightbulb.string("message_id", "Message ID.")
    emoji = lightbulb.string("emoji", "Emoji of the reaction role to remove.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_ROLES):
            await ctx.respond("❌ You need the **Manage Roles** permission.")
            return
        try:
            mid = int(self.message_id)
        except ValueError:
            await ctx.respond("❌ Invalid message ID.")
            return
        emoji = self.emoji.strip()
        key = (ctx.guild_id, mid, emoji)
        if key not in _reaction_roles:
            await ctx.respond("❌ No reaction role found for that emoji/message.")
            return
        del _reaction_roles[key]
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM reaction_roles WHERE guild_id = ? AND message_id = ? AND emoji = ?", (ctx.guild_id, mid, emoji))
            await db.commit()
        await ctx.respond(f"✅ Reaction role for {emoji} removed.")


@rr_group.register
class RRList(lightbulb.SlashCommand, name="list", description="List all reaction roles in this server."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        entries = [(mid, emoji, rid) for (gid, mid, emoji), rid in _reaction_roles.items() if gid == ctx.guild_id]
        if not entries:
            await ctx.respond("ℹ️ No reaction roles configured.")
            return
        lines = [f"Message `{mid}` | {emoji} → <@&{rid}>" for mid, emoji, rid in entries[:20]]
        await ctx.respond("**Reaction Roles:**\n" + "\n".join(lines))


loader.command(rr_group)
