import asyncio
import datetime
import re
import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("TempRoles")

DB_PATH = "atlas.db"

_DURATION_RE = re.compile(
    r"^(?:(\d+)\s*d(?:ays?)?)?\s*(?:(\d+)\s*h(?:ours?)?)?\s*"
    r"(?:(\d+)\s*m(?:in(?:utes?)?)?)?\s*(?:(\d+)\s*s(?:ec(?:onds?)?)?)?$",
    re.IGNORECASE,
)


def _parse(text: str) -> int | None:
    m = _DURATION_RE.match(text.strip())
    if not m or not any(m.groups()):
        return None
    d, h, mi, s = (int(v) if v else 0 for v in m.groups())
    total = d * 86400 + h * 3600 + mi * 60 + s
    return total if total > 0 else None


def _fmt(seconds: int) -> str:
    parts = []
    for unit, size in [("d", 86400), ("h", 3600), ("m", 60), ("s", 1)]:
        if seconds >= size:
            parts.append(f"{seconds // size}{unit}")
            seconds %= size
    return " ".join(parts) or "0s"


def _now() -> int:
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp())


async def _remove_role(guild_id: int, user_id: int, role_id: int, row_id: int) -> None:
    try:
        await plugin.bot.rest.remove_role_from_member(guild_id, user_id, role_id)
        logger.info(f"Removed temp role {role_id} from {user_id} in guild {guild_id}")
    except Exception as e:
        logger.warning(f"Failed to remove temp role {role_id} from {user_id}: {e}")
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM temp_roles WHERE id = ?", (row_id,))
        await db.commit()


async def _schedule(delay: int, guild_id: int, user_id: int, role_id: int, row_id: int) -> None:
    await asyncio.sleep(delay)
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT id FROM temp_roles WHERE id = ?", (row_id,)) as cur:
            if not await cur.fetchone():
                return
    await _remove_role(guild_id, user_id, role_id, row_id)


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS temp_roles (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                role_id    INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            )
        """)
        await db.commit()
        now = _now()
        async with db.execute(
            "SELECT id, guild_id, user_id, role_id, expires_at FROM temp_roles"
        ) as cur:
            rows = await cur.fetchall()

    expired, pending = [], []
    for row in rows:
        (expired if row[4] <= now else pending).append(row)

    for row_id, guild_id, user_id, role_id, _ in expired:
        asyncio.create_task(_remove_role(guild_id, user_id, role_id, row_id))

    for row_id, guild_id, user_id, role_id, expires_at in pending:
        asyncio.create_task(_schedule(expires_at - now, guild_id, user_id, role_id, row_id))

    logger.info(f"TempRoles loaded: {len(pending)} pending, {len(expired)} expired.")


@plugin.command()
@lightbulb.command("temprole", "Manage temporary roles.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def temprole(ctx: lightbulb.Context) -> None:
    pass


@temprole.child
@lightbulb.option("duration", "How long to give the role, e.g. 1h, 30m, 2d.", type=str)
@lightbulb.option("role", "Role to assign temporarily.", type=hikari.Role)
@lightbulb.option("member", "Member to give the role to.", type=hikari.Member)
@lightbulb.command("give", "Temporarily assign a role to a member.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def temprole_give(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_ROLES:
        await ctx.respond("❌ You need the **Manage Roles** permission.")
        return
    seconds = _parse(ctx.options.duration)
    if not seconds:
        await ctx.respond("❌ Invalid duration. Try `1h`, `30m`, or `2d`.")
        return
    member: hikari.Member = ctx.options.member
    role: hikari.Role = ctx.options.role
    expires_at = _now() + seconds

    try:
        await plugin.bot.rest.add_role_to_member(ctx.guild_id, member, role)
    except Exception as e:
        await ctx.respond(f"❌ Could not assign role: {e}")
        return

    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO temp_roles (guild_id, user_id, role_id, expires_at) VALUES (?, ?, ?, ?)",
            (ctx.guild_id, member.id, role.id, expires_at),
        )
        row_id = cur.lastrowid
        await db.commit()

    asyncio.create_task(_schedule(seconds, ctx.guild_id, member.id, role.id, row_id))
    await ctx.respond(f"✅ {role.mention} given to {member.mention} for **{_fmt(seconds)}**.")


@temprole.child
@lightbulb.option("role", "Role to remove.", type=hikari.Role)
@lightbulb.option("member", "Member to remove the role from.", type=hikari.Member)
@lightbulb.command("revoke", "Remove a temporary role immediately.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def temprole_revoke(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_ROLES:
        await ctx.respond("❌ You need the **Manage Roles** permission.")
        return
    member: hikari.Member = ctx.options.member
    role: hikari.Role = ctx.options.role

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT id FROM temp_roles WHERE guild_id = ? AND user_id = ? AND role_id = ?",
            (ctx.guild_id, member.id, role.id),
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await ctx.respond("❌ No active temp role entry found for that member and role.")
            return
        await db.execute("DELETE FROM temp_roles WHERE id = ?", (row[0],))
        await db.commit()

    try:
        await plugin.bot.rest.remove_role_from_member(ctx.guild_id, member, role)
    except Exception as e:
        await ctx.respond(f"❌ Could not remove role: {e}")
        return
    await ctx.respond(f"✅ Removed {role.mention} from {member.mention}.")


@temprole.child
@lightbulb.command("list", "List active temporary roles in this server.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def temprole_list(ctx: lightbulb.Context) -> None:
    now = _now()
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, role_id, expires_at FROM temp_roles WHERE guild_id = ? ORDER BY expires_at",
            (ctx.guild_id,),
        ) as cur:
            rows = await cur.fetchall()
    if not rows:
        await ctx.respond("No active temporary roles.")
        return
    lines = ["**Active Temporary Roles**"]
    for user_id, role_id, expires_at in rows:
        remaining = _fmt(max(0, expires_at - now))
        lines.append(f"<@{user_id}> — <@&{role_id}> — expires in **{remaining}**")
    await ctx.respond("\n".join(lines))


def load(bot):
    bot.add_plugin(plugin)
    logger.info("TempRoles extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("TempRoles extension unloaded.")
