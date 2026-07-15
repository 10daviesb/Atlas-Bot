import asyncio
import datetime
import aiosqlite
import hikari
import lightbulb
import logging

logger = logging.getLogger(__name__)
plugin = lightbulb.Plugin("Birthdays")

DB_PATH = "atlas.db"

# guild_id -> {channel_id, role_id or None}
_guild_configs: dict[int, dict] = {}
# (guild_id, user_id) -> (month, day)
_birthdays: dict[tuple[int, int], tuple[int, int]] = {}


@plugin.listener(hikari.StartedEvent)
async def on_started(event: hikari.StartedEvent) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS birthday_config (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                role_id    INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS birthdays (
                guild_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                month    INTEGER NOT NULL,
                day      INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await db.commit()
        async with db.execute("SELECT guild_id, channel_id, role_id FROM birthday_config") as cur:
            for guild_id, channel_id, role_id in await cur.fetchall():
                _guild_configs[guild_id] = {"channel_id": channel_id, "role_id": role_id}
        async with db.execute("SELECT guild_id, user_id, month, day FROM birthdays") as cur:
            for guild_id, user_id, month, day in await cur.fetchall():
                _birthdays[(guild_id, user_id)] = (month, day)

    asyncio.create_task(_birthday_loop())
    logger.info(f"Birthdays loaded: {len(_birthdays)} registered.")


async def _seconds_until_midnight_utc() -> int:
    now = datetime.datetime.now(datetime.timezone.utc)
    tomorrow = (now + datetime.timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return int((tomorrow - now).total_seconds())


async def _birthday_loop() -> None:
    while True:
        await asyncio.sleep(await _seconds_until_midnight_utc())
        now = datetime.datetime.now(datetime.timezone.utc)
        today_month, today_day = now.month, now.day
        await _check_birthdays(today_month, today_day)


async def _check_birthdays(month: int, day: int) -> None:
    for (guild_id, user_id), (b_month, b_day) in list(_birthdays.items()):
        if b_month != month or b_day != day:
            continue
        cfg = _guild_configs.get(guild_id)
        if not cfg:
            continue
        try:
            user = await plugin.bot.rest.fetch_user(user_id)
            embed = hikari.Embed(
                title="🎂 Happy Birthday!",
                description=f"Today is {user.mention}'s birthday! 🎉",
                color=0xFFD700,
            )
            await plugin.bot.rest.create_message(cfg["channel_id"], embed=embed)
            if cfg.get("role_id"):
                await plugin.bot.rest.add_role_to_member(guild_id, user_id, cfg["role_id"])
                asyncio.create_task(_remove_birthday_role(guild_id, user_id, cfg["role_id"]))
        except Exception as e:
            logger.warning(f"Birthday announcement failed for {user_id} in {guild_id}: {e}")


async def _remove_birthday_role(guild_id: int, user_id: int, role_id: int) -> None:
    await asyncio.sleep(86400)
    try:
        await plugin.bot.rest.remove_role_from_member(guild_id, user_id, role_id)
    except Exception as e:
        logger.warning(f"Could not remove birthday role for {user_id}: {e}")


@plugin.command()
@lightbulb.option("role", "Birthday role (optional, given for 24h).", type=hikari.Role, default=None)
@lightbulb.option("channel", "Channel for birthday announcements.", type=hikari.TextableGuildChannel)
@lightbulb.command("birthdaysetup", "Configure birthday announcements.")
@lightbulb.implements(lightbulb.SlashCommand)
async def birthdaysetup(ctx: lightbulb.Context) -> None:
    if not isinstance(ctx.member, hikari.Member) or not ctx.member.permissions & hikari.Permissions.MANAGE_GUILD:
        await ctx.respond("❌ You need the **Manage Server** permission.")
        return
    channel: hikari.TextableGuildChannel = ctx.options.channel
    role: hikari.Role | None = ctx.options.role
    role_id = role.id if role else None
    _guild_configs[ctx.guild_id] = {"channel_id": channel.id, "role_id": role_id}
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO birthday_config (guild_id, channel_id, role_id) VALUES (?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, role_id = excluded.role_id
        """, (ctx.guild_id, channel.id, role_id))
        await db.commit()
    msg = f"✅ Birthday announcements will post to {channel.mention}."
    if role:
        msg += f" Members will receive {role.mention} for 24h on their birthday."
    await ctx.respond(msg)


@plugin.command()
@lightbulb.command("birthday", "Manage your birthday.")
@lightbulb.implements(lightbulb.SlashCommandGroup)
async def birthday(ctx: lightbulb.Context) -> None:
    pass


@birthday.child
@lightbulb.option("day", "Day of birth (1–31).", type=int)
@lightbulb.option("month", "Month of birth (1–12).", type=int)
@lightbulb.command("set", "Register your birthday.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def birthday_set(ctx: lightbulb.Context) -> None:
    month, day = ctx.options.month, ctx.options.day
    try:
        datetime.date(2000, month, day)
    except ValueError:
        await ctx.respond("❌ Invalid date.")
        return
    _birthdays[(ctx.guild_id, ctx.author.id)] = (month, day)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            INSERT INTO birthdays (guild_id, user_id, month, day) VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET month = excluded.month, day = excluded.day
        """, (ctx.guild_id, ctx.author.id, month, day))
        await db.commit()
    await ctx.respond(f"🎂 Birthday set to **{day}/{month}**. We'll celebrate!")


@birthday.child
@lightbulb.command("clear", "Remove your registered birthday.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def birthday_clear(ctx: lightbulb.Context) -> None:
    _birthdays.pop((ctx.guild_id, ctx.author.id), None)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "DELETE FROM birthdays WHERE guild_id = ? AND user_id = ?",
            (ctx.guild_id, ctx.author.id),
        )
        await db.commit()
    await ctx.respond("🗑️ Birthday removed.")


@birthday.child
@lightbulb.option("member", "Member to check (defaults to you).", type=hikari.Member, default=None)
@lightbulb.command("check", "See when a member's birthday is.")
@lightbulb.implements(lightbulb.SlashSubCommand)
async def birthday_check(ctx: lightbulb.Context) -> None:
    target = ctx.options.member or ctx.member
    data = _birthdays.get((ctx.guild_id, target.id))
    if not data:
        await ctx.respond(f"**{target.display_name}** hasn't set their birthday.")
        return
    month, day = data
    await ctx.respond(f"🎂 **{target.display_name}**'s birthday is on **{day}/{month}**.")


def load(bot):
    bot.add_plugin(plugin)
    logger.info("Birthdays extension loaded.")


def unload(bot):
    bot.remove_plugin(plugin)
    logger.info("Birthdays extension unloaded.")
