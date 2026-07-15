import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Autoroles")

DB_PATH = "atlas.db"

# guild_id -> list of (role_id, target) where target in ('all', 'human', 'bot')
_roles: dict[int, list[tuple[int, str]]] = {}


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS autoroles (
                guild_id INTEGER NOT NULL,
                role_id  INTEGER NOT NULL,
                target   TEXT    NOT NULL DEFAULT 'human',
                PRIMARY KEY (guild_id, role_id)
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, role_id, target FROM autoroles") as cur:
            for guild_id, role_id, target in await cur.fetchall():
                _roles.setdefault(guild_id, []).append((role_id, target))
    logger.info("Autoroles DB initialized.")


@plugin.listener(hikari.MemberCreateEvent)
async def on_member_join(event: hikari.MemberCreateEvent) -> None:
    entries = _roles.get(event.guild_id, [])
    if not entries:
        return
    is_bot = event.member.is_bot
    for role_id, target in entries:
        if target == "bot" and not is_bot:
            continue
        if target == "human" and is_bot:
            continue
        try:
            await plugin.bot.rest.add_role_to_member(event.guild_id, event.member, role_id)
        except Exception as e:
            logger.warning(f"Autorole {role_id} failed for {event.member}: {e}")


@plugin.command()
@lightbulb.command("autorole", "Configure roles assigned automatically on join.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def autorole(ctx: lightbulb.Context) -> None:
    pass


@autorole.child
@lightbulb.option(
    "target",
    "Who receives this role.",
    choices=["all", "human", "bot"],
    default="human",
)
@lightbulb.option("role", "Role to auto-assign.", type=hikari.Role)
@lightbulb.command("add", "Add an autorole.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def autorole_add(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_ROLES:
        await ctx.respond("❌ You need the **Manage Roles** permission.")
        return
    role: hikari.Role = ctx.options.role
    target: str = ctx.options.target
    entry = (role.id, target)
    guild_roles = _roles.setdefault(ctx.guild_id, [])
    if any(r == role.id for r, _ in guild_roles):
        await ctx.respond(f"❌ {role.mention} is already an autorole.")
        return
    guild_roles.append(entry)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO autoroles (guild_id, role_id, target) VALUES (?, ?, ?)",
            (ctx.guild_id, role.id, target),
        )
        await db.commit()
    await ctx.respond(f"✅ {role.mention} will now be given to **{target}** members on join.")


@autorole.child
@lightbulb.option("role", "Role to remove.", type=hikari.Role)
@lightbulb.command("remove", "Remove an autorole.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def autorole_remove(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_ROLES:
        await ctx.respond("❌ You need the **Manage Roles** permission.")
        return
    role: hikari.Role = ctx.options.role
    guild_roles = _roles.get(ctx.guild_id, [])
    before = len(guild_roles)
    _roles[ctx.guild_id] = [(r, t) for r, t in guild_roles if r != role.id]
    if len(_roles[ctx.guild_id]) == before:
        await ctx.respond(f"❌ {role.mention} is not an autorole.")
        return
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM autoroles WHERE guild_id = ? AND role_id = ?",
            (ctx.guild_id, role.id),
        )
        await db.commit()
    await ctx.respond(f"✅ Removed {role.mention} from autoroles.")


@autorole.child
@lightbulb.command("list", "List configured autoroles.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def autorole_list(ctx: lightbulb.Context) -> None:
    entries = _roles.get(ctx.guild_id, [])
    if not entries:
        await ctx.respond("No autoroles configured.")
        return
    lines = ["**Autoroles**"]
    for role_id, target in entries:
        lines.append(f"<@&{role_id}> — `{target}`")
    await ctx.respond("\n".join(lines))


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Autoroles extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Autoroles extension unloaded.")
