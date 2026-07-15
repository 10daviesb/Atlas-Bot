import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"

# guild_id -> [role_id, ...]
_autoroles: dict[int, list[int]] = {}
_rest: hikari.api.RESTClient | None = None


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest
    _rest = event.app.rest
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS autoroles (
                guild_id INTEGER NOT NULL,
                role_id  INTEGER NOT NULL,
                PRIMARY KEY (guild_id, role_id)
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, role_id FROM autoroles") as cur:
            for guild_id, role_id in await cur.fetchall():
                _autoroles.setdefault(guild_id, []).append(role_id)
    logger.info(f"AutoRoles loaded for {len(_autoroles)} guilds.")


@loader.listener(hikari.MemberCreateEvent)
async def on_member_join(event: hikari.MemberCreateEvent) -> None:
    roles = _autoroles.get(event.guild_id)
    if not roles or _rest is None:
        return
    for role_id in roles:
        try:
            await _rest.add_role_to_member(event.guild_id, event.user_id, role_id, reason="AutoRole")
        except Exception as e:
            logger.warning(f"AutoRole failed to assign role {role_id} in guild {event.guild_id}: {e}")


# /autorole group
autorole_group = lightbulb.Group("autorole", "Manage auto-roles assigned to new members.")


@autorole_group.register
class AutoRoleAdd(lightbulb.SlashCommand, name="add", description="Add a role to the auto-role list."):
    role = lightbulb.role("role", "Role to give new members.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_ROLES):
            await ctx.respond("❌ You need the **Manage Roles** permission.")
            return
        role = self.role
        roles = _autoroles.setdefault(ctx.guild_id, [])
        if role.id in roles:
            await ctx.respond(f"⚠️ {role.mention} is already an auto-role.")
            return
        roles.append(role.id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("INSERT OR IGNORE INTO autoroles (guild_id, role_id) VALUES (?, ?)", (ctx.guild_id, role.id))
            await db.commit()
        await ctx.respond(f"✅ {role.mention} will now be given to new members.")


@autorole_group.register
class AutoRoleRemove(lightbulb.SlashCommand, name="remove", description="Remove a role from the auto-role list."):
    role = lightbulb.role("role", "Role to remove.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_ROLES):
            await ctx.respond("❌ You need the **Manage Roles** permission.")
            return
        role = self.role
        roles = _autoroles.get(ctx.guild_id, [])
        if role.id not in roles:
            await ctx.respond(f"⚠️ {role.mention} is not an auto-role.")
            return
        roles.remove(role.id)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM autoroles WHERE guild_id = ? AND role_id = ?", (ctx.guild_id, role.id))
            await db.commit()
        await ctx.respond(f"✅ {role.mention} removed from auto-roles.")


@autorole_group.register
class AutoRoleList(lightbulb.SlashCommand, name="list", description="List all auto-roles."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        roles = _autoroles.get(ctx.guild_id, [])
        if not roles:
            await ctx.respond("ℹ️ No auto-roles set for this server.")
            return
        role_list = "\n".join(f"<@&{r}>" for r in roles)
        await ctx.respond(f"**Auto-roles:**\n{role_list}")


loader.command(autorole_group)
