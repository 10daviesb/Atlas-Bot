import asyncio
import datetime
import re
import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)

loader = lightbulb.Loader()

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None
_check_task: asyncio.Task | None = None


def _parse_duration(text: str) -> int | None:
    m = re.fullmatch(r"(\d+)([smhd])", text.strip().lower())
    if not m:
        return None
    val, unit = int(m.group(1)), m.group(2)
    return val * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


async def _remove_role(guild_id: int, user_id: int, role_id: int) -> None:
    if _rest is None:
        return
    try:
        await _rest.remove_role_from_member(guild_id, user_id, role_id, reason="TempRole expired")
    except Exception as e:
        logger.warning(f"TempRole removal failed: {e}")


async def _check_loop() -> None:
    while True:
        await asyncio.sleep(30)
        now = datetime.datetime.now(datetime.timezone.utc).timestamp()
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT id, guild_id, user_id, role_id FROM temproles WHERE expires_at <= ?",
                (now,)
            ) as cur:
                due = await cur.fetchall()
            for rid, guild_id, user_id, role_id in due:
                await _remove_role(guild_id, user_id, role_id)
                await db.execute("DELETE FROM temproles WHERE id = ?", (rid,))
            if due:
                await db.commit()


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest, _check_task
    _rest = event.app.rest
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS temproles (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                role_id    INTEGER NOT NULL,
                expires_at REAL    NOT NULL
            )
        """)
        await db.commit()
    _check_task = asyncio.create_task(_check_loop())
    logger.info("TempRoles loaded.")


@loader.listener(hikari.StoppingEvent)
async def on_stopping(event: hikari.StoppingEvent) -> None:
    if _check_task:
        _check_task.cancel()


# /temprole group
temprole_group = lightbulb.Group("temprole", "Manage temporary roles.")


@temprole_group.register
class TempRoleAdd(lightbulb.SlashCommand, name="add", description="Give a user a temporary role."):
    user = lightbulb.user("user", "User to give the role to.")
    role = lightbulb.role("role", "Role to give.")
    duration = lightbulb.string("duration", "Duration (e.g. 1h, 30m, 2d).")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_ROLES):
            await ctx.respond("❌ You need the **Manage Roles** permission.")
            return

        secs = _parse_duration(self.duration)
        if not secs:
            await ctx.respond("❌ Invalid duration. Examples: `30m`, `2h`, `1d`.")
            return

        target = self.user
        role = self.role
        expires_at = datetime.datetime.now(datetime.timezone.utc).timestamp() + secs

        try:
            await ctx.client.rest.add_role_to_member(ctx.guild_id, target.id, role.id, reason="TempRole assigned")
        except hikari.ForbiddenError:
            await ctx.respond("❌ I don't have permission to assign that role.")
            return

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO temproles (guild_id, user_id, role_id, expires_at) VALUES (?, ?, ?, ?)
            """, (ctx.guild_id, target.id, role.id, expires_at))
            await db.commit()

        await ctx.respond(
            f"✅ Gave {role.mention} to {target.mention} for **{self.duration}**. "
            f"Expires <t:{int(expires_at)}:R>."
        )


@temprole_group.register
class TempRoleRemove(lightbulb.SlashCommand, name="remove", description="Remove a temporary role immediately."):
    user = lightbulb.user("user", "User to remove the role from.")
    role = lightbulb.role("role", "Role to remove.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_ROLES):
            await ctx.respond("❌ You need the **Manage Roles** permission.")
            return

        target = self.user
        role = self.role

        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM temproles WHERE guild_id = ? AND user_id = ? AND role_id = ?",
                (ctx.guild_id, target.id, role.id)
            )
            await db.commit()

        await _remove_role(ctx.guild_id, target.id, role.id)
        await ctx.respond(f"✅ Removed {role.mention} from {target.mention}.")


@temprole_group.register
class TempRoleList(lightbulb.SlashCommand, name="list", description="List all active temporary roles."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, role_id, expires_at FROM temproles WHERE guild_id = ? ORDER BY expires_at",
                (ctx.guild_id,)
            ) as cur:
                rows = await cur.fetchall()

        if not rows:
            await ctx.respond("ℹ️ No active temporary roles.")
            return

        lines = [f"<@{uid}> → <@&{rid}> — expires <t:{int(exp)}:R>" for uid, rid, exp in rows[:20]]
        await ctx.respond("**Active Temporary Roles:**\n" + "\n".join(lines))


loader.command(temprole_group)
