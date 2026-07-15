import random
import time
import aiosqlite
import hikari
import lightbulb
import logging
from config import config

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Leveling")

DB_PATH = "atlas.db"
XP_COOLDOWN = 60  # seconds between XP grants per user
XP_MIN, XP_MAX = 15, 25
IMAGE_XP_MIN, IMAGE_XP_MAX = 5, 15  # bonus for messages with images

# In-memory cooldown: (guild_id, user_id) -> last grant time
_cooldowns: dict[tuple[int, int], float] = {}


def xp_for_level(level: int) -> int:
    return 5 * (level ** 2) + 50 * level + 100


def xp_progress(total_xp: int) -> tuple[int, int, int]:
    """Returns (level, current_xp_in_level, xp_needed_for_next_level)."""
    level, remaining = 0, total_xp
    while remaining >= xp_for_level(level):
        remaining -= xp_for_level(level)
        level += 1
    return level, remaining, xp_for_level(level)


# guild_id -> {level: role_id}
_level_roles: dict[int, dict[int, int]] = {}


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_xp (
                guild_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                xp       INTEGER NOT NULL DEFAULT 0,
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
                _level_roles.setdefault(guild_id, {})[level] = role_id
    logger.info("Leveling DB initialized.")


@plugin.listener(hikari.GuildMessageCreateEvent)
async def on_message(event: hikari.GuildMessageCreateEvent) -> None:
    if event.author.is_bot or not event.content:
        return

    key = (event.guild_id, event.author_id)
    now = time.monotonic()
    if now - _cooldowns.get(key, 0) < XP_COOLDOWN:
        return
    _cooldowns[key] = now

    xp_gain = random.randint(XP_MIN, XP_MAX)
    if any((a.media_type or "").startswith("image/") for a in event.message.attachments):
        xp_gain += random.randint(IMAGE_XP_MIN, IMAGE_XP_MAX)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO user_xp (guild_id, user_id, xp) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = xp + excluded.xp
        """, (event.guild_id, event.author_id, xp_gain))
        await db.commit()

        async with db.execute(
            "SELECT xp FROM user_xp WHERE guild_id = ? AND user_id = ?",
            (event.guild_id, event.author_id),
        ) as cursor:
            row = await cursor.fetchone()

    total_xp = row[0]
    new_level, _, _ = xp_progress(total_xp)
    old_level, _, _ = xp_progress(max(0, total_xp - xp_gain))

    if new_level > old_level:
        await plugin.bot.rest.create_message(
            event.channel_id,
            f"🎉 {event.author.mention} levelled up to **Level {new_level}**!",
        )
        logger.info(f"{event.author} reached level {new_level} in guild {event.guild_id}")
        guild_roles = _level_roles.get(event.guild_id, {})
        for lvl in range(old_level + 1, new_level + 1):
            if lvl in guild_roles:
                try:
                    await plugin.bot.rest.add_role_to_member(
                        event.guild_id, event.author_id, guild_roles[lvl]
                    )
                except Exception as e:
                    logger.warning(f"Level role assign failed (level {lvl}): {e}")


@plugin.command()
@lightbulb.option("member", "Member to check (defaults to you).", type=hikari.Member, default=None)
@lightbulb.command("rank", "Check your level and XP progress.")
@lightbulb.implements(lightbulb.SlashCommand)
async def rank(ctx: lightbulb.Context) -> None:
    target = ctx.options.member or ctx.member

    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT xp FROM user_xp WHERE guild_id = ? AND user_id = ?",
            (ctx.guild_id, target.id),
        ) as cursor:
            row = await cursor.fetchone()

    total_xp = row[0] if row else 0
    level, current, needed = xp_progress(total_xp)
    filled = int((current / needed) * 10)
    bar = "█" * filled + "░" * (10 - filled)

    await ctx.respond(
        f"**{target.display_name}'s Rank**\n"
        f"Level **{level}** — {current}/{needed} XP\n"
        f"`[{bar}]`"
    )
    logger.info(f"rank checked for {target} by {ctx.author}")


@plugin.command()
@lightbulb.command("leaderboard", "Show the top 10 users by XP in this server.")
@lightbulb.implements(lightbulb.SlashCommand)
async def leaderboard(ctx: lightbulb.Context) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT user_id, xp FROM user_xp WHERE guild_id = ? ORDER BY xp DESC LIMIT 10",
            (ctx.guild_id,),
        ) as cursor:
            rows = await cursor.fetchall()

    if not rows:
        await ctx.respond("No one has earned any XP yet — start chatting!")
        return

    medals = ["🥇", "🥈", "🥉"]
    lines = ["**Server Leaderboard**"]
    for i, (user_id, xp) in enumerate(rows):
        prefix = medals[i] if i < 3 else f"`#{i + 1}`"
        level, _, _ = xp_progress(xp)
        lines.append(f"{prefix} <@{user_id}> — Level **{level}** ({xp} XP)")

    await ctx.respond("\n".join(lines))
    logger.info(f"leaderboard viewed by {ctx.author} in guild {ctx.guild_id}")


@plugin.command()
@lightbulb.command("levelrole", "Configure roles awarded at certain levels.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def levelrole(ctx: lightbulb.Context) -> None:
    pass


@levelrole.child
@lightbulb.option("role", "Role to award.", type=hikari.Role)
@lightbulb.option("level", "Level that triggers this role.", type=int)
@lightbulb.command("add", "Award a role when members reach a level.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def levelrole_add(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_ROLES:
        await ctx.respond("❌ You need the **Manage Roles** permission.")
        return
    lvl: int = ctx.options.level
    role: hikari.Role = ctx.options.role
    if lvl < 1:
        await ctx.respond("❌ Level must be at least 1.")
        return
    _level_roles.setdefault(ctx.guild_id, {})[lvl] = role.id
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, level) DO UPDATE SET role_id = excluded.role_id
        """, (ctx.guild_id, lvl, role.id))
        await db.commit()
    await ctx.respond(f"✅ {role.mention} will be awarded at **Level {lvl}**.")


@levelrole.child
@lightbulb.option("level", "Level to remove the role from.", type=int)
@lightbulb.command("remove", "Remove a level role.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def levelrole_remove(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_ROLES:
        await ctx.respond("❌ You need the **Manage Roles** permission.")
        return
    lvl: int = ctx.options.level
    guild_roles = _level_roles.get(ctx.guild_id, {})
    if lvl not in guild_roles:
        await ctx.respond(f"❌ No level role set for Level {lvl}.")
        return
    del guild_roles[lvl]
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM level_roles WHERE guild_id = ? AND level = ?",
            (ctx.guild_id, lvl),
        )
        await db.commit()
    await ctx.respond(f"✅ Level role for **Level {lvl}** removed.")


@levelrole.child
@lightbulb.command("list", "List all level roles.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def levelrole_list(ctx: lightbulb.Context) -> None:
    guild_roles = _level_roles.get(ctx.guild_id, {})
    if not guild_roles:
        await ctx.respond("No level roles configured.")
        return
    lines = ["**Level Roles**"]
    for lvl in sorted(guild_roles):
        lines.append(f"Level **{lvl}** → <@&{guild_roles[lvl]}>")
    await ctx.respond("\n".join(lines))


def load(bot):
    if config.ENABLE_LEVELING:
        bot.add_plugin(plugin)
        logger.info("Leveling extension loaded.")
    else:
        logger.info("Leveling extension skipped (ENABLE_LEVELING=False).")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Leveling extension unloaded.")
