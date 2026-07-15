import random
import time
import aiosqlite
import hikari
import lightbulb
import logging
from config import config

logger = logging.getLogger(__name__)

loader = lightbulb.Loader(should_load_hook=lambda: getattr(config, "ENABLE_LEVELING", True))

DB_PATH = "atlas.db"
_rest: hikari.api.RESTClient | None = None

# (guild_id, user_id) -> last_xp_time
_xp_cooldowns: dict[tuple[int, int], float] = {}
# guild_id -> [(level, role_id), ...]
_level_roles: dict[int, list[tuple[int, int]]] = {}

XP_MIN = 15
XP_MAX = 25
XP_COOLDOWN = 60  # seconds between XP gains


def _xp_for_level(level: int) -> int:
    return 5 * (level ** 2) + 50 * level + 100


@loader.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    global _rest
    _rest = event.app.rest
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS leveling (
                guild_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                xp       INTEGER NOT NULL DEFAULT 0,
                level    INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS level_roles (
                guild_id INTEGER NOT NULL,
                level    INTEGER NOT NULL,
                role_id  INTEGER NOT NULL,
                PRIMARY KEY (guild_id, level)
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, level, role_id FROM level_roles") as cur:
            for guild_id, level, role_id in await cur.fetchall():
                _level_roles.setdefault(guild_id, []).append((level, role_id))
    logger.info("Leveling loaded.")


@loader.listener(hikari.GuildMessageCreateEvent)
async def on_message(event: hikari.GuildMessageCreateEvent) -> None:
    if event.author.is_bot or not event.content or _rest is None:
        return

    key = (event.guild_id, event.author_id)
    now = time.monotonic()
    if now - _xp_cooldowns.get(key, 0) < XP_COOLDOWN:
        return
    _xp_cooldowns[key] = now

    xp_gain = random.randint(XP_MIN, XP_MAX)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO leveling (guild_id, user_id, xp, level) VALUES (?, ?, 0, 0)
            ON CONFLICT(guild_id, user_id) DO NOTHING
        """, (event.guild_id, event.author_id))
        await db.execute(
            "UPDATE leveling SET xp = xp + ? WHERE guild_id = ? AND user_id = ?",
            (xp_gain, event.guild_id, event.author_id)
        )
        async with db.execute(
            "SELECT xp, level FROM leveling WHERE guild_id = ? AND user_id = ?",
            (event.guild_id, event.author_id)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            await db.commit()
            return
        xp, level = row

        # Check for level up
        while xp >= _xp_for_level(level + 1):
            level += 1
            await db.execute(
                "UPDATE leveling SET level = ? WHERE guild_id = ? AND user_id = ?",
                (level, event.guild_id, event.author_id)
            )
            await db.commit()

            # Announce level up
            try:
                await _rest.create_message(
                    event.channel_id,
                    f"🎉 {event.author.mention} reached **level {level}**!"
                )
            except Exception as e:
                logger.warning(f"Level up announcement failed: {e}")

            # Assign level role if configured
            roles = _level_roles.get(event.guild_id, [])
            for req_level, role_id in roles:
                if level == req_level:
                    try:
                        await _rest.add_role_to_member(
                            event.guild_id, event.author_id, role_id,
                            reason=f"Reached level {level}"
                        )
                    except Exception as e:
                        logger.warning(f"Level role assignment failed: {e}")
        await db.commit()


@loader.command
class Rank(lightbulb.SlashCommand, name="rank", description="Check your rank or another user's rank."):
    user = lightbulb.user("user", "User to check.", default=None)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        target = self.user or ctx.user
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT xp, level FROM leveling WHERE guild_id = ? AND user_id = ?",
                (ctx.guild_id, target.id)
            ) as cur:
                row = await cur.fetchone()
        if not row:
            await ctx.respond(f"ℹ️ **{target.username}** hasn't earned any XP yet.")
            return
        xp, level = row
        next_xp = _xp_for_level(level + 1)
        embed = hikari.Embed(title=f"{target.username}'s Rank", color=0x5865F2)
        embed.set_thumbnail(target.avatar_url or target.default_avatar_url)
        embed.add_field("Level", str(level), inline=True)
        embed.add_field("XP", f"{xp} / {next_xp}", inline=True)
        await ctx.respond(embed=embed)


@loader.command
class Leaderboard(lightbulb.SlashCommand, name="leaderboard", description="Show the XP leaderboard."):
    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute(
                "SELECT user_id, xp, level FROM leveling WHERE guild_id = ? ORDER BY xp DESC LIMIT 10",
                (ctx.guild_id,)
            ) as cur:
                rows = await cur.fetchall()
        if not rows:
            await ctx.respond("ℹ️ No leveling data yet.")
            return
        lines = [f"**#{i+1}** <@{uid}>: Level **{lvl}** ({xp} XP)" for i, (uid, xp, lvl) in enumerate(rows)]
        embed = hikari.Embed(title="XP Leaderboard", description="\n".join(lines), color=0x5865F2)
        await ctx.respond(embed=embed)


# /levelrole group
levelrole_group = lightbulb.Group("levelrole", "Configure level-up roles.")


@levelrole_group.register
class LevelRoleSet(lightbulb.SlashCommand, name="set", description="Assign a role at a specific level."):
    level = lightbulb.integer("level", "Level required.", min_value=1)
    role = lightbulb.role("role", "Role to assign.")

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        lvl = self.level
        role = self.role
        roles = _level_roles.setdefault(ctx.guild_id, [])
        roles[:] = [(l, r) for l, r in roles if l != lvl]
        roles.append((lvl, role.id))
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)
                ON CONFLICT(guild_id, level) DO UPDATE SET role_id = excluded.role_id
            """, (ctx.guild_id, lvl, role.id))
            await db.commit()
        await ctx.respond(f"✅ {role.mention} will be assigned at level **{lvl}**.")


@levelrole_group.register
class LevelRoleRemove(lightbulb.SlashCommand, name="remove", description="Remove a level-up role."):
    level = lightbulb.integer("level", "Level to remove role from.", min_value=1)

    @lightbulb.invoke
    async def invoke(self, ctx: lightbulb.Context) -> None:
        if not ctx.member or not (ctx.member.permissions & hikari.Permissions.MANAGE_GUILD):
            await ctx.respond("❌ You need the **Manage Server** permission.")
            return
        lvl = self.level
        roles = _level_roles.get(ctx.guild_id, [])
        _level_roles[ctx.guild_id] = [(l, r) for l, r in roles if l != lvl]
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM level_roles WHERE guild_id = ? AND level = ?", (ctx.guild_id, lvl))
            await db.commit()
        await ctx.respond(f"✅ Level role for level **{lvl}** removed.")


loader.command(levelrole_group)
